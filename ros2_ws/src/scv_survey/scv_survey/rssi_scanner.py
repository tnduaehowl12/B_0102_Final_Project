"""IF-02 rssi_scanner: iw 로 핫스팟 RSSI 를 1 Hz 로 재서 {ns}/survey/raw (NetRaw) 로 보낸다.

노트북 시험: iface=wlo1, robot_id=laptop. RPi 에서는 iface=wlan0, robot_id=robot4 등.

method=scan (기본): 주변 AP 를 스캔해서 target_ssid 의 signal 을 잰다 (노트북은 turtle08 에 붙은 채로).
  target_ssid 를 비우면 SSID 에 ssid_pattern(iPhone) 이 들어간 AP 중 처음 가장 센 것으로 고정한다.
  실행 중 바꾸기: ros2 param set /{ns}/rssi_scanner target_ssid "csh의 iPhone"
method=link: 지금 붙어 있는 AP 의 signal (예전 방식, target_ssid 를 비우면 붙어 있는 AP 아무거나).

로그: 측정마다 한 줄(SSID·dBm·채널·스캔 시간), status_period 초마다 요약, 상태가 바뀌면 따로 한 줄.
스캔이 실패하면(장치 바쁨 등) NetRaw 를 보내지 않는다 — 미검출로 세면 멀쩡한 칸이 회색이 되므로.
"""

import statistics
import time

import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.duration import Duration
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from scv_msgs.msg import NetRaw
from scv_survey.iw_reader import (
    HotspotTracker, fresh_bss, is_permission_error, iw_available, match_ssid, read_iw_link,
    run_iw_scan)

RAW_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=600,
)

SETCAP_HINT = ('iw scan 권한이 없습니다. 한 번만 실행하세요: sudo setcap cap_net_admin+ep /usr/sbin/iw '
               '(확인: getcap /usr/sbin/iw)')


def _chan(freq_mhz: int) -> str:
    if 2412 <= freq_mhz <= 2472:
        return f'ch{(freq_mhz - 2407) // 5}'
    if freq_mhz == 2484:
        return 'ch14'
    if 5000 <= freq_mhz <= 5900:
        return f'ch{(freq_mhz - 5000) // 5}'
    return '?'


class RssiScanner(Node):
    def __init__(self):
        super().__init__('rssi_scanner')
        self.iface = self.declare_parameter('iface', 'wlo1').value
        self.method = self.declare_parameter('method', 'scan').value
        ssid = self.declare_parameter('target_ssid', '').value
        self.pattern = self.declare_parameter('ssid_pattern', 'iPhone').value
        self.robot_id = self.declare_parameter('robot_id', 'laptop').value
        rate = self.declare_parameter('rate_hz', 1.0).value
        self.rescan_after_miss = self.declare_parameter('rescan_after_miss', 3).value
        self.full_scan_interval = self.declare_parameter('full_scan_interval', 10.0).value
        self.scan_retries = self.declare_parameter('scan_retries', 2).value
        self.log_samples = self.declare_parameter('log_samples', True).value
        status_period = self.declare_parameter('status_period', 10.0).value
        if self.method not in ('scan', 'link'):
            raise ValueError(f"method 는 scan 또는 link (받은 값: {self.method})")

        self.tracker = self._new_tracker(ssid)
        self.link_ssid = ssid
        self.pending_ssid = None
        self.fatal = False
        self.seq = 0
        self.window = self._empty_window()

        self.pub = self.create_publisher(NetRaw, 'survey/raw', RAW_QOS)
        self.add_on_set_parameters_callback(self.on_param)
        self.timer = self.create_timer(1.0 / rate, self.on_timer)
        if status_period > 0:
            self.create_timer(status_period, self.on_status)

        if self.method == 'scan':
            target = (f"'{ssid}' (직접 입력)" if ssid else
                      f"자동 — SSID 에 '{self.pattern}' 가 들어간 AP 중 처음 가장 센 것")
            self.get_logger().info(
                f'측정 시작: iw dev {self.iface} scan, 대상 {target}, {rate} Hz, robot_id={self.robot_id}. '
                '처음엔 전체 대역 스캔(약 5 s)으로 채널을 찾는다')
        else:
            self.get_logger().info(
                f'측정 시작: iw dev {self.iface} link (붙어 있는 AP), '
                f"대상 {repr(ssid) if ssid else '붙어 있는 AP 아무거나'}, {rate} Hz, robot_id={self.robot_id}")

    def _new_tracker(self, ssid):
        return HotspotTracker(ssid=ssid, pattern=self.pattern,
                              rescan_after_miss=self.rescan_after_miss,
                              full_scan_interval=self.full_scan_interval)

    def on_param(self, params):
        for p in params:
            if p.name == 'target_ssid':
                if not isinstance(p.value, str):
                    return SetParametersResult(successful=False, reason='target_ssid 는 문자열')
                self.pending_ssid = p.value     # 다음 측정부터 적용
        return SetParametersResult(successful=True)

    # ------------------------------------------------------------ 측정

    def on_timer(self):
        if self.fatal:
            return
        if self.pending_ssid is not None:
            ssid, self.pending_ssid = self.pending_ssid, None
            self.tracker = self._new_tracker(ssid)
            self.link_ssid = ssid
            self.get_logger().warn(
                f"대상 SSID 변경: {repr(ssid) if ssid else '자동(' + self.pattern + ')'} — 채널을 다시 찾는다")
        if self.method == 'link':
            self.measure_link()
        else:
            self.measure_scan()

    def measure_link(self):
        r = read_iw_link(self.iface, self.link_ssid)
        now = self.get_clock().now()
        self.publish(now, r.detected, r.rssi_dbm)
        name = r.ssid if r.ssid is not None else '(접속 없음)'
        if r.detected:
            self.log_sample(f"'{name}' {r.rssi_dbm:4d} dBm (link)", r.rssi_dbm, None)
        else:
            self.log_sample(f"'{self.link_ssid}' 미검출 (link, 지금 SSID: {name})", None, None)

    def scan_once(self, freqs):
        res = run_iw_scan(self.iface, freqs)
        return res, (fresh_bss(res.bss, res.start_boottime, res.duration_s) if res.ok else [])

    def measure_scan(self):
        freqs = self.tracker.next_freqs(time.monotonic())
        res, fresh = self.scan_once(freqs)
        t_start = res.start_boottime
        # 한 채널 스캔은 AP 가 있어도 4 번에 1 번꼴로 못 듣는다 (probe 응답 누락, 10/11 실측)
        # → 같은 채널을 scan_retries 번까지 다시. 한 번에 약 0.06 s (2.4 GHz 0.15 s)
        for _ in range(max(0, int(self.scan_retries)) if freqs else 0):
            if not res.ok or match_ssid(fresh, ssid=self.tracker.ssid):
                break
            self.window['retry'] += 1
            res, fresh = self.scan_once(freqs)
        now = self.get_clock().now()
        scan_ms = (res.end_boottime - t_start) * 1000.0
        where = f'{freqs[0]} MHz' if freqs else '전체 대역'

        if not res.ok:
            self.window['fail'] += 1
            if is_permission_error(res.error):
                self.get_logger().fatal(SETCAP_HINT)
                self.fatal = True
                return
            self.get_logger().warn(f'스캔 실패 ({where}, {scan_ms:.0f} ms): {res.error} — 이번 측정은 보내지 않음')
            return

        tr = self.tracker.update(fresh, res.full, time.monotonic())
        for e in tr.events:
            if '미검출' in e:
                self.get_logger().warn(e)
            else:
                self.get_logger().info(e)
        if res.full and tr.candidates and (tr.target is None or tr.events):
            self.log_candidates(tr.candidates)

        if tr.target is None:
            self.publish(now, False, None)
            if self.tracker.ssid:
                text = f'{self.tracker.ssid!r} 미검출 (연속 {self.tracker.misses} 회)'
            else:
                text = f"SSID 에 '{self.pattern}' 가 들어간 AP 없음 (찾을 때까지 전체 대역 스캔)"
            self.log_sample(text, None, scan_ms, f'{where} 스캔 {scan_ms:.0f} ms')
            return

        t = tr.target
        rssi = int(round(t.signal_dbm))
        # 측정 시각 = 실제로 들은 시각 (전체 스캔이면 iw 가 끝난 시각과 수 초 차이)
        if t.seen_boottime is not None:
            age_s = res.end_boottime - t.seen_boottime
        else:
            age_s = (t.age_ms or 0) / 1000.0
        stamp = now - Duration(nanoseconds=int(max(0.0, age_s) * 1e9))
        self.publish(stamp, True, rssi)
        self.log_sample(f"'{t.ssid}' {rssi:4d} dBm", rssi, scan_ms,
                        f'{_chan(t.freq_mhz)} {t.freq_mhz} MHz · {t.bssid} · {where} 스캔 {scan_ms:.0f} ms '
                        f'· {age_s * 1000:.0f} ms 전 수신')

    def publish(self, stamp, detected, rssi):
        msg = NetRaw()
        msg.stamp = stamp.to_msg()
        msg.robot_id = self.robot_id
        msg.detected = bool(detected)
        msg.rssi_dbm = int(rssi) if detected else 0
        self.pub.publish(msg)
        self.seq += 1

    # ------------------------------------------------------------ 로그

    def log_sample(self, text, rssi, scan_ms, detail=''):
        w = self.window
        w['n'] += 1
        if rssi is None:
            w['miss'] += 1
        else:
            w['hit'] += 1
            w['rssi'].append(rssi)
        if scan_ms is not None:
            w['scan_ms'].append(scan_ms)
        if self.log_samples:
            line = f'[#{self.seq:4d}] {text}' + (f'  ({detail})' if detail else '')
            # rclpy 는 호출 위치마다 로그 수준이 고정이라 info·warn 을 한 줄에서 고르면 안 된다
            if rssi is not None:
                self.get_logger().info(line)
            else:
                self.get_logger().warn(line)

    def log_candidates(self, candidates):
        lines = ', '.join(f"'{c.ssid}' {c.signal_dbm:.0f} dBm {c.freq_mhz} MHz" for c in candidates[:6])
        self.get_logger().info(f"주변 '{self.pattern}' AP {len(candidates)} 개: {lines}")

    def on_status(self):
        w = self.window
        if self.method == 'scan':
            target = repr(self.tracker.ssid) if self.tracker.ssid else f"찾는 중('{self.pattern}')"
            chan = f'{self.tracker.freq} MHz' if self.tracker.freq else '채널 모름'
            head = f'[상태] 대상 {target} · {chan}'
        else:
            head = f"[상태] link {repr(self.link_ssid) if self.link_ssid else '(붙어 있는 AP)'}"
        rssi = f'중앙값 {statistics.median(w["rssi"]):.0f} dBm (최소 {min(w["rssi"])}, 최대 {max(w["rssi"])})' \
            if w['rssi'] else 'RSSI 없음'
        scan = f' · 스캔 평균 {statistics.mean(w["scan_ms"]):.0f} ms' if w['scan_ms'] else ''
        retry = f" · 재스캔 {w['retry']}" if w['retry'] else ''
        self.get_logger().info(
            f"{head} · 최근 측정 {w['n']} (검출 {w['hit']} / 미검출 {w['miss']} / 실패 {w['fail']}) · "
            f'{rssi}{scan}{retry} · 누적 발행 {self.seq}')
        self.window = self._empty_window()

    @staticmethod
    def _empty_window():
        return {'n': 0, 'hit': 0, 'miss': 0, 'fail': 0, 'retry': 0, 'rssi': [], 'scan_ms': []}


def main(args=None):
    rclpy.init(args=args)
    if not iw_available():
        rclpy.logging.get_logger('rssi_scanner').fatal(
            'iw 명령이 없습니다. sudo apt install iw 로 설치하세요.')
        rclpy.try_shutdown()
        return 1
    node = RssiScanner()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()

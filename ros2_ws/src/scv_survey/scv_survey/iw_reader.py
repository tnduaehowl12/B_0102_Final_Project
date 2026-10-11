"""iw 로 핫스팟 RSSI 를 읽는다 (ROS 와 무관).

두 가지 방식:
- scan (기본): `iw dev <iface> scan [freq …]` 로 주변 AP 를 들어서 대상 SSID 의 signal 을 꺼낸다.
  노트북은 다른 AP(turtle08)에 붙은 채로 핫스팟을 '듣기만' 한다. 스캔에는 CAP_NET_ADMIN 이 필요하다
  (`sudo setcap cap_net_admin+ep /usr/sbin/iw`).
- link: `iw dev <iface> link` 로 지금 붙어 있는 AP 하나의 signal 만 읽는다. root 불필요.

iw scan 출력에는 이번 스캔에서 못 들은 AP 도 커널 캐시(최대 약 30 초)에서 같이 나온다.
그래서 BSS 마다 `last seen` 시각으로 이번 스캔에서 들은 것만 남긴다 (`fresh_bss`).
"""

import math
import re
import shutil
import subprocess
import time
from typing import List, NamedTuple, Optional, Sequence

_SSID_RE = re.compile(r'^\s*SSID:\s*(.*)$', re.MULTILINE)
_SIGNAL_RE = re.compile(r'^\s*signal:\s*(-?\d+)\s*dBm', re.MULTILINE)

# iw scan 출력 (BSS 블록 안). SSID 는 탭 하나로 시작하는 줄만 (다른 IE 안의 SSID 와 구분)
_BSS_HEAD_RE = re.compile(r'^BSS ([0-9a-f:]{17})\(on [^)]*\)(.*)$', re.MULTILINE)
_SCAN_SSID_RE = re.compile(r'^\tSSID: ?(.*)$', re.MULTILINE)
_SCAN_SIGNAL_RE = re.compile(r'^\tsignal: (-?\d+(?:\.\d+)?) dBm', re.MULTILINE)
_SCAN_FREQ_RE = re.compile(r'^\tfreq: (\d+(?:\.\d+)?)', re.MULTILINE)
_SEEN_BOOT_RE = re.compile(r'^\tlast seen: (\d+(?:\.\d+)?)s \[boottime\]', re.MULTILINE)
_SEEN_AGO_RE = re.compile(r'^\tlast seen: (\d+) ms ago', re.MULTILINE)
_HEX_ESC_RE = re.compile(r'\\x([0-9a-fA-F]{2})')


class LinkReading(NamedTuple):
    detected: bool          # target_ssid 에 붙어 있고 signal 을 읽었으면 True
    rssi_dbm: Optional[int]  # detected 가 False 면 None
    ssid: Optional[str]     # 지금 붙어 있는 SSID (없으면 None)


class ScanBss(NamedTuple):
    bssid: str
    ssid: str                      # UTF-8 로 되돌린 SSID (숨은 SSID 는 '')
    freq_mhz: int
    signal_dbm: float
    seen_boottime: Optional[float]  # 마지막으로 들은 시각 [s, CLOCK_BOOTTIME]
    age_ms: Optional[int]           # iw 가 출력한 시점 기준 몇 ms 전에 들었는지
    associated: bool                # 노트북이 지금 붙어 있는 AP


class ScanResult(NamedTuple):
    ok: bool                 # iw 가 성공했는지 (False 면 bss 는 비어 있고 error 에 이유)
    error: str
    bss: List[ScanBss]
    start_boottime: float    # iw 실행 직전 [s, CLOCK_BOOTTIME]
    end_boottime: float      # iw 끝난 직후
    full: bool               # 전체 대역 스캔이면 True

    @property
    def duration_s(self) -> float:
        return self.end_boottime - self.start_boottime


def iw_available() -> bool:
    return shutil.which('iw') is not None


def _boottime() -> float:
    return time.clock_gettime(time.CLOCK_BOOTTIME)


# ---------------------------------------------------------------- link 방식

def parse_iw_link(text: str, target_ssid: str) -> LinkReading:
    """`iw dev <iface> link` 출력에서 SSID 와 signal 을 꺼낸다. target_ssid 가 '' 이면 붙어 있는 AP 아무거나."""
    if 'Not connected' in text:
        return LinkReading(False, None, None)
    ssid_m = _SSID_RE.search(text)
    sig_m = _SIGNAL_RE.search(text)
    ssid = decode_iw_ssid(ssid_m.group(1).strip()) if ssid_m else None
    if sig_m is None or ssid is None or (target_ssid and ssid != target_ssid):
        return LinkReading(False, None, ssid)
    return LinkReading(True, int(sig_m.group(1)), ssid)


def read_iw_link(iface: str, target_ssid: str, timeout: float = 2.0) -> LinkReading:
    """iw 를 실행해 한 번 읽는다. 실행 실패도 미검출로 돌려준다."""
    try:
        out = subprocess.run(
            ['iw', 'dev', iface, 'link'],
            capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return LinkReading(False, None, None)
    if out.returncode != 0:
        return LinkReading(False, None, None)
    return parse_iw_link(out.stdout, target_ssid)


# ---------------------------------------------------------------- scan 방식

def decode_iw_ssid(text: str) -> str:
    """iw 가 `\\xNN` 으로 바꿔 쓴 바이트(한글, ’, 앞뒤 공백, 백슬래시)를 UTF-8 문자열로 되돌린다.

    예: 'csh\\xec\\x9d\\x98 iPhone' → 'csh의 iPhone'
    """
    if '\\x' not in text:
        return text
    raw = bytearray()
    pos = 0
    for m in _HEX_ESC_RE.finditer(text):
        raw += text[pos:m.start()].encode('utf-8')
        raw.append(int(m.group(1), 16))
        pos = m.end()
    raw += text[pos:].encode('utf-8')
    return raw.decode('utf-8', errors='replace')


def parse_iw_scan(text: str) -> List[ScanBss]:
    """`iw dev <iface> scan` 출력을 BSS 목록으로. signal·freq 가 없는 블록은 버린다."""
    heads = list(_BSS_HEAD_RE.finditer(text))
    out = []
    for i, h in enumerate(heads):
        block = text[h.end():heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        sig = _SCAN_SIGNAL_RE.search(block)
        freq = _SCAN_FREQ_RE.search(block)
        if sig is None or freq is None:
            continue
        ssid = _SCAN_SSID_RE.search(block)
        boot = _SEEN_BOOT_RE.search(block)
        ago = _SEEN_AGO_RE.search(block)
        out.append(ScanBss(
            bssid=h.group(1),
            ssid=decode_iw_ssid(ssid.group(1)) if ssid else '',
            freq_mhz=int(round(float(freq.group(1)))),
            signal_dbm=float(sig.group(1)),
            seen_boottime=float(boot.group(1)) if boot else None,
            age_ms=int(ago.group(1)) if ago else None,
            associated='associated' in h.group(2)))
    return out


def fresh_bss(bss: Sequence[ScanBss], start_boottime: float, duration_s: float,
              slack_s: float = 0.05) -> List[ScanBss]:
    """이번 스캔(시작 시각 이후)에 들은 BSS 만. boottime 이 없으면 `ms ago` 로 판단."""
    out = []
    for b in bss:
        if b.seen_boottime is not None:
            fresh = b.seen_boottime >= start_boottime - slack_s
        elif b.age_ms is not None:
            fresh = b.age_ms <= (duration_s + slack_s) * 1000.0
        else:
            fresh = False
        if fresh:
            out.append(b)
    return out


def match_ssid(bss: Sequence[ScanBss], ssid: str = '', pattern: str = '') -> List[ScanBss]:
    """ssid 를 주면 정확히 같은 것, 아니면 pattern 이 (대소문자 무시) 들어간 것. 센 순서로."""
    if ssid:
        hits = [b for b in bss if b.ssid == ssid]
    elif pattern:
        hits = [b for b in bss if pattern.lower() in b.ssid.lower()]
    else:
        hits = []
    return sorted(hits, key=lambda b: b.signal_dbm, reverse=True)


def run_iw_scan(iface: str, freqs: Optional[Sequence[int]] = None,
                timeout: float = 10.0) -> ScanResult:
    """iw scan 을 한 번 실행한다. freqs 가 비면 전체 대역 (iwlwifi 에서 약 5 s)."""
    cmd = ['iw', 'dev', iface, 'scan']
    if freqs:
        cmd += ['freq'] + [str(int(f)) for f in freqs]
    t0 = _boottime()
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return ScanResult(False, f'시간 초과 ({timeout:.0f} s)', [], t0, _boottime(), not freqs)
    except OSError as e:
        return ScanResult(False, str(e), [], t0, _boottime(), not freqs)
    t1 = _boottime()
    if out.returncode != 0:
        err = (out.stderr or out.stdout).strip().splitlines()
        return ScanResult(False, err[-1] if err else f'종료 코드 {out.returncode}', [], t0, t1, not freqs)
    return ScanResult(True, '', parse_iw_scan(out.stdout), t0, t1, not freqs)


def is_permission_error(error: str) -> bool:
    return 'Operation not permitted' in error or '(-1)' in error


class TrackResult(NamedTuple):
    target: Optional[ScanBss]   # 이번 스캔에서 들은 대상 (없으면 None → 미검출)
    candidates: List[ScanBss]   # pattern 이 들어간 AP (로그용, 센 순서)
    events: List[str]           # 상태 변화 (로그용)


class HotspotTracker:
    """어느 채널을 스캔할지 정하고, 스캔 결과에서 대상 핫스팟을 고른다.

    - ssid 를 주면 그 SSID 만 잰다. 비우면 SSID 에 pattern 이 들어간 AP 중 처음 가장 센 것으로 고정한다.
    - 대상 채널을 모르면 전체 스캔, 알면 그 채널만 스캔한다 (5 GHz 약 0.06 s, 2.4 GHz 약 0.15 s).
    - rescan_after_miss 번 연속 못 찾으면 채널이 바뀌었을 수 있으므로 full_scan_interval 초마다 전체 스캔을 섞는다.
    """

    def __init__(self, ssid: str = '', pattern: str = 'iPhone',
                 rescan_after_miss: int = 3, full_scan_interval: float = 10.0):
        self.manual = bool(ssid)
        self.ssid = ssid
        self.pattern = pattern
        self.rescan_after_miss = max(1, int(rescan_after_miss))
        self.full_scan_interval = full_scan_interval
        self.freq: Optional[int] = None
        self.misses = 0
        self.last_full = -math.inf

    def next_freqs(self, now: float) -> Optional[List[int]]:
        """이번에 스캔할 주파수. None 이면 전체 대역."""
        if self.freq is None:
            return None
        if self.misses >= self.rescan_after_miss and now - self.last_full >= self.full_scan_interval:
            return None
        return [self.freq]

    def update(self, fresh: Sequence[ScanBss], full: bool, now: float) -> TrackResult:
        events = []
        if full:
            self.last_full = now
        candidates = match_ssid(fresh, pattern=self.pattern) if self.pattern else []
        if not self.ssid:
            if not candidates:
                return TrackResult(None, candidates, events)
            self.ssid = candidates[0].ssid
            events.append(f"자동 선택: SSID 에 '{self.pattern}' 가 들어간 AP 중 가장 센 "
                          f"'{self.ssid}' 로 고정")
        hits = match_ssid(fresh, ssid=self.ssid)
        if not hits:
            self.misses += 1
            if self.misses == self.rescan_after_miss:
                self.last_full = -math.inf     # 첫 재탐색은 바로
                events.append(f'{self.misses} 회 연속 미검출 → {self.full_scan_interval:.0f} s 마다 '
                              '전체 대역 스캔으로 채널 재탐색')
            return TrackResult(None, candidates, events)
        target = hits[0]
        if self.freq is None:
            events.append(f'채널 고정: {target.freq_mhz} MHz (이후 이 채널만 스캔)')
        elif target.freq_mhz != self.freq:
            events.append(f'채널 바뀜: {self.freq} → {target.freq_mhz} MHz')
        if self.misses >= self.rescan_after_miss:
            events.append(f'다시 검출 ({self.misses} 회 미검출 뒤)')
        self.freq = target.freq_mhz
        self.misses = 0
        return TrackResult(target, candidates, events)

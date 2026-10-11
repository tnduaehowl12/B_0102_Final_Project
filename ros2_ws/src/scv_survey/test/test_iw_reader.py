from scv_survey.iw_reader import parse_iw_link

CONNECTED = """Connected to aa:bb:cc:dd:ee:ff (on wlo1)
\tSSID: turtle08
\tfreq: 5180
\tRX: 123456 bytes (789 packets)
\tTX: 23456 bytes (123 packets)
\tsignal: -41 dBm
\trx bitrate: 866.7 MBit/s VHT-MCS 9 80MHz short GI VHT-NSS 2
\ttx bitrate: 780.0 MBit/s VHT-MCS 8 80MHz short GI VHT-NSS 2
"""


def test_connected_target():
    r = parse_iw_link(CONNECTED, 'turtle08')
    assert r.detected and r.rssi_dbm == -41 and r.ssid == 'turtle08'


def test_other_ssid_is_not_detected():
    r = parse_iw_link(CONNECTED.replace('turtle08', 'office'), 'turtle08')
    assert not r.detected and r.rssi_dbm is None and r.ssid == 'office'


def test_not_connected():
    r = parse_iw_link('Not connected.\n', 'turtle08')
    assert not r.detected and r.rssi_dbm is None and r.ssid is None


def test_missing_signal_line():
    text = '\n'.join(line for line in CONNECTED.splitlines() if 'signal:' not in line)
    assert not parse_iw_link(text, 'turtle08').detected


def test_ssid_with_space():
    r = parse_iw_link(CONNECTED.replace('turtle08', 'my wifi'), 'my wifi')
    assert r.detected and r.rssi_dbm == -41


# ---------------------------------------------------------------- scan 방식
# 10/11 노트북에서 실제로 본 `iw dev wlo1 scan` 출력 형식을 줄인 것.
# 스캔 시작 boottime 은 1900.0 s, 걸린 시간 0.06 s 로 본다 (1900.0 보다 먼저 들은 BSS 는 캐시에 남은 것).
from scv_survey.iw_reader import (  # noqa: E402
    HotspotTracker, decode_iw_ssid, fresh_bss, is_permission_error, match_ssid, parse_iw_scan)

SCAN = """BSS b2:38:6c:49:ed:18(on wlo1) -- associated
\tlast seen: 1899.400s [boottime]
\tTSF: 18997455053452276 usec (219877d, 22:50:53)
\tfreq: 5785.0
\tbeacon interval: 100 TUs
\tsignal: -37.00 dBm
\tlast seen: 640 ms ago
\tInformation elements from Probe Response frame:
\tSSID: turtle08
BSS 3a:a3:35:69:74:1b(on wlo1)
\tlast seen: 1900.020s [boottime]
\tfreq: 5745.0
\tsignal: -54.00 dBm
\tlast seen: 20 ms ago
\tInformation elements from Probe Response frame:
\tSSID: iPhone
\tRSN:\t * Version: 1
BSS 6e:11:22:33:44:55(on wlo1)
\tlast seen: 1900.030s [boottime]
\tfreq: 5745.0
\tsignal: -41.00 dBm
\tlast seen: 10 ms ago
\tSSID: csh\\xec\\x9d\\x98 iPhone
BSS 66:af:97:89:c7:5f(on wlo1)
\tlast seen: 1900.025s [boottime]
\tfreq: 5745.0
\tsignal: -65.00 dBm
\tlast seen: 15 ms ago
\tUnknown IE (0):
BSS 5a:86:94:ca:b1:6c(on wlo1)
\tlast seen: 1880.000s [boottime]
\tfreq: 5520.0
\tsignal: -86.00 dBm
\tlast seen: 20040 ms ago
\tSSID: \\xec\\x84\\x9c\\xec\\x9a\\xb8\\xeb\\xb2\\x95\\xec\\x9d\\xb8_5G
BSS 7a:00:00:00:00:01(on wlo1)
\tlast seen: 1885.000s [boottime]
\tfreq: 2437.0
\tsignal: -30.00 dBm
\tlast seen: 15040 ms ago
\tSSID: Kim\\xe2\\x80\\x99s iPhone
"""
T0, DUR = 1900.0, 0.06


def test_decode_iw_ssid():
    assert decode_iw_ssid('csh\\xec\\x9d\\x98 iPhone') == 'csh의 iPhone'
    assert decode_iw_ssid('Kim\\xe2\\x80\\x99s iPhone') == 'Kim’s iPhone'
    assert decode_iw_ssid('\\x20lead space') == ' lead space'   # 앞뒤 공백·백슬래시도 \\x 로 나온다
    assert decode_iw_ssid('a\\x5cb') == 'a\\b'
    assert decode_iw_ssid('turtle08') == 'turtle08'


def test_link_korean_ssid_and_any():
    text = CONNECTED.replace('turtle08', 'csh\\xec\\x9d\\x98 iPhone')
    assert parse_iw_link(text, 'csh의 iPhone').detected
    r = parse_iw_link(CONNECTED, '')              # 비우면 붙어 있는 AP 아무거나
    assert r.detected and r.ssid == 'turtle08'


def test_parse_iw_scan_fields():
    bss = parse_iw_scan(SCAN)
    assert len(bss) == 6
    t = bss[0]
    assert (t.bssid, t.ssid, t.freq_mhz, t.signal_dbm, t.associated) == \
        ('b2:38:6c:49:ed:18', 'turtle08', 5785, -37.0, True)
    assert t.seen_boottime == 1899.4 and t.age_ms == 640
    assert bss[2].ssid == 'csh의 iPhone' and not bss[2].associated
    assert bss[3].ssid == ''                       # 숨은 SSID
    assert bss[4].ssid == '서울법인_5G'


def test_parse_iw_scan_drops_block_without_signal():
    text = SCAN.replace('\tsignal: -54.00 dBm\n', '')
    assert 'iPhone' not in [b.ssid for b in parse_iw_scan(text)]
    assert parse_iw_scan('') == []


def test_fresh_bss_by_boottime():
    fresh = fresh_bss(parse_iw_scan(SCAN), T0, DUR)
    assert {b.ssid for b in fresh} == {'iPhone', 'csh의 iPhone', ''}   # turtle08·캐시 항목 제외


def test_fresh_bss_by_ms_ago_when_no_boottime():
    text = '\n'.join(ln for ln in SCAN.splitlines() if 'boottime' not in ln)
    fresh = fresh_bss(parse_iw_scan(text), T0, DUR)
    assert {b.ssid for b in fresh} == {'iPhone', 'csh의 iPhone', ''}


def test_match_ssid_exact_and_pattern():
    bss = parse_iw_scan(SCAN)
    assert [b.bssid for b in match_ssid(bss, ssid='csh의 iPhone')] == ['6e:11:22:33:44:55']
    assert match_ssid(bss, ssid='csh의 iphone') == []          # 직접 입력은 정확히 같아야
    pat = match_ssid(bss, pattern='iphone')                     # pattern 은 대소문자 무시, 센 순서
    assert [b.ssid for b in pat] == ['Kim’s iPhone', 'csh의 iPhone', 'iPhone']


def test_permission_error():
    assert is_permission_error('command failed: Operation not permitted (-1)')
    assert not is_permission_error('command failed: Device or resource busy (-16)')


def _fresh(text=SCAN):
    return fresh_bss(parse_iw_scan(text), T0, DUR)


def test_tracker_manual_ssid_locks_channel():
    tr = HotspotTracker(ssid='csh의 iPhone')
    assert tr.next_freqs(0.0) is None                            # 채널 모름 → 전체 스캔
    r = tr.update(_fresh(), full=True, now=0.0)
    assert r.target.bssid == '6e:11:22:33:44:55' and r.target.signal_dbm == -41.0
    assert tr.next_freqs(1.0) == [5745]                          # 이후 그 채널만
    assert any('채널 고정' in e for e in r.events)


def test_tracker_manual_ignores_stronger_other_iphone():
    tr = HotspotTracker(ssid='iPhone')
    r = tr.update(_fresh(), full=True, now=0.0)
    assert r.target.ssid == 'iPhone' and r.target.signal_dbm == -54.0


def test_tracker_auto_locks_strongest_and_keeps_it():
    tr = HotspotTracker(ssid='', pattern='iPhone')
    r = tr.update(_fresh(), full=True, now=0.0)
    assert tr.ssid == 'csh의 iPhone' and r.target.ssid == 'csh의 iPhone'
    assert any('자동 선택' in e for e in r.events)
    # 다른 iPhone 이 더 세져도 고정한 SSID 를 계속 잰다
    stronger = _fresh(SCAN.replace('-54.00 dBm', '-20.00 dBm'))
    assert tr.update(stronger, full=False, now=1.0).target.ssid == 'csh의 iPhone'


def test_tracker_auto_without_candidate_is_miss():
    tr = HotspotTracker(ssid='', pattern='Galaxy')
    r = tr.update(_fresh(), full=True, now=0.0)
    assert r.target is None and tr.ssid == '' and tr.next_freqs(1.0) is None


def test_tracker_off_then_on():
    """핫스팟을 끄면 1 Hz 로 미검출, 3 회 뒤부터 10 s 마다 전체 스캔, 켜면 다시 검출."""
    tr = HotspotTracker(ssid='csh의 iPhone', rescan_after_miss=3, full_scan_interval=10.0)
    tr.update(_fresh(), full=True, now=0.0)
    off = _fresh(SCAN.replace('csh\\xec\\x9d\\x98 iPhone', 'other'))
    plan = []
    for t in range(1, 16):
        freqs = tr.next_freqs(float(t))
        plan.append('full' if freqs is None else freqs[0])
        r = tr.update(off, full=freqs is None, now=float(t))
        assert r.target is None
    # 1–3 s 는 그 채널, 4 s 에 전체(마지막 전체는 0 s 라 간격 충족), 다음 전체는 14 s
    assert plan[:4] == [5745, 5745, 5745, 'full']
    assert plan[4:13] == [5745] * 9 and plan[13] == 'full'
    # 다른 채널(2412)로 다시 켜짐 → 전체 스캔에서 찾고 채널을 바꿔 고정
    on = _fresh(SCAN.replace('\tfreq: 5745.0\n\tsignal: -41.00', '\tfreq: 2412.0\n\tsignal: -41.00'))
    r = tr.update(on, full=True, now=24.0)
    assert r.target is not None and tr.misses == 0 and tr.next_freqs(25.0) == [2412]
    assert any('채널 바뀜' in e for e in r.events) and any('다시 검출' in e for e in r.events)

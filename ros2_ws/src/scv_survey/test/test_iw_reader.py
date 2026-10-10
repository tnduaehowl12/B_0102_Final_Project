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

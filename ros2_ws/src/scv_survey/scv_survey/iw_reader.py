"""`iw dev <iface> link` 로 지금 붙어 있는 AP 의 RSSI 를 읽는다 (ROS 와 무관).

스캔(`iw scan`)이 아니라 접속 중인 링크 정보만 읽으므로 root 가 필요 없고 통신도 끊지 않는다.
"""

import re
import shutil
import subprocess
from typing import NamedTuple, Optional

_SSID_RE = re.compile(r'^\s*SSID:\s*(.*)$', re.MULTILINE)
_SIGNAL_RE = re.compile(r'^\s*signal:\s*(-?\d+)\s*dBm', re.MULTILINE)


class LinkReading(NamedTuple):
    detected: bool          # target_ssid 에 붙어 있고 signal 을 읽었으면 True
    rssi_dbm: Optional[int]  # detected 가 False 면 None
    ssid: Optional[str]     # 지금 붙어 있는 SSID (없으면 None)


def iw_available() -> bool:
    return shutil.which('iw') is not None


def parse_iw_link(text: str, target_ssid: str) -> LinkReading:
    """`iw dev <iface> link` 출력에서 SSID 와 signal 을 꺼낸다."""
    if 'Not connected' in text:
        return LinkReading(False, None, None)
    ssid_m = _SSID_RE.search(text)
    sig_m = _SIGNAL_RE.search(text)
    ssid = ssid_m.group(1).strip() if ssid_m else None
    if ssid != target_ssid or sig_m is None:
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

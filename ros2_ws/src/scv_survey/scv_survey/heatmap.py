"""RSSI 샘플을 격자 칸으로 모으고 색을 정한다 (ROS 와 무관, pytest 대상).

- 칸 번호는 지도 원점(origin) 기준: i = floor((x - ox) / cell), j = floor((y - oy) / cell)
- 칸 대표값은 검출된 RSSI 의 중앙값. 미검출 샘플은 통계에 넣지 않고 따로 센다
- (robot_id, seq) 가 같은 샘플은 한 번만, pose_ok 가 False 인 샘플은 버린다
"""

import colorsys
import math
import statistics
from dataclasses import dataclass, field
from typing import Dict, List, NamedTuple, Optional, Tuple

Color = Tuple[float, float, float]

# 신호 세기 → 색 (NetSpot 식 그라데이션): 강할수록 빨강, 약할수록(음영) 파랑
#   STRONG_DBM 이상 빨강 → 주황 → 노랑 → 초록 → 하늘 → WEAK_DBM 이하 파랑
STRONG_DBM = -35
WEAK_DBM = -75
MISS_COLOR: Color = (0.4, 0.4, 0.4)    # 회색 (미검출 — 파랑(약함)과 구분)


class Sample(NamedTuple):
    robot_id: str
    seq: int
    x: float
    y: float
    pose_ok: bool
    detected: bool
    rssi_dbm: int


def rssi_to_color(rssi: float, strong: float = STRONG_DBM, weak: float = WEAK_DBM) -> Color:
    """색상환 파랑(240°) → 빨강(0°) 을 RSSI 에 비례해 고른다. 범위 밖은 양 끝 색"""
    t = (rssi - weak) / (strong - weak)
    t = min(1.0, max(0.0, t))
    return colorsys.hsv_to_rgb((1.0 - t) * 2.0 / 3.0, 1.0, 1.0)


def cell_index(x: float, y: float, ox: float, oy: float, cell: float) -> Tuple[int, int]:
    return (math.floor((x - ox) / cell), math.floor((y - oy) / cell))


def cell_center(i: int, j: int, ox: float, oy: float, cell: float) -> Tuple[float, float]:
    return (ox + (i + 0.5) * cell, oy + (j + 0.5) * cell)


@dataclass
class CellStats:
    rssi: List[int] = field(default_factory=list)  # 검출된 값만
    n_missed: int = 0

    @property
    def n_detected(self) -> int:
        return len(self.rssi)

    @property
    def n_total(self) -> int:
        return self.n_detected + self.n_missed

    @property
    def median(self) -> Optional[float]:
        return statistics.median(self.rssi) if self.rssi else None

    @property
    def miss_ratio(self) -> float:
        return self.n_missed / self.n_total if self.n_total else 0.0


def pose_usable(age_s: Optional[float], cov_xy: Optional[float],
                max_age: float = 0.5, max_cov: float = 0.25,
                lag_s: Optional[float] = None) -> Tuple[bool, str]:
    """TF 로 얻은 위치를 지도에 써도 되는지. (쓸 수 있는지, 안 되면 이유)

    age_s: 측정 시각과 붙인 TF 시각의 차 [s] (None 이면 TF 를 못 찾음)
    lag_s: 지금 시각 - 가장 최근 TF 시각 [s]. 통신 지연이거나 노트북·로봇 시계 차.
           측정 시각의 TF 를 찾았어도(age 0) 시계가 어긋나 있으면 엉뚱한 과거 위치일 수 있어 따로 본다
    max_age <= 0 이면 age·lag 검사를 하지 않는다
    cov_xy: AMCL 공분산 xx + yy [m^2] (None 이면 amcl_pose 를 아직 못 받음 → 검사 안 함)
    """
    if age_s is None:
        return False, 'TF 없음'
    if max_age > 0 and lag_s is not None and abs(lag_s) > max_age:
        return False, f'최근 TF 가 지금보다 {lag_s:+.2f} s (통신 지연 또는 노트북·로봇 시계 차)'
    if max_age > 0 and abs(age_s) > max_age:
        return False, f'TF 시각 차 {age_s:.2f} s > {max_age} s'
    if cov_xy is not None and cov_xy > max_cov:
        return False, f'AMCL 공분산 {cov_xy:.3f} > {max_cov} m^2'
    return True, ''


def cell_color(stats: CellStats, miss_ratio_thresh: float = 0.5,
               strong: float = STRONG_DBM, weak: float = WEAK_DBM) -> Color:
    if stats.n_detected == 0 or stats.miss_ratio >= miss_ratio_thresh:
        return MISS_COLOR
    return rssi_to_color(stats.median, strong, weak)


class SurveyGrid:
    """받은 샘플을 보관하고, 요청할 때 칸별 통계를 계산한다.

    원점·범위는 /map 을 받은 뒤 바뀔 수 있어서 샘플 자체를 보관하고 칸은 매번 다시 계산한다.
    """

    def __init__(self, cell_size: float = 0.5, origin: Tuple[float, float] = (0.0, 0.0)):
        self.cell_size = cell_size
        self.origin = origin
        self.bounds: Optional[Tuple[float, float, float, float]] = None  # xmin, ymin, xmax, ymax
        self._samples: List[Sample] = []
        self._seen = set()

    def set_map(self, ox: float, oy: float, width_m: float, height_m: float) -> None:
        self.origin = (ox, oy)
        self.bounds = (ox, oy, ox + width_m, oy + height_m)

    def in_bounds(self, x: float, y: float) -> bool:
        if self.bounds is None:
            return True
        xmin, ymin, xmax, ymax = self.bounds
        return xmin <= x < xmax and ymin <= y < ymax

    def add(self, s: Sample) -> bool:
        """지도에 쓸 샘플이면 보관하고 True. 중복·pose_ok False 는 False."""
        key = (s.robot_id, s.seq)
        if key in self._seen:
            return False
        self._seen.add(key)
        if not s.pose_ok:
            return False
        self._samples.append(s)
        return True

    @property
    def samples(self) -> List[Sample]:
        """지도에 쓴 샘플 (범위 밖 포함)"""
        return list(self._samples)

    def cells(self) -> Dict[Tuple[int, int], CellStats]:
        ox, oy = self.origin
        out: Dict[Tuple[int, int], CellStats] = {}
        for s in self._samples:
            if not self.in_bounds(s.x, s.y):
                continue
            st = out.setdefault(cell_index(s.x, s.y, ox, oy, self.cell_size), CellStats())
            if s.detected:
                st.rssi.append(s.rssi_dbm)
            else:
                st.n_missed += 1
        return out

    def center(self, idx: Tuple[int, int]) -> Tuple[float, float]:
        return cell_center(idx[0], idx[1], self.origin[0], self.origin[1], self.cell_size)

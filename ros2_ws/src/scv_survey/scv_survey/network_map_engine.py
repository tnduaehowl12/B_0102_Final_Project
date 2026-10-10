"""network_map_engine (히트맵 부분): {ns}/survey/sample 을 0.5 m 칸으로 모아 RViz 용 MarkerArray 로 보낸다.

- map_topic(기본 /map, 로봇 시험은 /robot4/map)을 받으면 지도 원점에 칸을 맞추고, 지도 밖 샘플은 버린다
- /survey/heatmap: 칸 색(TRIANGLE_LIST) + 칸마다 중앙값 글자(TEXT_VIEW_FACING)
  + 샘플을 잰 자리 검은 점(POINTS, 최근 max_points 개) — 로봇이 지나간 자리에 찍혔는지 확인용
  + 지도 아래 범례 막대 (파랑 rssi_weak ~ 빨강 rssi_strong)
- 색: 강할수록 빨강 → 주황 → 노랑 → 초록 → 하늘 → 약할수록(음영) 파랑, 미검출은 회색
  CUBE_LIST 는 RViz 조명 때문에 색이 절반쯤 어두워져서, 조명을 받지 않는 TRIANGLE_LIST 로 칸을 그린다
- csv_path 를 주면 지도에 쓴 샘플을 CSV 로 남긴다 (일지 근거)
"""

import csv
import os

import rclpy
from geometry_msgs.msg import Point
from nav_msgs.msg import OccupancyGrid
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import ColorRGBA
from visualization_msgs.msg import Marker, MarkerArray

from scv_msgs.msg import NetSample
from scv_survey.heatmap import (
    MISS_COLOR, STRONG_DBM, WEAK_DBM, Sample, SurveyGrid, cell_color, rssi_to_color)
from scv_survey.manual_tagger import SAMPLE_QOS

def add_square(m: Marker, cx: float, cy: float, half_x: float, half_y: float,
               color: ColorRGBA, z: float = 0.01) -> None:
    """TRIANGLE_LIST 마커에 (cx, cy) 중심 사각형 하나(삼각형 2개)를 더한다"""
    x0, x1, y0, y1 = cx - half_x, cx + half_x, cy - half_y, cy + half_y
    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y0), (x1, y1), (x0, y1)):
        m.points.append(Point(x=x, y=y, z=z))
        m.colors.append(color)


def flat_marker(header, ns: str, mid: int, mtype: int) -> Marker:
    m = Marker()
    m.header = header
    m.ns = ns
    m.id = mid
    m.type = mtype
    m.action = Marker.ADD
    m.pose.orientation.w = 1.0
    m.scale.x = m.scale.y = m.scale.z = 1.0
    # RViz 는 꼭짓점 색에 이 색(알파 포함)을 곱한다. 기본값(알파 0)이면 반투명 칸이 사라진다
    m.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
    return m


LATCHED = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    depth=1,
)


class NetworkMapEngine(Node):
    def __init__(self):
        super().__init__('network_map_engine')
        topics = self.declare_parameter('sample_topics', ['/laptop/survey/sample']).value
        cell = self.declare_parameter('cell_size', 0.5).value
        self.miss_thresh = self.declare_parameter('miss_ratio_thresh', 0.5).value
        self.alpha = self.declare_parameter('alpha', 0.7).value
        self.min_full = self.declare_parameter('min_samples_full_alpha', 2).value
        csv_path = self.declare_parameter('csv_path', '').value
        map_topic = self.declare_parameter('map_topic', '/map').value
        self.show_points = self.declare_parameter('show_points', True).value
        self.max_points = self.declare_parameter('max_points', 2000).value
        self.strong = float(self.declare_parameter('rssi_strong', float(STRONG_DBM)).value)
        self.weak = float(self.declare_parameter('rssi_weak', float(WEAK_DBM)).value)

        self.grid = SurveyGrid(cell_size=cell)
        self.dirty = True
        self.csv = None
        if csv_path:
            path = os.path.expanduser(csv_path)
            os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
            # 빈 파일도 새 파일로 본다 (header 를 쓰기 전에 종료된 경우)
            new = not os.path.exists(path) or os.path.getsize(path) == 0
            self.csv_file = open(path, 'a', newline='')
            self.csv = csv.writer(self.csv_file)
            if new:
                self.csv.writerow(['stamp', 'robot_id', 'seq', 'run_id', 'x', 'y', 'detected', 'rssi_dbm'])
                self.csv_file.flush()   # 샘플이 오기 전에 종료돼도 header 는 남게
            self.get_logger().info(f'CSV 기록: {path}')

        self.pub = self.create_publisher(MarkerArray, '/survey/heatmap', LATCHED)
        self.create_subscription(OccupancyGrid, map_topic, self.on_map, LATCHED)
        for t in topics:
            self.create_subscription(NetSample, t, self.on_sample, SAMPLE_QOS)
        self.create_timer(1.0, self.on_timer)
        self.get_logger().info(f'구독: {list(topics)} + {map_topic}, 칸 {cell} m, '
                               f'색 {self.strong:.0f} dBm 빨강 ~ {self.weak:.0f} dBm 파랑')

    def on_map(self, m: OccupancyGrid):
        o = m.info.origin.position
        w = m.info.width * m.info.resolution
        h = m.info.height * m.info.resolution
        self.grid.set_map(o.x, o.y, w, h)
        self.dirty = True
        self.get_logger().info(f'지도 받음: 원점 ({o.x:.3f}, {o.y:.3f}), {w:.2f} x {h:.2f} m')

    def on_sample(self, m: NetSample):
        s = Sample(m.robot_id, m.seq, m.x, m.y, m.pose_ok, m.detected, m.rssi_dbm)
        if not self.grid.add(s):
            return
        if not self.grid.in_bounds(s.x, s.y):
            self.get_logger().warn(f'지도 밖 샘플 ({s.x:.2f}, {s.y:.2f}) — 표시하지 않음',
                                   throttle_duration_sec=5.0)
        self.dirty = True
        if self.csv:
            t = m.stamp.sec + m.stamp.nanosec * 1e-9
            self.csv.writerow([f'{t:.3f}', m.robot_id, m.seq, m.run_id,
                               f'{m.x:.3f}', f'{m.y:.3f}', m.detected,
                               m.rssi_dbm if m.detected else ''])
            self.csv_file.flush()

    def on_timer(self):
        if not self.dirty:
            return
        self.dirty = False
        self.pub.publish(self.build_markers())

    def build_markers(self) -> MarkerArray:
        stamp = self.get_clock().now().to_msg()
        cell = self.grid.cell_size
        out = MarkerArray()

        clear = Marker()
        clear.action = Marker.DELETEALL
        out.markers.append(clear)

        header = Marker().header
        header.frame_id = 'map'
        header.stamp = stamp
        cells = flat_marker(header, 'cells', 0, Marker.TRIANGLE_LIST)
        half = cell * 0.95 / 2

        for k, (idx, st) in enumerate(sorted(self.grid.cells().items())):
            cx, cy = self.grid.center(idx)
            r, g, b = cell_color(st, self.miss_thresh, self.strong, self.weak)
            a = self.alpha if st.n_total >= self.min_full else self.alpha * 0.5
            add_square(cells, cx, cy, half, half, ColorRGBA(r=r, g=g, b=b, a=a))

            text = Marker()
            text.header = header
            text.ns = 'labels'
            text.id = k
            text.type = Marker.TEXT_VIEW_FACING
            text.action = Marker.ADD
            text.pose.position = Point(x=cx, y=cy, z=0.1)
            text.pose.orientation.w = 1.0
            text.scale.z = cell * 0.3
            text.color = ColorRGBA(r=0.0, g=0.0, b=0.0, a=1.0)
            med = st.median
            text.text = f'{med:.0f}' if med is not None else 'X'
            out.markers.append(text)

        if cells.points:
            out.markers.insert(1, cells)
        if self.show_points:
            out.markers.append(self.build_points(header))
        out.markers.extend(self.build_legend(header))
        return out

    def build_points(self, header) -> Marker:
        # 칸과 같은 색이면 칸 위에서 안 보이므로 검은 점 (미검출 샘플은 회색 점)
        dots = flat_marker(header, 'points', 0, Marker.POINTS)
        dots.scale.x = dots.scale.y = 0.05
        for s in self.grid.samples[-self.max_points:]:
            if not self.grid.in_bounds(s.x, s.y):
                continue
            r, g, b = (0.0, 0.0, 0.0) if s.detected else MISS_COLOR
            dots.points.append(Point(x=s.x, y=s.y, z=0.05))
            dots.colors.append(ColorRGBA(r=r, g=g, b=b, a=0.8))
        if not dots.points:
            dots.action = Marker.DELETE
        return dots

    def build_legend(self, header, steps: int = 20, width: float = 2.0):
        """지도 왼쪽 아래 밖에 파랑(약함) → 빨강(강함) 막대와 양 끝 dBm 글자"""
        if self.grid.bounds is None:
            return []
        xmin, ymin, _, _ = self.grid.bounds
        y = ymin - 0.3
        seg = width / steps

        bar = flat_marker(header, 'legend', 0, Marker.TRIANGLE_LIST)
        for k in range(steps):
            rssi = self.weak + (self.strong - self.weak) * (k + 0.5) / steps
            r, g, b = rssi_to_color(rssi, self.strong, self.weak)
            add_square(bar, xmin + (k + 0.5) * seg, y, seg / 2, 0.1, ColorRGBA(r=r, g=g, b=b, a=1.0))

        out = [bar]
        for i, (x, label) in enumerate([(xmin, f'{self.weak:.0f}'),
                                        (xmin + width, f'{self.strong:.0f} dBm')]):
            t = Marker()
            t.header = header
            t.ns = 'legend'
            t.id = i + 1
            t.type = Marker.TEXT_VIEW_FACING
            t.action = Marker.ADD
            t.pose.position = Point(x=x, y=y - 0.25, z=0.1)
            t.pose.orientation.w = 1.0
            t.scale.z = 0.18
            t.color = ColorRGBA(r=1.0, g=1.0, b=1.0, a=1.0)
            t.text = label
            out.append(t)
        return out

    def destroy_node(self):
        if self.csv:
            self.csv_file.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = NetworkMapEngine()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()

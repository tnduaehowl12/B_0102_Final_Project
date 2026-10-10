"""노트북 시험용 survey_buffer 대체: NetRaw 에 위치를 붙여 NetSample 로 보낸다.

pose_source 로 위치를 어디서 얻을지 고른다.

manual (노트북만 들고 잴 때)
- 시작하면 초기위치(init_x, init_y, init_yaw — 기본은 map 원점 = SLAM 시작점)에서 samples_per_point 개를 잰다
- RViz "Publish Point"(/clicked_point) 나 "2D Pose Estimate"(/initialpose) 로 새 위치를 주면 그 자리에서 다시 잰다
- 위치를 준 뒤 들어온 NetRaw samples_per_point 개만 pose_ok=True. 나머지(옮기는 중)는 pose_ok=False

tf (노트북을 TurtleBot4 위에 올리고 teleop 으로 움직이며 잴 때)
- NetRaw 마다 로봇 TF map → base_link 를 찾아 위치로 붙인다
  TF 는 Wi-Fi 지연만큼 늦게 오므로 측정 시각의 TF 가 올 때까지 tf_wait 동안 기다렸다가 그 시각으로 보간한다
  (그래도 없으면 가장 최근 TF)
- pose_ok=False: TF 를 못 찾음 / 측정 시각과 붙인 TF 시각 차가 max_pose_age 초과 /
  지금과 최근 TF 시각 차(통신 지연 또는 노트북·로봇 시계 차)가 max_pose_age 초과 / AMCL 공분산(xx+yy)이 max_pose_cov 초과
- launch 에서 /tf, /tf_static 을 {ns}/tf, {ns}/tf_static 으로 바꿔 준다 (TurtleBot4 이름공간)
"""

import math
import statistics
from collections import deque

import rclpy
from geometry_msgs.msg import PointStamped, PoseWithCovarianceStamped
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from tf2_ros import Buffer, TransformException, TransformListener

from scv_msgs.msg import NetRaw, NetSample
from scv_survey.heatmap import pose_usable
from scv_survey.rssi_scanner import RAW_QOS

SAMPLE_QOS = QoSProfile(reliability=ReliabilityPolicy.RELIABLE, depth=50)
AMCL_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    depth=1,
)


def yaw_from_quat(q) -> float:
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


class ManualTagger(Node):
    def __init__(self):
        super().__init__('manual_tagger')
        self.pose_source = self.declare_parameter('pose_source', 'manual').value
        self.run_id = self.declare_parameter('run_id', 1).value
        self.seq = 0
        self.pose = (0.0, 0.0, 0.0)

        self.pub = self.create_publisher(NetSample, 'survey/sample', SAMPLE_QOS)
        self.create_subscription(NetRaw, 'survey/raw', self.on_raw, RAW_QOS)

        if self.pose_source == 'tf':
            self.init_tf()
        elif self.pose_source == 'manual':
            self.init_manual()
        else:
            raise ValueError(f'pose_source 는 manual 또는 tf: {self.pose_source}')

    # ---------------- manual ----------------

    def init_manual(self):
        self.n_per_point = self.declare_parameter('samples_per_point', 5).value
        x = self.declare_parameter('init_x', 0.0).value
        y = self.declare_parameter('init_y', 0.0).value
        yaw = self.declare_parameter('init_yaw', 0.0).value
        measure_on_start = self.declare_parameter('measure_on_start', True).value

        self.pose = (x, y, yaw)
        self.remaining = 0
        self.set_time = self.get_clock().now()
        self.collected = []

        self.create_subscription(PointStamped, '/clicked_point', self.on_click, 10)
        self.create_subscription(PoseWithCovarianceStamped, '/initialpose', self.on_initialpose, 10)

        if measure_on_start:
            self.set_point(x, y, yaw, '초기위치')

    def set_point(self, x, y, yaw, why):
        self.pose = (x, y, yaw)
        self.remaining = self.n_per_point
        self.set_time = self.get_clock().now()
        self.collected = []
        self.get_logger().info(
            f'[{why}] ({x:.2f}, {y:.2f}) 에서 {self.n_per_point}개 측정 시작 — 노트북을 움직이지 마세요')

    def on_click(self, msg: PointStamped):
        self.set_point(msg.point.x, msg.point.y, 0.0, 'Publish Point')

    def on_initialpose(self, msg: PoseWithCovarianceStamped):
        p = msg.pose.pose
        self.set_point(p.position.x, p.position.y, yaw_from_quat(p.orientation), '2D Pose Estimate')

    def manual_pose_ok(self, raw: NetRaw) -> bool:
        # 위치를 주기 전에 잰 샘플(transient_local 로 밀려온 옛 샘플 포함)은 그 자리 값이 아니다
        measuring = self.remaining > 0 and Time.from_msg(raw.stamp) >= self.set_time
        if not measuring:
            return False
        self.remaining -= 1
        self.collected.append(raw.rssi_dbm if raw.detected else None)
        if self.remaining == 0:
            hits = [v for v in self.collected if v is not None]
            med = f'{statistics.median(hits):.1f} dBm' if hits else '없음'
            self.get_logger().info(
                f'({self.pose[0]:.2f}, {self.pose[1]:.2f}) 측정 끝: 중앙값 {med}, '
                f'검출 {len(hits)}/{len(self.collected)} — 다음 위치를 클릭하세요')
        return True

    # ---------------- tf ----------------

    def init_tf(self):
        self.map_frame = self.declare_parameter('map_frame', 'map').value
        self.base_frame = self.declare_parameter('base_frame', 'base_link').value
        self.max_pose_age = self.declare_parameter('max_pose_age', 0.5).value
        self.max_pose_cov = self.declare_parameter('max_pose_cov', 0.25).value
        self.tf_wait = self.declare_parameter('tf_wait', 0.5).value
        self.cov_xy = None
        self.lag = None
        self.n_ok = 0
        self.n_bad = 0
        self.pending = deque()

        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.create_subscription(PoseWithCovarianceStamped, 'amcl_pose', self.on_amcl, AMCL_QOS)
        self.create_timer(0.05, self.flush_pending)
        self.get_logger().info(
            f'TF {self.map_frame} → {self.base_frame} 로 위치를 붙입니다 '
            f'(TF 기다림 ≤ {self.tf_wait} s, 시각 차·지연 ≤ {self.max_pose_age} s, '
            f'AMCL 공분산 ≤ {self.max_pose_cov} m^2)')

    def on_amcl(self, msg: PoseWithCovarianceStamped):
        c = msg.pose.covariance
        self.cov_xy = c[0] + c[7]

    def flush_pending(self):
        """측정 시각의 TF 가 들어온 샘플부터 순서대로 보낸다. tf_wait 이 지나면 있는 TF 로 판정"""
        now = self.get_clock().now()
        while self.pending:
            raw = self.pending[0]
            t_meas = Time.from_msg(raw.stamp)
            waited = (now - t_meas).nanoseconds * 1e-9
            ready = self.tf_buffer.can_transform(self.map_frame, self.base_frame, t_meas)
            if not ready and waited < self.tf_wait:
                return   # TF 는 통신 지연만큼 늦게 온다 → 조금 더 기다린다
            self.pending.popleft()
            self.publish(raw, self.tf_pose_ok(raw, now))

    def lookup_pose(self, stamp, now):
        """(x, y, yaw, 측정 시각 - 붙인 TF 시각, 지금 - 최근 TF 시각) [s] 또는 None"""
        try:
            latest = self.tf_buffer.lookup_transform(self.map_frame, self.base_frame, Time())
        except TransformException:
            return None
        t_meas = Time.from_msg(stamp)
        try:
            tf = self.tf_buffer.lookup_transform(self.map_frame, self.base_frame, t_meas)
        except TransformException:
            tf = latest
        tr = tf.transform.translation
        age = (t_meas - Time.from_msg(tf.header.stamp)).nanoseconds * 1e-9
        lag = (now - Time.from_msg(latest.header.stamp)).nanoseconds * 1e-9
        return tr.x, tr.y, yaw_from_quat(tf.transform.rotation), age, lag

    def tf_pose_ok(self, raw: NetRaw, now) -> bool:
        found = self.lookup_pose(raw.stamp, now)
        if found is not None:
            x, y, yaw, age, self.lag = found
            self.pose = (x, y, yaw)
        else:
            age = None
        ok, why = pose_usable(age, self.cov_xy, self.max_pose_age, self.max_pose_cov, self.lag)
        if ok:
            self.n_ok += 1
            rssi = f'{raw.rssi_dbm} dBm' if raw.detected else '미검출'
            self.get_logger().info(
                f'({self.pose[0]:.2f}, {self.pose[1]:.2f}) {rssi}  TF 지연 {self.lag:.2f} s  '
                f'[사용 {self.n_ok} / 제외 {self.n_bad}]',
                throttle_duration_sec=2.0)
        else:
            self.n_bad += 1
            self.get_logger().warn(f'위치 제외: {why}', throttle_duration_sec=2.0)
        return ok

    # ---------------- 공통 ----------------

    def on_raw(self, raw: NetRaw):
        if self.pose_source == 'tf':
            self.pending.append(raw)
            self.flush_pending()
        else:
            self.publish(raw, self.manual_pose_ok(raw))

    def publish(self, raw: NetRaw, ok: bool):
        s = NetSample()
        s.seq = self.seq
        s.stamp = raw.stamp
        s.robot_id = raw.robot_id
        s.run_id = self.run_id
        s.x, s.y, s.yaw = (float(v) for v in self.pose)
        s.pose_ok = ok
        s.resent = False
        s.detected = raw.detected
        s.rssi_dbm = raw.rssi_dbm
        self.pub.publish(s)
        self.seq += 1

def main(args=None):
    rclpy.init(args=args)
    node = ManualTagger()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()

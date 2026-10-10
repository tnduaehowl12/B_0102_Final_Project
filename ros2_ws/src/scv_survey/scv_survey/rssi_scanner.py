"""IF-02 rssi_scanner: iw 로 핫스팟 RSSI 를 1 Hz 로 재서 {ns}/survey/raw (NetRaw) 로 보낸다.

노트북 시험: iface=wlo1, robot_id=laptop. RPi 에서는 iface=wlan0, robot_id=robot4 등.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy

from scv_msgs.msg import NetRaw
from scv_survey.iw_reader import iw_available, read_iw_link

RAW_QOS = QoSProfile(
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
    history=HistoryPolicy.KEEP_LAST,
    depth=600,
)


class RssiScanner(Node):
    def __init__(self):
        super().__init__('rssi_scanner')
        self.iface = self.declare_parameter('iface', 'wlo1').value
        self.ssid = self.declare_parameter('target_ssid', 'turtle08').value
        self.robot_id = self.declare_parameter('robot_id', 'laptop').value
        rate = self.declare_parameter('rate_hz', 1.0).value

        self.pub = self.create_publisher(NetRaw, 'survey/raw', RAW_QOS)
        self.timer = self.create_timer(1.0 / rate, self.on_timer)
        self.get_logger().info(
            f'iw dev {self.iface} link 로 {self.ssid} 측정, {rate} Hz, robot_id={self.robot_id}')

    def on_timer(self):
        r = read_iw_link(self.iface, self.ssid)
        msg = NetRaw()
        msg.stamp = self.get_clock().now().to_msg()
        msg.robot_id = self.robot_id
        msg.detected = r.detected
        msg.rssi_dbm = r.rssi_dbm if r.detected else 0
        self.pub.publish(msg)
        if r.detected:
            self.get_logger().debug(f'{self.ssid} {r.rssi_dbm} dBm')
        else:
            self.get_logger().warn(
                f'{self.ssid} 미검출 (지금 SSID: {r.ssid})', throttle_duration_sec=5.0)


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

#!/usr/bin/env python3
# PLAN 1-4: odom 단독 오차. odom 기준 2 m 직진(0.2 m/s) 또는 360° 회전(0.5 rad/s) 후 멈추고 결과 출력
#   python3 odom_check.py --ros-args -r __ns:=/robot3 -p mode:=straight
#   python3 odom_check.py --ros-args -r __ns:=/robot3 -p mode:=rotate
# 줄자로 잰 실제 값을 입력하면 ~/scv_logs/odom_check.csv 에 한 줄 추가 (Enter만 누르면 기록 안 함)
import csv
import math
import os
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry

LOG = os.path.expanduser('~/scv_logs/odom_check.csv')


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


class OdomCheck(Node):
    def __init__(self):
        super().__init__('odom_check')
        self.mode = self.declare_parameter('mode', 'straight').value
        self.pose = None   # (x, y, yaw)
        self.create_subscription(Odometry, 'odom', self.on_odom, qos_profile_sensor_data)
        self.cmd_pub = self.create_publisher(TwistStamped, 'cmd_vel', 10)
        self.get_logger().info(f'Odom check started (mode={self.mode})')

    def on_odom(self, msg):
        p, q = msg.pose.pose.position, msg.pose.pose.orientation
        self.pose = (p.x, p.y, math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z)))

    def send(self, v, w):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.linear.x, msg.twist.angular.z = v, w
        self.cmd_pub.publish(msg)

    def stop(self):
        for _ in range(5):
            self.send(0.0, 0.0)
            time.sleep(0.05)

    def straight(self, dist=2.0, v=0.2):
        x0, y0, _ = self.pose
        end = time.time() + dist / v * 2   # 시간 제한
        while math.hypot(self.pose[0] - x0, self.pose[1] - y0) < dist and time.time() < end:
            self.send(v, 0.0)
            time.sleep(0.02)
        self.stop()
        time.sleep(1.0)   # 멈춘 뒤 odom 안정
        return math.hypot(self.pose[0] - x0, self.pose[1] - y0)

    def rotate(self, w=0.5):
        turned, last = 0.0, self.pose[2]
        end = time.time() + 2 * math.pi / w * 2
        while turned < 2 * math.pi and time.time() < end:
            self.send(0.0, w)
            time.sleep(0.02)
            turned, last = turned + wrap(self.pose[2] - last), self.pose[2]
        self.stop()
        time.sleep(1.0)
        return math.degrees(turned + wrap(self.pose[2] - last))


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = OdomCheck()
    spin = threading.Thread(target=rclpy.spin, args=(node,))
    spin.start()
    try:
        while node.pose is None:
            time.sleep(0.1)
        input('로봇을 시작 테이프에 맞추고 Enter (Ctrl+C로 정지)')
        if node.mode == 'rotate':
            odom, unit = node.rotate(), 'deg'
            hint = '실제 회전 각도(°, 360 기준으로 더/덜 돈 만큼 반영)'
        else:
            odom, unit = node.straight(), 'm'
            hint = '줄자로 잰 실제 이동 거리(m)'
        print(f'odom 결과: {odom:.3f} {unit}')
        actual = input(f'{hint}, 기록 안 하려면 Enter: ').strip()
        if actual:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            new = not os.path.exists(LOG)
            with open(LOG, 'a', newline='') as f:
                w = csv.writer(f)
                if new:
                    w.writerow(['time', 'robot', 'mode', 'odom', 'actual', 'error', 'unit'])
                w.writerow([time.strftime('%F %T'), node.get_namespace(), node.mode,
                            f'{odom:.4f}', actual, f'{odom - float(actual):.4f}', unit])
            print(f'오차(odom-실제): {odom - float(actual):+.3f} {unit} → {LOG}')
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        rclpy.shutdown()
        spin.join()


if __name__ == '__main__':
    main()

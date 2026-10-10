#!/usr/bin/env python3
# PLAN 1-1·1-2: Wi-Fi 너머 scan·odom 수신 지연, cmd_vel→odom 반응 지연 측정
#   python3 latency_check.py --ros-args -r __ns:=/robot3                 # 10초마다 수신 지연 (로봇 안 움직임)
#   python3 latency_check.py --ros-args -r __ns:=/robot3 -p step:=true   # 0.3 rad/s 0.5초 회전 ×20, 반응 지연 (로봇 움직임)
# 수신 지연(받은 시각 - header.stamp)은 로봇 PC·RPi 시계(chrony)가 맞아야 의미가 있다.
import threading
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.signals import SignalHandlerOptions
from geometry_msgs.msg import TwistStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import LaserScan


def stats(ms):
    s = sorted(ms)
    return f'mean {sum(s) / len(s):.0f} / p95 {s[int(0.95 * (len(s) - 1))]:.0f} / max {s[-1]:.0f} ms (n={len(s)})'


class LatencyCheck(Node):
    def __init__(self):
        super().__init__('latency_check')
        self.step = self.declare_parameter('step', False).value
        self.delays = {'scan': [], 'odom': []}
        self.wz, self.wz_time = 0.0, 0.0
        self.create_subscription(LaserScan, 'scan', lambda m: self.on_msg('scan', m), qos_profile_sensor_data)
        self.create_subscription(Odometry, 'odom', self.on_odom, qos_profile_sensor_data)
        self.cmd_pub = self.create_publisher(TwistStamped, 'cmd_vel', 10)
        if not self.step:
            self.create_timer(10.0, self.report)
        self.get_logger().info(f'Latency check started (step={self.step})')

    def on_msg(self, name, msg):
        stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        self.delays[name].append((time.time() - stamp) * 1000)

    def on_odom(self, msg):
        self.on_msg('odom', msg)
        self.wz, self.wz_time = msg.twist.twist.angular.z, time.time()

    def report(self):
        for name, d in self.delays.items():
            self.get_logger().info(f'[{name}] ' + (stats(d) if d else '수신 없음'))
            d.clear()

    def send(self, wz):
        msg = TwistStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'base_link'
        msg.twist.angular.z = wz
        self.cmd_pub.publish(msg)

    def stop(self):
        for _ in range(5):
            self.send(0.0)
            time.sleep(0.05)

    def run_steps(self, trials=20):
        results = []
        for i in range(trials):
            time.sleep(1.5)   # 멈춘 상태에서 시작
            t0, latency = time.time(), None
            while time.time() - t0 < 2.0:
                self.send(0.3 if time.time() - t0 < 0.5 else 0.0)
                if latency is None and self.wz_time > t0 and abs(self.wz) > 0.1:
                    latency = (self.wz_time - t0) * 1000
                time.sleep(0.02)
            self.stop()
            self.get_logger().info(f'step {i + 1}/{trials}: ' + (f'{latency:.0f} ms' if latency else '반응 없음'))
            if latency:
                results.append(latency)
        self.get_logger().info('[cmd_vel→odom] ' + (stats(results) if results else '반응 없음 — cmd_vel 타입·네임스페이스 확인'))


def main():
    rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
    node = LatencyCheck()
    spin = threading.Thread(target=rclpy.spin, args=(node,))
    spin.start()
    try:
        if node.step:
            node.run_steps()
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()
        rclpy.shutdown()
        spin.join()


if __name__ == '__main__':
    main()

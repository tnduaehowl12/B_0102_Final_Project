"""로봇 RPi 한 대: rssi_scanner. (드라이버는 turtlebot4 기본 bringup 이 띄운다)

    ros2 launch scv_bringup robot_rpi.launch.py robot_ns:=robot4
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, GroupAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import PushRosNamespace


def generate_launch_description():
    nodes = [
        # 노드가 준비되면 여기에 추가한다 (RSSI 팀):
        # Node(package='scv_survey', executable='rssi_scanner', parameters=[{'robot_id': LaunchConfiguration('robot_ns')}]),
    ]
    return LaunchDescription([
        DeclareLaunchArgument('robot_ns', default_value='robot4', description='로봇 이름공간 (robot4, robot3)'),
        GroupAction([PushRosNamespace(LaunchConfiguration('robot_ns')), *nodes]),
    ])

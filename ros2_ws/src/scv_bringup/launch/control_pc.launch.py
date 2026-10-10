"""관제 PC: inspection_manager, ros_bridge, network_map_engine, 관제 웹.

    ros2 launch scv_bringup control_pc.launch.py
"""
from launch import LaunchDescription


def generate_launch_description():
    nodes = [
        # 노드가 준비되면 여기에 추가한다:
        # 관제 A: Node(package='scv_manager', executable='inspection_manager')
        # 관제 B: Node(package='scv_monitor', executable='ros_bridge'), 관제 웹
        # RSSI B: Node(package='scv_survey', executable='network_map_engine')
    ]
    return LaunchDescription(nodes)

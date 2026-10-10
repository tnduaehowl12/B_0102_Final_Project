"""노트북 단위시험: test_map 위에 노트북으로 잰 turtle08 RSSI 를 0.5 m 칸 색으로 표시한다.

노트북만 들고 (위치는 RViz 클릭):
  ros2 launch scv_survey laptop_test.launch.py
노트북을 TurtleBot4 위에 올리고 (위치는 로봇 TF, 지도·AMCL 은 turtlebot4_navigation localization 이 띄움):
  ros2 launch scv_survey laptop_test.launch.py pose_source:=tf robot_ns:=robot4
"""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch_ros.actions import Node


def _nodes(context):
    share = get_package_share_directory('scv_survey')
    arg = lambda name: context.launch_configurations[name]  # noqa: E731
    use_tf = arg('pose_source') == 'tf'
    ns = arg('robot_ns') or ('robot4' if use_tf else 'laptop')
    csv_path = arg('csv_path') or f'~/scv_survey_logs/{ns}_{arg("pose_source")}.csv'

    if use_tf:
        tagger_params = {'pose_source': 'tf', 'base_frame': arg('base_frame'),
                         'max_pose_age': float(arg('max_pose_age'))}
        # TurtleBot4 는 TF·지도·AMCL 을 로봇 이름공간 아래에 둔다
        tf_remaps = [('/tf', 'tf'), ('/tf_static', 'tf_static')]
        rviz_remaps = [(f'/{t}', f'/{ns}/{t}')
                       for t in ('tf', 'tf_static', 'map', 'initialpose', 'scan', 'robot_description')]
        map_topic = f'/{ns}/map'
    else:
        tagger_params = {'pose_source': 'manual',
                         'init_x': float(arg('init_x')), 'init_y': float(arg('init_y')),
                         'samples_per_point': int(arg('samples_per_point'))}
        tf_remaps, rviz_remaps, map_topic = [], [], '/map'

    nodes = [
        Node(package='scv_survey', executable='rssi_scanner', namespace=ns, output='screen',
             parameters=[{'iface': arg('iface'), 'target_ssid': arg('ssid'), 'robot_id': ns}]),
        Node(package='scv_survey', executable='manual_tagger', namespace=ns, output='screen',
             parameters=[tagger_params], remappings=tf_remaps),
        Node(package='scv_survey', executable='network_map_engine', output='screen',
             parameters=[{'sample_topics': [f'/{ns}/survey/sample'],
                          'map_topic': map_topic,
                          'cell_size': float(arg('cell_size')),
                          'rssi_strong': float(arg('rssi_strong')),
                          'rssi_weak': float(arg('rssi_weak')),
                          'csv_path': csv_path}]),
    ]
    if not use_tf:
        # 로봇 시험에서는 localization.launch.py 의 map_server 가 /{ns}/map 을 낸다
        nodes += [
            Node(package='nav2_map_server', executable='map_server', name='map_server',
                 parameters=[{'yaml_filename': arg('map')}], output='screen'),
            Node(package='nav2_lifecycle_manager', executable='lifecycle_manager',
                 name='lifecycle_manager_map', output='screen',
                 parameters=[{'autostart': True, 'node_names': ['map_server']}]),
        ]
    if arg('rviz') == 'true':
        nodes.append(
            Node(package='rviz2', executable='rviz2', name='rviz2', output='log',
                 arguments=['-d', os.path.join(share, 'rviz', 'survey.rviz')],
                 remappings=rviz_remaps))
    return nodes


def generate_launch_description():
    share = get_package_share_directory('scv_survey')
    return LaunchDescription([
        DeclareLaunchArgument('pose_source', default_value='manual',
                              description='manual: RViz 클릭 위치 / tf: 로봇 TF map→base_link'),
        DeclareLaunchArgument('robot_ns', default_value='',
                              description='비우면 manual=laptop, tf=robot4'),
        DeclareLaunchArgument('map', default_value=os.path.join(share, 'maps', 'test_map.yaml'),
                              description='manual 에서만 씀'),
        DeclareLaunchArgument('iface', default_value='wlo1'),
        DeclareLaunchArgument('ssid', default_value='turtle08'),
        DeclareLaunchArgument('init_x', default_value='0.0'),
        DeclareLaunchArgument('init_y', default_value='0.0'),
        DeclareLaunchArgument('samples_per_point', default_value='5'),
        DeclareLaunchArgument('base_frame', default_value='base_link'),
        DeclareLaunchArgument('max_pose_age', default_value='0.5',
                              description='측정 시각·지금과 TF 시각 차 허용 [s] (지연·시계 차), 0 이면 검사 안 함'),
        DeclareLaunchArgument('cell_size', default_value='0.5'),
        DeclareLaunchArgument('rssi_strong', default_value='-35.0',
                              description='이 값 이상은 빨강 [dBm]'),
        DeclareLaunchArgument('rssi_weak', default_value='-75.0',
                              description='이 값 이하는 파랑(음영) [dBm]'),
        DeclareLaunchArgument('csv_path', default_value='',
                              description='비우면 ~/scv_survey_logs/{robot_ns}_{pose_source}.csv'),
        DeclareLaunchArgument('rviz', default_value='true'),
        OpaqueFunction(function=_nodes),
    ])

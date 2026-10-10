cmake_minimum_required(VERSION 3.8)
project(scv_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)
find_package(builtin_interfaces REQUIRED)
find_package(geometry_msgs REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/NetRaw.msg"
  "msg/NetSample.msg"
  "msg/RobotStatus.msg"
  "msg/Candidate.msg"
  "msg/InspectionResult.msg"
  "msg/Alert.msg"
  "srv/SyncSamples.srv"
  "action/ExecuteTask.action"
  "action/PreciseMeasure.action"
  "action/InspectFacility.action"
  DEPENDENCIES builtin_interfaces geometry_msgs
)

ament_export_dependencies(rosidl_default_runtime)
ament_package()

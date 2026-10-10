# SCV 인터페이스 (초안 v0.2)

2026-10-10 · 작성 도윤 (PM) · **팀 검토 전 초안입니다. 피드백을 받아 고칩니다.**

v0.2: 회차 전달·근거 사진·후보 발견 로봇·재개/재배정·각도 rad·scv_survey 패키지

팀 사이에 오가는 토픽·서비스·액션과 그 타입을 한곳에 모았습니다. 타입 정의는 `ros2_ws/src/scv_msgs/` 에 있습니다. 고칠 것이 있으면 그 약속의 **주인**에게 말하고, 주인이 `scv_msgs` 와 이 문서를 함께 고칩니다.

## 이름 규칙

- `{ns}` 는 로봇 이름공간입니다: `/robot1`, `/robot2`. `robot_id` 필드에는 앞의 `/` 없이 `robot1`, `robot2` 를 씁니다.
- 좌표는 저장 지도(`map`) 기준이고 단위는 m, 각도는 rad 입니다.
- `/inspection/...` 은 로봇과 무관한 관제 PC 쪽 이름입니다.

## 기기와 패키지

| 패키지 | 실행 위치 | 들어갈 노드 | 팀 |
| --- | --- | --- | --- |
| `scv_msgs` | 5대 전부 | 메시지·서비스·액션 | PM |
| `scv_survey` | RPi · 로봇 PC · 관제 PC | `rssi_scanner`, `survey_buffer`, `network_map_engine` | 통신 인프라·RSSI (A·B) |
| `scv_nav` | 로봇 PC | `mission_executor`, Nav2 설정 | 주행 |
| `scv_detection` | 로봇 PC | `detection_alert` | 비전·물리 인프라 |
| `scv_manager` | 관제 PC | `inspection_manager` | 관제·작업 관리 (A) |
| `scv_monitor` | 관제 PC | `ros_bridge`, 관제 웹, `webcam_node` | 관제·작업 관리 (B) |
| `scv_bringup` | 5대 전부 | launch, params, 지도, `facilities.yaml` | PM |
| `scv_testbed` | PC | 가짜 데이터 도구, 시험 스크립트 | PM |

## 인터페이스

IF 번호는 시스템 다이어그램과 같습니다 (IF-03·13 은 삭제된 번호). IF-01(핫스팟 RF) · 17(Socket.IO·SQL) · 18(HTTP·웹캠 USB)은 ROS 밖이라 이 표에 없다 (다이어그램 참고).

| IF | 이름 | 종류 · 타입 | 보내는 쪽 → 받는 쪽 | QoS · 주기 | 주인 |
| --- | --- | --- | --- | --- | --- |
| 02 | `{ns}/survey/raw` | topic · `scv_msgs/NetRaw` | rssi_scanner (RPi) → survey_buffer (로봇 PC) | reliable · transient_local · KEEP_LAST 600 · 1 Hz | RSSI A |
| 04 | `{ns}/survey/precise` | action · `scv_msgs/PreciseMeasure` | mission_executor (로봇 PC) → rssi_scanner (RPi) | — | RSSI A |
| 05 | `{ns}/inspect_facility` | action · `scv_msgs/InspectFacility` | mission_executor → detection_alert (같은 로봇 PC) | feedback 보정값은 rad · m | 비전 B |
| 06 | `{ns}/dock` · `{ns}/undock` | action · `irobot_create_msgs` | mission_executor (로봇 PC) → Create 3 | — | 주행 |
| 07 | `{ns}/scan` · `odom` · `tf` · `tf_static` / `{ns}/cmd_vel` | topic · 표준 타입 | RPi ↔ Nav2 (로봇 PC) | 센서 best effort · cmd_vel reliable | 주행 |
| 08 | `{ns}/survey/sample` | topic · `scv_msgs/NetSample` | survey_buffer (로봇 PC) → ros_bridge · network_map_engine (관제 PC) | reliable · depth 50 · 1 Hz (sync 재발행은 depth를 넘지 않게 천천히, 예: 20 Hz 이하) | RSSI A |
| 09 | `{ns}/survey/sync` | service · `scv_msgs/SyncSamples` | ros_bridge (관제 PC) → survey_buffer (로봇 PC) | 재연결 때 | RSSI A |
| 10 | `{ns}/keepout_mask` | topic · `nav_msgs/OccupancyGrid` | network_map_engine (관제 PC) → Nav2 (로봇 PC) | reliable · transient_local | RSSI B |
| 11 | `{ns}/execute_task` | action · `scv_msgs/ExecuteTask` | inspection_manager (관제 PC) → mission_executor (로봇 PC) | — | 관제 A |
| 12 | `{ns}/status` | topic · `scv_msgs/RobotStatus` | mission_executor (로봇 PC) → inspection_manager · ros_bridge (관제 PC) | reliable · 1 Hz | 관제 A |
| 14 | `{ns}/oakd/rgb/image_raw/compressed` · depth | topic · `sensor_msgs/CompressedImage` | OAK-D (RPi) → detection_alert (로봇 PC) · CAM 탭 (관제 PC) | best effort · 구독할 때만 | 비전 B |
| 15 | `/inspection/candidates` | topic · `scv_msgs/Candidate` | network_map_engine → inspection_manager (관제 PC 안) | reliable · transient_local · KEEP_LAST 100 | RSSI B |
| 16 | `/inspection/alerts` | topic · `scv_msgs/Alert` | inspection_manager → 관제 웹 (관제 PC 안) | reliable | 관제 A |
| 16 | `/inspection/start` · `/inspection/estop` · `/inspection/resume` | service · `std_srvs/Trigger` | 관제 웹 → inspection_manager | — | 관제 A |
| 16 | `/inspection/reassign` | service · `scv_msgs/Reassign` | 관제 웹 → inspection_manager | — | 관제 A |
| 19 | `{ns}/inspect/result` | topic · `scv_msgs/InspectionResult` | detection_alert (로봇 PC) → inspection_manager · ros_bridge (관제 PC) | reliable · transient_local · KEEP_LAST 50 | 비전 B |

## 타입 한눈에

| 타입 | 담는 것 |
| --- | --- |
| `NetRaw` | 측정 시각, 로봇, 핫스팟 RSSI (미검출 −100) |
| `NetSample` | `NetRaw` + seq, 회차, 위치(x·y·yaw), `pose_ok`, `resent` |
| `RobotStatus` | 상태, 배터리, 새 작업을 받는지, 수행 중인 작업·진행률, 위치, 경고, 회차 |
| `Candidate` | 이상 후보: 출처(네트워크·비전), 종류, 대상, 갈 위치, 점수, 근거, 발견 로봇·회차 |
| `InspectionResult` | 설비 판정 한 건: 설비, 종류, 판정, 사진, 관측 횟수, 사진 축소본(CompressedImage) |
| `Alert` | 알림: 수준, 코드, 로봇, 대상, 문구, 늦게 전달됐는지 |
| `SyncSamples` (srv) | 회차와 `from_seq` 를 주면 그 뒤 샘플을 `survey/sample` 로 다시 발행 |
| `Reassign` (srv) | 한 로봇의 남은 작업을 다른 로봇으로 (받는 로봇 비우면 manager가 고름) |
| `ExecuteTask` (action) | 작업 한 건: 종류(SURVEY_SEGMENT·FACILITY_CHECK·REINSPECTION·DOCK), 웨이포인트, 대상, 회차 |
| `PreciseMeasure` (action) | 정지 측정: 시간 → RSSI 중앙값·IQR·표본 수 |
| `InspectFacility` (action) | 설비 점검: 설비 → 판정, 피드백으로 자세 보정 요청 |

필드와 상수는 각 `.msg` · `.srv` · `.action` 파일의 주석을 보세요.

## 설계 문서에 없어서 PM 이 채운 부분 — 검토해 주세요

아래는 설계 초안에 필드 정의가 없거나 서로 달라서 임시로 정한 것입니다. 주인이 확인하고 고쳐 주세요.

| 무엇 | 임시로 정한 내용 | 확인할 사람 |
| --- | --- | --- |
| `NetRaw` 필드 | 시각, `robot_id`, `rssi_dbm` 세 가지뿐 | RSSI A |
| `SyncSamples` 응답 | 샘플을 응답에 담지 않고 `survey/sample` 로 다시 발행, 응답은 개수만 | RSSI A · 관제 B |
| `RobotStatus` 필드 전체 | 상태 7가지, `accepting_tasks`, `warning` 등 | 관제 A · 주행 |
| `InspectionResult` 필드 전체 | 판정·종류 상수를 여기에 두고 `InspectFacility` 가 함께 씀 | 비전 B · 관제 |
| `Alert` 필드 전체 | `code` 는 문자열 (CANDIDATE, CONFIRMED, E1–E8 …) | 관제 A |
| `Candidate` 위치 | 초안의 `geometry_msgs/Pose2D` 는 폐기 예정 타입이라 `x`·`y`·`yaw` 로 바꿈 | RSSI B · 관제 A |
| `Candidate` 종류 | 혼잡·로밍 의심은 범위에서 빠져 상수에서 뺌 (1 과 4 만 남김) | RSSI B |
| `ExecuteTask` 종류 | 다이어그램에 있는 `DOCK` 을 추가 | 관제 A · 주행 |
| 회차 전달 | manager가 `ExecuteTask.run_id`에 넣고, mission_executor가 `RobotStatus.run_id`로 내보내고, survey_buffer가 그것을 읽음 | 관제 A · 주행 · RSSI A |
| 근거 사진 축소본 | JPEG, 긴 변 640 px 이하. 원본은 로봇 PC `image_ref` | 비전 B · 관제 B |
| 네트워크 후보의 `robot_id` | 두 로봇 병합 칸이면 그 칸의 가장 최근 샘플을 잰 로봇 (제안) | RSSI B · 관제 A |
| `Reassign` 형식 | 보낼 로봇 · 받을 로봇(비우면 manager) → 옮긴 작업 수 | 관제 A |
| `resent` | sync 요청으로 다시 보낸 샘플만 true | RSSI A · 관제 B |

## 빌드

```bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
ros2 interface list | grep scv_msgs
# 11개 (msg 6 · srv 2 · action 3)
```

`scv_msgs` 를 고치면 그것을 쓰는 패키지도 다시 빌드해야 합니다.

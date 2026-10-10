# SCV System Design Document (제출용 초안 v0.1)

2026-10-10 · 작성 도윤 (PM) · 출처: 팀 노션 「SCV 설계」, 아키텍처 초안 v0.8, 시스템 다이어그램 v0.9, 저장소. **저장소(`scv_msgs`, `docs/interfaces.md`)와 다르면 저장소가 맞습니다.**

## 1. 개요

TurtleBot4 두 대를 이동형 인프라 점검 플랫폼으로 써서, 물리 인프라(소화기·방화셔터 하강구간·비상구 유도등)와 통신 인프라(핫스팟 RSSI)를 같은 순찰에서 위치 기반으로 점검하고, 이상 후보는 다른 로봇이 다시 확인한다. 요구사항은 `requirements.md`, 흐름은 `process_flow.md`, 시험은 `../TEST_PLAN.md`.

과제의 세 모듈:

| 모듈 | 노드 |
| --- | --- |
| Detection Alert | `detection_alert` (설비 점검 액션 서버, YOLO) |
| AMR Controller | Nav2·AMCL, `mission_executor`, `rssi_scanner`, `survey_buffer`, `inspection_manager` |
| System Monitor | `ros_bridge`, `network_map_engine`, 관제 웹(Flask), SQLite |

## 2. 기기와 배치

| 기기 | 대수 | 돌리는 것 |
| --- | --- | --- |
| 로봇 RPi (TurtleBot4 탑재) | 2 (4번 `/robot4`, 3번 `/robot3`) | 드라이버(Create 3 · LiDAR · OAK-D), `rssi_scanner`, Discovery Server |
| 로봇 PC (MSI GPU 노트북) | 2 (로봇마다 1) | Nav2·AMCL·keepout 필터, `mission_executor`, `detection_alert`, `survey_buffer` |
| 관제 PC (Victus 노트북) | 1 | `inspection_manager`, `ros_bridge`, `network_map_engine`, 관제 웹, SQLite, Discovery Server |
| 휴대폰 핫스팟 | 1 | 측정 대상. 로봇 통신에는 쓰지 않는다 |

- 공통: Ubuntu 24.04 · ROS 2 Jazzy · FastDDS. 모든 기기가 Wi-Fi `turtle08`.
- Discovery Server 는 RPi 4번 · RPi 3번 · 관제 PC 세 곳. 로봇 PC 는 자기 로봇 RPi 서버의 클라이언트.
- Nav2·AMCL 과 YOLO 추론은 RPi 가 아니라 로봇 PC 에서 돈다(RPi4 성능). 설비 점검 루프가 로봇 PC 안에서 닫혀, 관제 PC 가 끊겨도 판정이 계속된다.
- 음영은 '들어가서 버티는 곳'이 아니라 '지도에 표시하고 피하는 곳'이다. 로봇 통신(turtle08)과 측정 대상(핫스팟)이 다르므로 음영에서도 로봇은 조종을 잃지 않는다.

## 3. 패키지와 팀

| 패키지 | 실행 위치 | 노드 | 팀 · 브랜치 |
| --- | --- | --- | --- |
| `scv_msgs` | 전부 | 메시지 6 · 서비스 2 · 액션 3 | PM |
| `scv_survey` | RPi · 로봇 PC · 관제 PC | `rssi_scanner`, `survey_buffer`, `network_map_engine` | RSSI · `feature/survey` |
| `scv_nav` | 로봇 PC | `mission_executor`, Nav2 설정 | 주행 · `feature/driving` |
| `scv_detection` | 로봇 PC | `detection_alert` | 비전 · `feature/vision` |
| `scv_manager` | 관제 PC | `inspection_manager` | 관제 · `feature/control` |
| `scv_monitor` | 관제 PC | `ros_bridge`, 관제 웹 | 관제 · `feature/control` |
| `scv_bringup` | 전부 | 기기별 launch, 설정(`facilities.yaml`, `zones.yaml`), 지도 | PM · `feature/pm` |
| `scv_testbed` | PC | 시험 스크립트 | PM · `feature/pm` |

팀 브랜치에는 그 팀 패키지와 `scv_msgs` 만 있고, `main` 이 통합본이다. 로봇 PC·관제 PC·RPi 는 `main` 으로 돌린다.

실행:

```bash
ros2 launch scv_bringup robot_rpi.launch.py robot_ns:=robot4     # 로봇 RPi
ros2 launch scv_bringup robot_pc.launch.py  robot_ns:=robot4     # 로봇 PC
ros2 launch scv_bringup control_pc.launch.py                     # 관제 PC
```

## 4. 노드가 하는 일

| 노드 | 하는 일 |
| --- | --- |
| `rssi_scanner` | 핫스팟을 스캔해 RSSI 와 검출 여부를 1 Hz 로 발행(위치는 붙이지 않음). 요청이 오면 정지 30초 반복 스캔 → 중앙값·IQR·표본 수 |
| `survey_buffer` | RPi 샘플에 같은 시각의 AMCL 위치와 seq 를 붙여 로봇 PC 디스크에 먼저 저장하고 관제 PC 로 발행. 요청이 오면 지정한 seq 부터 다시 발행 |
| Nav2·AMCL | 저장 지도 위 위치 추정·주행. 관제 PC 가 보낸 keepout 마스크의 칸을 경로에서 뺀다 |
| `mission_executor` | 받은 작업(측정 구간·설비 점검·재검증·Dock)을 Nav2 로 수행하고 결과를 보고. 상태를 1 Hz 로 발행. 관제 PC 가 끊겨도 받은 작업은 끝낸다 |
| `detection_alert` | 요청 때만 OAK-D 영상을 구독 → YOLO → 등록 위치와 대조 → 정면 판별(아니면 자세 보정 요청, 최대 3회) → 판정. 사진은 로봇 PC 에 저장하고 축소본을 결과와 함께 보낸다 |
| `inspection_manager` | 작업·후보 상태의 주인. 경로 생성, 작업 배정, 후보 → 재검증 작업, 이탈 시 재배정, 최종 판정, 비상정지 |
| `network_map_engine` | 격자 통계·신뢰도 → 두 대 병합 → 기준선 비교 → 상태 추정 → 후보 · 음영 칸 → keepout 마스크 |
| `ros_bridge` | 샘플·상태·판정·알림을 받아 (robot, seq) 중복을 거르고 SQLite 에 저장, 화면에 실시간 전달 |
| 관제 웹 | 순찰 시작·재배정·비상정지, 네트워크 지도·작업/로봇·점검 이력, 보고서·점검표 |

## 5. 인터페이스

이름·타입·방향·QoS·주인은 [`docs/interfaces.md`](../interfaces.md), 필드는 `ros2_ws/src/scv_msgs/` 의 정의 파일이 원본이다.

| 구간 | 인터페이스 |
| --- | --- |
| RPi ↔ 로봇 PC | IF-02 측정 raw · IF-04 정지 측정 · IF-06 Dock/Undock · IF-07 센서·`cmd_vel` · IF-14 OAK-D 영상 |
| 로봇 PC 안 | IF-05 설비 점검 |
| 로봇 PC ↔ 관제 PC | IF-08 측정 샘플 · IF-09 sync · IF-10 keepout 마스크 · IF-11 작업 · IF-12 상태 · IF-19 판정 결과 |
| 관제 PC 안 | IF-15 후보 · IF-16 알림·시작·비상정지·재개·재배정 |

## 6. 데이터

- 측정 샘플: 시각, 로봇, 회차, 위치(x·y·yaw), 위치 확실 여부, 검출 여부, RSSI. 미검출은 RSSI 값으로 적지 않고 검출 여부로 표시한다.
- 지도: 격자(1 m 제안) 칸별 평균·중앙값·분산·표본 수. 표본이 적은 칸(n < 3 제안)은 신뢰 낮음. 보간 칸은 따로 표시하고 판정에 쓰지 않는다.
- 설비 판정: NORMAL · NOT_DETECTED · OCCLUDED · POSITION_ANOMALY · ABNORMAL · UNCONFIRMED → 최종 정상 / 이상 / 미확인.
- 후보: 출처(네트워크·비전), 종류, 대상(격자 칸 또는 설비), 발견 로봇, 회차 → 재검증 뒤 확정 · 해제 · 미확인.
- DB(SQLite): runs · net_samples · grid_stats · baselines · facilities · candidates · tasks · inspections · alerts.
- 설정: `scv_bringup/config/facilities.yaml`(설비 번호·종류·예상 위치·관측 자세), `zones.yaml`(측정 구역·경로 간격), 저장 지도 `map.yaml`.

## 7. 다중 로봇 운영

두 로봇은 같은 기능으로 만들고, 시연은 "스카우트 + 검증자" 정책으로 한다. 로봇 A 가 1차 순찰을 하고 로봇 B 는 후보 지점 재검증과 남은 구역을 맡는다. 한 대가 빠지면 남은 로봇이 이어받는다. 작업의 주인은 로봇이 아니라 `inspection_manager` 의 작업 목록이다. 두 로봇은 서로 직접 통신하지 않는다.

## 8. 설계 결정

| # | 결정 |
| --- | --- |
| D1 | YOLO 는 로봇 PC(MSI GPU)에서 추론 |
| D2 | RSSI 는 내장 무선랜으로 핫스팟 채널만 스캔해 읽는다 (주행 통신이 흔들리면 USB 동글로 분리) |
| D3 | 측정 경로는 구역별 왕복 + 설비 지점 |
| D4 | 두 로봇은 같은 기능, 스카우트 + 검증자 정책으로 시연 |
| D5 | Flask 와 ROS 는 별도 `ros_bridge` 로 잇는다 (웹이 죽어도 수집 계속) |
| D6 | 격자·신뢰 기준·변화 판정 수치는 첫 측정을 보고 정한다 |
| D7 | 측정 버퍼는 로봇 PC 에 둔다 (위치 결합도 로봇 PC) |
| D8 | 관제 PC 와 끊기면 받은 작업은 끝까지, 새 작업만 대기 |
| D9 | 시험 AP 는 휴대폰 핫스팟 (로봇과 통신하지 않음) |
| D10 | 측정 지표는 RSSI 만 (BSSID·채널·로밍·지연·손실·처리량 제외) |
| D11 | 상태 추정은 커버리지 저하 의심 · 판단 불가 두 가지, 회피 기준과 해제 규칙 포함 |
| 10/10 | 고정 웹캠은 쓰지 않는다 · 로봇은 4번·3번 · 미검출은 검출 여부로 표시 · 지도는 테스트베드에서 한 번 만든 것을 고정해 쓴다 |

## 9. 한계

- 강의장 축소 테스트베드의 결과이고 실제 창고를 재현한 것이 아니다 (BR-R07).
- 휴대폰 핫스팟으로 만든 음영은 실제 설비 AP 의 음영과 같지 않다.
- 로봇 높이에서 잰 신호다. 단말 높이의 품질과 다를 수 있다.
- 로봇과 로봇 PC 사이의 Wi-Fi 가 끊기지 않는 것을 전제로 한다.

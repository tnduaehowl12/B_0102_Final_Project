# scv_survey — RSSI 측정·히트맵 (노트북 단위시험판)

2026-10-10 · 통신 인프라·RSSI 팀

노트북으로 핫스팟(turtle08) RSSI 를 재서, 잰 위치의 0.5 m 칸을 신호 세기 색으로 RViz 지도 위에 칠한다.
위치는 두 가지 중 하나로 얻는다.

| 모드 | 위치 | 쓰는 때 |
| --- | --- | --- |
| `manual` | RViz 에서 클릭한 점 | 노트북만 들고 잴 때 |
| `tf` | 로봇 TF `map → base_link` (AMCL) | 노트북을 TurtleBot4 위에 올리고 teleop 으로 움직이며 잴 때 |

`manual_tagger` 는 로봇 PC 의 `survey_buffer` 자리를 대신하는 **시험용** 노드다. 나머지(`rssi_scanner`, `network_map_engine`)는 실제 구성에서 그대로 쓸 수 있게 IF-02·IF-08 형식을 따른다.

## 전체 흐름

```text
 iw dev wlo1 link ──▶ rssi_scanner ──IF-02 {ns}/survey/raw (NetRaw, 1 Hz)──▶ manual_tagger
                                                                             │  위치를 붙인다
                       manual: /clicked_point, /initialpose (RViz 클릭) ────▶│
                       tf:     {ns}/tf, {ns}/tf_static, {ns}/amcl_pose ─────▶│
                                                                             ▼
                                         IF-08 {ns}/survey/sample (NetSample, pose_ok 포함)
                                                                             │
 map_server ── /map 또는 {ns}/map ──────────────────────────────▶ network_map_engine
                                                                             │ 0.5 m 칸으로 모아 색칠
                                                                             ▼
                                              /survey/heatmap (MarkerArray) ──▶ RViz
                                              ~/scv_survey_logs/*.csv (지도에 쓴 샘플)
```

## 파일 구성

```text
scv_survey/
├── scv_survey/
│   ├── iw_reader.py           iw 출력 읽기 (ROS 무관)
│   ├── heatmap.py             칸 계산·색·위치 판정 (ROS 무관, pytest 대상)
│   ├── rssi_scanner.py        노드: RSSI 측정 → NetRaw
│   ├── manual_tagger.py       노드(시험용): NetRaw + 위치 → NetSample
│   └── network_map_engine.py  노드: NetSample → 히트맵 마커·CSV
├── launch/laptop_test.launch.py
├── rviz/survey.rviz
├── maps/test_map.yaml, test_map.pgm   (해상도 0.05 m, 94×230 px, 원점 −3.107, −4.823)
└── test/test_iw_reader.py, test_heatmap.py
```

## 파일별 동작

### `iw_reader.py` — iw 로 RSSI 읽기

- `read_iw_link(iface, target_ssid)`: `iw dev <iface> link` 를 실행해 `SSID` 와 `signal: -41 dBm` 을 꺼낸다.
  - 스캔(`iw scan`)이 아니라 **접속 중인 링크 정보**만 읽는다 → root 불필요, 통신이 끊기지 않음, 한 번에 2–3 ms.
- 판정:
  - `detected=True`: 지금 붙어 있는 SSID 가 `target_ssid` 이고 signal 이 있을 때
  - `detected=False`: `Not connected.` / 다른 SSID / signal 줄 없음 / iw 실행 실패
- `iw_available()`: iw 설치 여부. 없으면 `rssi_scanner` 가 `sudo apt install iw` 안내 후 종료.

### `heatmap.py` — 칸·색·위치 판정 (ROS 무관)

| 함수·클래스 | 하는 일 |
| --- | --- |
| `Sample` | 샘플 한 개 (robot_id, seq, x, y, pose_ok, detected, rssi_dbm) |
| `cell_index(x, y, ox, oy, cell)` | 지도 원점 기준 칸 번호 `(floor((x−ox)/cell), floor((y−oy)/cell))` |
| `cell_center(i, j, …)` | 칸 중심 좌표 |
| `CellStats` | 칸 하나의 통계: 검출된 RSSI 목록, 미검출 수, **중앙값**, 미검출 비율 |
| `SurveyGrid.add(s)` | `(robot_id, seq)` 중복과 `pose_ok=False` 샘플은 버리고 보관 |
| `SurveyGrid.set_map(…)` | `/map` 의 원점·크기로 칸을 맞추고, 지도 밖 샘플은 칸 계산에서 뺀다 |
| `SurveyGrid.cells()` | 보관한 샘플로 칸별 통계를 매번 다시 계산 (지도를 늦게 받아도 맞게) |
| `rssi_to_color(rssi, strong, weak)` | RSSI → 색 (아래 「색 규칙」) |
| `cell_color(stats, …)` | 칸 색. 검출 0개거나 미검출 비율 ≥ 0.5 면 회색 |
| `pose_usable(age, cov, max_age, max_cov, lag)` | TF 위치를 지도에 써도 되는지와 이유 (아래 「샘플 제외 규칙」) |

### `rssi_scanner.py` — 노드: RSSI 측정 (IF-02)

- `rate_hz`(1 Hz) 마다 `read_iw_link` 를 호출해 `survey/raw` (`scv_msgs/NetRaw`) 로 보낸다.
  - `stamp` = 측정 시각, `robot_id`, `detected`, `rssi_dbm` (미검출이면 0, 쓰지 않음)
- QoS: reliable · transient_local · KEEP_LAST 600 (IF-02).
- 미검출이 이어지면 5 초에 한 번 "미검출 (지금 SSID: …)" 경고.

| 파라미터 | 기본값 | 설명 |
| --- | --- | --- |
| `iface` | `wlo1` | 무선 인터페이스 (RPi 는 `wlan0`) |
| `target_ssid` | `turtle08` | 측정할 핫스팟 |
| `robot_id` | `laptop` | launch 가 이름공간으로 채움 |
| `rate_hz` | 1.0 | 측정 주기 |

### `manual_tagger.py` — 노드(시험용): 위치 붙이기 (IF-02 → IF-08)

`survey/raw` 를 받아 위치·`seq`·`run_id` 를 붙여 `survey/sample` (`scv_msgs/NetSample`) 로 보낸다. `pose_ok=False` 인 샘플도 보내고, 지도에서는 엔진이 뺀다.

**manual 모드** (`pose_source:=manual`)
1. 시작하면 초기위치 `(init_x, init_y)` 에서 `samples_per_point`(5) 개를 잰다.
2. RViz **Publish Point** (`/clicked_point`) 나 **2D Pose Estimate** (`/initialpose`) 로 새 위치를 주면 그 자리에서 다시 5 개.
3. 위치를 준 **뒤** 들어온 5 개만 `pose_ok=True`. 옮기는 중이거나 위치를 주기 전 샘플은 `False`.
4. 5 개가 끝나면 "측정 끝: 중앙값 −42.0 dBm, 검출 5/5" 로그.

**tf 모드** (`pose_source:=tf`)
1. NetRaw 를 대기열에 넣고, **측정 시각의 TF 가 도착할 때까지 최대 `tf_wait`(0.5 s) 기다린다** (TF 는 Wi-Fi 지연만큼 늦게 온다).
2. TF `map → base_link` 를 측정 시각으로 보간해 x, y, yaw 를 붙인다. 끝내 없으면 가장 최근 TF.
3. `pose_usable` 로 `pose_ok` 를 정한다.
4. 2 초마다 로그: `(x, y) −41 dBm  TF 지연 0.03 s  [사용 n / 제외 m]`, 제외될 때는 `위치 제외: <이유>`.
- launch 가 `/tf`, `/tf_static` 을 `/{ns}/tf`, `/{ns}/tf_static` 으로 바꿔 준다 (TurtleBot4 이름공간).
- `{ns}/amcl_pose` 의 공분산(xx + yy)을 받아 둔다.

| 파라미터 | 기본값 | 모드 | 설명 |
| --- | --- | --- | --- |
| `pose_source` | `manual` | 공통 | `manual` / `tf` |
| `run_id` | 1 | 공통 | 회차 |
| `samples_per_point` | 5 | manual | 한 자리에서 잴 개수 |
| `init_x`, `init_y`, `init_yaw` | 0.0 | manual | 초기위치 |
| `measure_on_start` | true | manual | 시작하자마자 초기위치에서 잴지 |
| `map_frame`, `base_frame` | `map`, `base_link` | tf | 찾을 TF |
| `tf_wait` | 0.5 s | tf | 측정 시각 TF 를 기다리는 최대 시간 |
| `max_pose_age` | 0.5 s | tf | 시각 차·지연 허용 (0 이면 검사 안 함) |
| `max_pose_cov` | 0.25 m² | tf | AMCL 공분산 xx+yy 허용 |

### `network_map_engine.py` — 노드: 히트맵 그리기

1. `map_topic` 을 받아 칸을 지도 원점에 맞춘다.
2. `sample_topics` 의 NetSample 을 `SurveyGrid` 에 넣는다 (중복·`pose_ok=False` 제외). 지도에 쓴 샘플은 CSV 에 한 줄씩.
3. 바뀐 것이 있으면 1 초마다 `/survey/heatmap` (MarkerArray, transient_local) 을 보낸다.

| 마커 ns | 종류 | 내용 |
| --- | --- | --- |
| `cells` | TRIANGLE_LIST | 칸 색 (반투명 0.7, 샘플 2 개 미만 칸은 0.35) |
| `labels` | TEXT_VIEW_FACING | 칸 중앙값 dBm (미검출 칸은 `X`) |
| `points` | POINTS | 샘플을 잰 자리 검은 점 (미검출은 회색, 최근 2000 개) |
| `legend` | TRIANGLE_LIST + TEXT | 지도 왼쪽 아래 파랑→빨강 막대, `−75` · `−35 dBm` |

- 칸을 CUBE_LIST 가 아닌 TRIANGLE_LIST 로 그리는 이유: RViz 조명 때문에 CUBE_LIST 는 색이 절반쯤 어두워진다. TRIANGLE_LIST 는 지정한 색 그대로 나온다. (마커 `color.a` 를 1 로 둬야 반투명 칸이 사라지지 않는다.)
- CSV 열: `stamp, robot_id, seq, run_id, x, y, detected, rssi_dbm`. header 는 파일이 없거나 비어 있을 때 쓰고 바로 flush.

| 파라미터 | 기본값 | 설명 |
| --- | --- | --- |
| `sample_topics` | `['/laptop/survey/sample']` | 구독할 샘플 토픽들 (launch 가 `/{ns}/survey/sample` 로) |
| `map_topic` | `/map` | tf 모드는 `/{ns}/map` |
| `cell_size` | 0.5 m | 칸 크기 |
| `rssi_strong`, `rssi_weak` | −35, −75 dBm | 빨강·파랑 끝 |
| `miss_ratio_thresh` | 0.5 | 이 비율 이상 미검출이면 회색 |
| `alpha`, `min_samples_full_alpha` | 0.7, 2 | 칸 투명도, 진하게 칠할 최소 샘플 수 |
| `show_points`, `max_points` | true, 2000 | 잰 자리 점 |
| `csv_path` | (없음) | CSV 경로 |

### `launch/laptop_test.launch.py`

| 인자 | 기본값 | 설명 |
| --- | --- | --- |
| `pose_source` | `manual` | `manual` / `tf` |
| `robot_ns` | (비움) | 비우면 manual=`laptop`, tf=`robot4`. 로봇 3번은 `robot3` |
| `map` | `maps/test_map.yaml` | manual 에서만 (tf 는 localization 이 지도를 냄) |
| `iface`, `ssid` | `wlo1`, `turtle08` | |
| `init_x`, `init_y`, `samples_per_point` | 0, 0, 5 | manual |
| `base_frame`, `max_pose_age` | `base_link`, 0.5 | tf |
| `cell_size`, `rssi_strong`, `rssi_weak` | 0.5, −35, −75 | |
| `csv_path` | (비움) | 비우면 `~/scv_survey_logs/{robot_ns}_{pose_source}.csv` |
| `rviz` | true | |

모드별로 띄우는 것:

| | manual | tf |
| --- | --- | --- |
| rssi_scanner, manual_tagger | `/laptop` | `/{ns}` (+ `/tf` → `/{ns}/tf` 바꿈) |
| network_map_engine | `/map` 구독 | `/{ns}/map` 구독 |
| map_server + lifecycle_manager | 띄움 (test_map) | 안 띄움 |
| RViz | 그대로 | `/tf`, `/tf_static`, `/map`, `/initialpose`, `/scan`, `/robot_description` 을 `/{ns}/…` 로 |

### `rviz/survey.rviz`

Fixed Frame `map`, 위에서 내려다보는 시점. 표시: Map, RSSI Heatmap(`/survey/heatmap`), TurtleBot4 모델, `base_link` 축, LaserScan. 도구: Publish Point(`/clicked_point`), 2D Pose Estimate(`/initialpose`). 로봇 모델·축·스캔은 tf 모드에서만 보인다.

## 색 규칙

- RSSI 를 `−75 ~ −35 dBm` 에 비례해 색상환 파랑(240°) → 빨강(0°) 으로 칠한다.

  | RSSI | −35 이상 | −45 | −55 | −65 | −75 이하 | 미검출 |
  | --- | --- | --- | --- | --- | --- | --- |
  | 색 | 빨강 | 노랑 | 초록 | 하늘 | 파랑 | 회색 |

- 칸 대표값은 그 칸 검출값의 **중앙값** (RSSI 는 ±5 dB 정도 튀어서 평균 대신).
- 미검출은 −100 같은 값으로 적지 않고 통계에서 뺀다 (interfaces v0.2.3). "약함(파랑)"과 "안 잡힘(회색)"을 구분한다.

## 샘플 제외 규칙 (`pose_ok=False`)

| 이유 (로그 문구) | 뜻 |
| --- | --- |
| `TF 없음` | `map → base_link` 가 없다 (AMCL 초기위치 전) |
| `최근 TF 가 지금보다 ±N s` | 통신 지연이 크거나 노트북·로봇 시계가 어긋남. 시계가 어긋나면 측정 시각 TF 가 "찾아져도" 엉뚱한 과거 위치일 수 있어 따로 본다 |
| `TF 시각 차 N s` | 붙인 TF 가 측정 시각과 `max_pose_age` 넘게 다름 (TF 끊김) |
| `AMCL 공분산 N > 0.25` | AMCL 이 아직 위치를 확신하지 못함 (초기위치 직후 0.50 에서 시작해 로봇이 움직일수록 줄어든다) |

## 실행 방법

빌드·단위테스트 (`ros2_ws` 에서):

```bash
colcon build --symlink-install --packages-select scv_msgs scv_survey && source install/setup.bash
cd src/scv_survey && /usr/bin/python3 -m pytest test -q
```

venv 의 pytest 9 는 ROS 의 `launch_testing` 플러그인과 맞지 않아 시스템 python(`/usr/bin/python3`)으로 돌린다.

**노트북만 (manual)**

```bash
ros2 launch scv_survey laptop_test.launch.py
```

노트북을 옮기고 → RViz Publish Point 로 그 자리 클릭 → 5 초 대기 → 다음 자리.

**TurtleBot4 위에 (tf)** — 터미널마다 (로봇 3번 예):

| 순서 | 터미널 | 명령 |
| --- | --- | --- |
| 1 | 확인 | `ros2 topic list \| grep robot3` · `ros2 topic info /robot3/cmd_vel` (TwistStamped 확인) |
| 2 | 위치 추정 | `ros2 launch turtlebot4_navigation localization.launch.py namespace:=/robot3 map:=<install>/share/scv_survey/maps/test_map.yaml` |
| 3 | 측정+RViz | `ros2 launch scv_survey laptop_test.launch.py pose_source:=tf robot_ns:=robot3 csv_path:=~/scv_survey_logs/<이름>.csv` |
| 4 | 초기위치 | RViz 2D Pose Estimate — **undock 위치 = 지도 원점 (0, 0), 방향 −x (yaw π)** |
| 5 | TF 확인 | `ros2 run tf2_ros tf2_echo map base_link --ros-args -r /tf:=/robot3/tf -r /tf_static:=/robot3/tf_static` |
| 6 | 샘플 확인 | `ros2 topic echo /robot3/survey/sample` |
| 7 | teleop | `ros2 run teleop_twist_keyboard teleop_twist_keyboard --ros-args -r __ns:=/robot3 -p stamped:=true -p speed:=0.2 -p turn:=0.5` |

끝낼 때: teleop 에서 `k`(정지) → Ctrl+C, 그다음 6 → 5 → 3 → 2.

도킹: `dock 3`, `undock 3` (`~/.local/bin/dock`, 저장소 밖 개인 설정).

## 시험 결과 (2026-10-10)

| 시험 | 환경 | 결과 |
| --- | --- | --- |
| pytest | mock | 35 개 통과 (iw 해석 5, 색·칸·통계·중복·위치 판정 30) |
| iw 값 확인 | 노트북 | `iw` 와 `/proc/net/wireless` 8/8 일치, 1 회 2–3 ms |
| manual 표시 | 노트북 | 초기위치 (0,0) 5 개 중앙값 −42 dBm → 칸 중심 (0.143, −0.073) 에 표시 (원점 계산과 일치) |
| tf 위치 정확도 | 가짜 로봇 TF (map→odom 어긋남 포함) | TF 지연 0 / 150 / 300 ms 모두 위치 오차 ≤ 0.001 m, 다른 칸 0 |
| 제외 동작 | 가짜 로봇 TF | AMCL 수렴 전·TF 끊김·시계 ±2 s 어긋남 구간 제외 확인 |
| 지도 표시 | 가짜 로봇 TF | RViz 칸 13 개 = CSV 로 다시 계산한 값 |
| **실제 teleop** | **로봇 3번** | 지도에 쓴 샘플 131 개, 칸 8 개, RSSI −46 ~ −35 dBm (칸 중앙값 −44 ~ −40), 미검출 0. TF 지연 0.02–0.07 s. 마지막 위치 TF·샘플·로그 모두 (−2.53, −1.99) 로 일치. 기록 `~/scv_survey_logs/robot3_teleop_01.csv` |

실제 시험에서 확인된 것:
- AMCL 은 undock 위치를 스스로 모른다 (`set_initial_pose: False`). 초기위치를 넣어야 `map` 프레임이 생긴다.
- 로봇 3번 undock 위치는 지도 원점 (0, 0) 이지만 **방향이 yaw π** 다. 0 으로 넣으면 스캔이 지도 밖으로 돈다.
- 초기위치 공분산을 RViz 기본(x, y 각 0.25)으로 주면 AMCL 공분산이 0.50 에서 시작해, 0.25 아래로 내려갈 때까지(약 3 분, 89 개) 샘플이 제외됐다.

## 알려진 한계 · 다음 작업

- 위치 정확도는 AMCL(보통 5–10 cm)을 넘지 못한다. 노트북 안테나와 `base_link` 사이 거리(0.1–0.2 m)는 반영하지 않았다.
- 로봇 방향에 따라 RSSI 가 몇 dB 달라질 수 있다 (같은 칸을 반대 방향으로도 지나 보기).
- 노드를 재시작할 때는 launch 전체를 함께. `manual_tagger` 만 재시작하면 `seq` 가 0 부터 다시 시작해 엔진이 중복으로 버린다.
- `/survey/heatmap` 은 `docs/interfaces.md` 에 없는 관제 PC 내부 토픽이다. 관제 웹에서 쓰려면 PM 에 등록 요청.
- 다음 작업 후보
  - launch 인자 `max_pose_cov`, `init_pose:=0,0,3.14` (시작할 때 작은 공분산으로 AMCL 초기위치 자동 설정)
  - `manual_tagger` 의 tf 모드를 실제 `survey_buffer` (로봇 PC, 버퍼·`survey/sync` 재발행)로 옮기기
  - RPi 에서 `rssi_scanner` (`iface:=wlan0`) 로 바꾸기
  - 칸 사이를 부드럽게 채우는 표시 (NetSpot 식 보간)

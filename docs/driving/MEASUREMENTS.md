# 주행 측정 기록

PLAN.md 각 단계의 「완료 기준」에 해당하는 실측값을 모아 둔다. 원본 데이터는 `data/`, 그래프는 `../daily/barlide/img/`.

## 1단계. 기반 환경 — robot3, 2026-10-10

측정 PC: GPU PC 2(VICTUS, 192.168.108.42) · Wi-Fi turtle08 · ROS_DOMAIN_ID 4 · Discovery Server 192.168.108.104
스크립트: `ros2_ws/src/scv_nav/scripts/latency_check.py`, `odom_check.py`, `plot_latency.py`
수신 지연 = PC가 받은 시각 − 메시지 header.stamp (로봇 RPi와 PC 시계가 chrony로 맞춰져 있다는 전제)

### 1-1 토픽 주기

| 토픽 | 주기 | 비고 |
| --- | --- | --- |
| /robot3/odom | 20.0 Hz | 도킹 중에도 수신 |
| /robot3/tf | 30.0 Hz | |
| /robot3/scan | 7.4 Hz | **도킹 중에는 0 Hz** (TurtleBot4가 도킹 중 라이다를 끔) → 언도킹 후 측정 |

### 1-2 수신 지연 (Wi-Fi)

`latency_check.py -p csv:=…` 로 메시지마다 기록한 값. 데이터: `data/2026-10-10_robot3_latency.csv`(도킹, 119 s), `data/2026-10-10_robot3_latency_undocked.csv`(언도킹, 29 s)

| 상태 | 토픽 | n | mean | median | p95 | max | min | 수신 간격 max | 0건인 초 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 도킹 | odom | 2386 | 48.5 ms | 46.8 ms | 59.0 ms | 102.9 ms | 35.6 ms | 74 ms | 0 / 120 s |
| 언도킹 | odom | 580 | 50.2 ms | 48.1 ms | 60.1 ms | 75.4 ms | 38.5 ms | 69 ms | 0 / 29 s |
| 언도킹 | scan | 214 | 14.5 ms | 14.2 ms | 17.3 ms | 28.6 ms | 12.4 ms | 148 ms | 0 / 29 s |

- odom 지연(약 50 ms)이 scan(약 15 ms)보다 큰 것은 로봇 쪽 odom 발행 경로(Create 3 → RPi 중계)의 차이로 보임. 두 토픽 모두 측정 구간 동안 끊김(0건인 초) 없음.
- 도킹 상태 odom max 102.9 ms는 첫 메시지 1건(기록 시작 직후). 그 뒤로는 75 ms 이하.

그래프: `../daily/barlide/img/2026-10-10_robot3_latency.png`, `2026-10-10_robot3_latency_undocked.png`

### 1-2 명령→반응 지연 (cmd_vel → odom)

`latency_check.py -p step:=true`: 정지 상태에서 cmd_vel 0.3 rad/s를 0.5 s 보내고, odom의 angular.z가 0.1 rad/s를 넘을 때까지의 시간. 20회.

데이터: `data/2026-10-10_robot3_step.csv` (회차별 값)

| n | mean | median | p95 | max | min | 분포 |
| --- | --- | --- | --- | --- | --- | --- |
| 20 | 170 ms | 164 ms | 218 ms | 224 ms | 128 ms | 120–180 ms 12회, 200–230 ms 8회 (두 무리) |

회차별(ms): 128, 215, 141, 169, 204, 131, 215, 139, 129, 159, 140, 224, 201, 131, 218, 143, 176, 202, 131, 212

- 두 무리로 갈리는 것은 로봇 쪽 제어 주기와 명령 도착 시점의 위상 차이로 보임(odom 50 ms 간격에 맞물림). 원인은 미확인.
- **1-2 허용 기준 제안**: cmd_vel→odom p95 ≤ 250 ms. Nav2 컨트롤러 20 Hz(50 ms) 기준 약 4주기 늦으므로 3-3 튜닝 때 `controller_frequency`·`transform_tolerance`에 반영. 초과 시 대응: controller 주기 낮추기 → transform_tolerance 올리기 → 5 GHz 대역.

그래프: `../daily/barlide/img/2026-10-10_robot3_step.png`

### 1-3 cmd_vel 끊김 시 동작

0.2 m/s 직진 중 cmd_vel 발행 프로세스를 `kill -9`로 끊고, odom linear.x가 0이 될 때까지 관찰. 3회.
데이터: `data/2026-10-10_robot3_cmdcut/` (rosbag2 mcap, /robot3/odom 3044건 + /robot3/cmd_vel 995건)

| 회차 | 정지까지 | 정지 위치(시작선 기준) |
| --- | --- | --- |
| 1 | 0.83–0.96 s 범위 | 1.460 m |
| 2 | 〃 | 1.427 m |
| 3 | 〃 | 1.488 m |

- 끊긴 뒤 **약 0.9 s 안에 로봇이 스스로 정지**(Create 3의 cmd_vel 타임아웃). 그동안 **약 13.6 cm**(평균) 더 이동.
- 0.2 m/s에서 14 cm는 장애물 이격 목표 30 cm의 절반 가까이 → 3-5 측정 속도 확정 때 고려.
- 이 구간(약 1.4 m)의 odom도 실측보다 약 1.8 % 적게 셈(1-4와 일치).

그래프·사진: `2026-10-10_robot3_cmdcut.png`, `2026-10-10_cmdcut_marks.jpg`

### 1-4 odom 단독 오차

`odom_check.py`: odom만 보고 2 m 직진 / 360° 회전 후 정지, 바닥 테이프·줄자로 실측값 입력. 각 5회. 데이터: `data/2026-10-10_robot3_odom_check.csv`
회전 실측은 각도기가 없어 범퍼 끝(중심에서 약 17 cm)의 어긋난 거리로 환산: 각도 ≈ atan(mm ÷ 170), 1 mm ≈ 0.34°.

**직진 (목표 2.0 m, 0.2 m/s)**

| 회차 | odom | 실측 | 오차(odom−실측) |
| --- | --- | --- | --- |
| 1 | 2.0431 m | 2.080 m | −3.69 cm |
| 2 | 2.0416 m | 2.084 m | −4.24 cm |
| 3 | 2.0428 m | 2.080 m | −3.72 cm |
| 4 | 2.0395 m | 2.080 m | −4.05 cm |
| 5 | 2.0452 m | 2.085 m | −3.98 cm |
| 평균 ± 표준편차 | | | **−3.94 ± 0.23 cm (−1.9 %)** |

CSV 5번째 줄(실측 2.045 m, 오차 −0.04 cm)은 오측정으로 제외하고 재측정(6번째 줄)을 5회차로 씀.

**회전 (목표 360°)**

| 회차 | odom | 실측 | 오차 |
| --- | --- | --- | --- |
| 1 | 363.82° | 363.4° | +0.42° |
| 2 | 364.76° | 363.0° | +1.76° |
| 3 | 364.68° | 363.4° | +1.28° |
| 4 | 363.99° | 363.0° | +0.99° |
| 5 | 363.47° | 362.0° | +1.47° |
| 평균 ± 표준편차 | | | **+1.18 ± 0.51° (+0.3 %)** |

odom·실측이 모두 360°를 넘는 것은 정지 명령 후 관성으로 더 돈 양(약 3°)이 포함된 것. 오차는 odom과 실측의 차이만 본다.

- 직진은 거리와 상관없이 약 1.8–1.9 % 적게 세는 **반복성 좋은 계통 오차** → 2-2 AMCL 튜닝(odom alpha, 또는 wheel 보정)에 반영.
- 회전 오차 +0.3 %는 목표치(yaw ≤ 5°) 대비 작음.

그래프·사진: `2026-10-10_robot3_odom.png`, `2026-10-10_start_position.jpg`, `2026-10-10_straight_arrival.jpg`, `2026-10-10_straight_error_marks.jpg`, `2026-10-10_rotate_error_marks.jpg`

### 1-5 SLAM 지도

slam_toolbox(sync)로 테스트베드 1회 작성: 해상도 0.05 m, 69×138 px, 주행 공간 약 3.2 × 6.5 m(19.98 m²). RSSI 팀 test_map과 비교: 벽의 99 %가 10 cm 이내로 겹침(평균 0.7 cm, p95 5 cm), 칸막이 3개 위치 동일, 두 지도 사이 회전 0.8°(7 m 끝에서 약 10 cm).
→ **PM 결정(10/10): 기준 지도는 RSSI 팀(성현) 것으로 통일. 주행에서 만든 지도는 배포하지 않음.** 그래프: `2026-10-10_map_compare.png`

### 1-1 Nav2 bringup — robot3 미측정

robot3에서는 이날 Nav2 bringup을 돌리지 않았다(측정은 모두 odom·scan·cmd_vel 직접 구독, 지도는 slam_toolbox). 아래는 같은 기종 robot4로 미니 프로젝트(2026-10-07, 이 PC)에서 Nav2 bringup을 돌린 기록이며, 로봇·launch가 달라 참고값이다.

| 항목 | 값 (robot4, 10/07, 3회) |
| --- | --- |
| 런치 → amcl active | 3.4–5.1 s |
| 도킹 중 bringup | amcl은 active가 되지만 라이다가 꺼져 map TF가 안 나옴. controller_server가 `Timed out waiting for transform from base_link to odom`, `StaticLayer: "map" … does not exist` 반복 → Nav2 lifecycle이 60 s 뒤 기동 포기 |
| 대응 | 언도킹 → 초기 pose 발행 → Nav2 lifecycle RESET·STARTUP 재요청 (navi_pkg `follow_car.wait_active`) |
| 언도킹 + 초기 pose → Nav2 active | 4.2–5.1 s (재기동 없이 성공한 경우) |
| 언도킹 → 카메라·라이다 복귀 | 0.6–0.8 s |

→ 2-1 초기 위치 방식(언도킹 직후 pose를 초기 pose로)은 이 경험에 근거. robot3·robot4에서 실제 Nav2 bringup 시간은 2단계에서 측정해 여기에 추가.

### 남은 일 (리뷰 반영)

- [ ] robot3 Nav2 bringup 시간·결과 측정(도킹/언도킹 각각) — 2-1과 함께
- [ ] robot4로 1-1~1-4 같은 측정 (두 로봇 비교)
- [ ] `latency_check.py`에 step 결과 CSV 저장과 cmd_vel 수신 간격·최대 공백 측정 모드 추가

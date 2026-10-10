# IF-08 {ns}/survey/sample · survey_buffer(로봇 PC) → ros_bridge · network_map_engine(관제 PC)
# NetRaw 에 같은 시각의 AMCL 위치와 seq 를 붙인 것. (robot_id, seq) 로 중복을 거른다.
uint32  seq
builtin_interfaces/Time stamp   # 측정 시각 (NetRaw 의 stamp)
string  robot_id
uint32  run_id                  # 순찰 회차
float32 x                       # map 좌표 [m]
float32 y
float32 yaw                     # [rad]
bool    pose_ok                 # false 면 위치 불확실 → 지도 계산에서 제외 (E5)
bool    resent                  # survey/sync 요청으로 다시 보낸 샘플이면 true
bool    detected                # 이번 스캔에서 핫스팟이 보였는지 (NetRaw 의 값)
int16   rssi_dbm                # 핫스팟 RSSI [dBm]. detected 가 false 면 쓰지 않는다

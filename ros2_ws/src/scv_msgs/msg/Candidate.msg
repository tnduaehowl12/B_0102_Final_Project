# IF-15 /inspection/candidates · network_map_engine → inspection_manager (관제 PC 안)
# 비전 후보(SOURCE_VISION)는 inspection_manager 가 IF-19 판정 결과로 직접 만든다 (이 토픽으로 오지 않음).
# 이상 '후보'. 재검증을 거쳐야 확정된다 (BR-T06).
uint8 SOURCE_NETWORK=1
uint8 SOURCE_VISION=2

uint8 NET_COVERAGE=1            # 커버리지 저하 의심
uint8 NET_UNKNOWN=4             # 판단 불가
uint8 VIS_NOT_DETECTED=11
uint8 VIS_OCCLUDED=12
uint8 VIS_POSITION=13
uint8 VIS_ABNORMAL=14           # 압력·소등·적치

builtin_interfaces/Time stamp
string  candidate_id
string  robot_id                # 후보를 만든 측정·관측을 한 로봇. 재검증은 다른 로봇에 배정 (BR-T06)
uint32  run_id
uint8   source
uint8   kind
string  ref                     # 격자 칸 또는 facility_id
float32 x                       # 재검증하러 갈 위치, map 좌표 [m]
float32 y
float32 yaw                     # [rad]
float32 score                   # 기준선 이탈 정도·신뢰도
string  evidence_ref            # 사진·샘플 범위

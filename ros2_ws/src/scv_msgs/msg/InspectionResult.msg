# IF-19 {ns}/inspect/result · detection_alert(로봇 PC) → inspection_manager · ros_bridge(관제 PC)
# 설비 판정 한 건. InspectFacility 액션도 이 상수를 쓴다.
uint8 KIND_EXTINGUISHER=1       # 소화기 (유무·위치·압력계)
uint8 KIND_SHUTTER=2            # 방화셔터 하강구간
uint8 KIND_EXIT_LIGHT=3         # 비상구 유도등

uint8 NORMAL=0
uint8 NOT_DETECTED=1
uint8 OCCLUDED=2
uint8 POSITION_ANOMALY=3
uint8 ABNORMAL=4                # 압력·소등·적치
uint8 UNCONFIRMED=5             # 자세 보정 3회 뒤에도 판정 못 함 (E6)

builtin_interfaces/Time stamp
string  robot_id
uint32  run_id
string  task_id
string  facility_id             # facilities.yaml
uint8   kind
uint8   verdict
string  detail
string  image_ref               # 로봇 PC 에 저장한 사진
uint8   attempts                # 관측 횟수 1–3

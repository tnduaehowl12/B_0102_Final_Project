# IF-12 {ns}/status · mission_executor(로봇 PC) → inspection_manager · ros_bridge(관제 PC) · 1 Hz
uint8 STATE_IDLE=0
uint8 STATE_EXECUTING=1
uint8 STATE_BLOCKED=2           # 통로 막힘 (E1)
uint8 STATE_DOCKING=3
uint8 STATE_DOCKED=4
uint8 STATE_ESTOP=5             # 비상정지 (E7)
uint8 STATE_ERROR=6

builtin_interfaces/Time stamp
string  robot_id
uint8   state
float32 battery_percent         # 0–100
bool    accepting_tasks         # 배터리 30% 이하이면 false (E2)
string  task_id                 # 수행 중인 작업, 없으면 빈 문자열
uint32  run_id                  # 마지막으로 받은 작업의 회차, 아직 없으면 0 (survey_buffer 가 읽음)
uint8   task_type               # ExecuteTask.Goal 의 type 상수
float32 progress                # 0.0–1.0
float32 x                       # map 좌표 [m]
float32 y
float32 yaw                     # [rad]
bool    pose_ok
string  warning                 # 경고 사유, 없으면 빈 문자열

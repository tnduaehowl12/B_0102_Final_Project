# IF-16 /inspection/alerts · 후보·확정·장애 → 관제 웹
uint8 LEVEL_INFO=0
uint8 LEVEL_WARN=1
uint8 LEVEL_ERROR=2

builtin_interfaces/Time stamp
uint8   level
string  code                    # 예: CANDIDATE, CONFIRMED, CLEARED, KEEPOUT, E1–E8
string  robot_id                # 로봇과 무관하면 빈 문자열
string  ref                     # candidate_id · facility_id · task_id · 격자 칸
string  message
bool    delayed                 # 재연결 뒤 늦게 전달된 알림

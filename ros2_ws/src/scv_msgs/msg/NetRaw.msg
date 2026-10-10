# IF-02 {ns}/survey/raw · rssi_scanner(RPi) → survey_buffer(로봇 PC)
# 핫스팟 RSSI 와 측정 시각만. 위치는 로봇 PC 가 붙인다.
builtin_interfaces/Time stamp   # 측정 시각
string  robot_id                # robot4, robot3
bool    detected                # 이번 스캔에서 핫스팟이 보였는지
int16   rssi_dbm                # 핫스팟 RSSI [dBm]. detected 가 false 면 쓰지 않는다

# IF-02 {ns}/survey/raw · rssi_scanner(RPi) → survey_buffer(로봇 PC)
# 핫스팟 RSSI 와 측정 시각만. 위치는 로봇 PC 가 붙인다.
int16 RSSI_NOT_DETECTED=-100

builtin_interfaces/Time stamp   # 측정 시각
string  robot_id                # robot4, robot3
int16   rssi_dbm                # 핫스팟 미검출이면 RSSI_NOT_DETECTED

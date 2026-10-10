# B_0102_Final_Project

## 브랜치

팀마다 브랜치 하나를 씁니다. 팀 브랜치에는 **그 팀이 쓰는 패키지와 공통 메시지(`scv_msgs`)만** 들어 있습니다. `main` 은 모든 패키지가 들어 있는 통합본입니다.

| 팀 | 브랜치 | 들어 있는 패키지 |
| --- | --- | --- |
| 비전·물리 인프라 | `feature/vision` | `scv_detection`, `scv_msgs` |
| 주행·작업 실행 | `feature/driving` | `scv_nav`, `scv_msgs` |
| 관제·작업 관리 | `feature/control` | `scv_manager`, `scv_monitor`, `scv_msgs` |
| 통신 인프라·RSSI | `feature/survey` | `scv_survey`, `scv_msgs` |
| PM + 통합 | `feature/pm` | `scv_bringup`, `scv_testbed`, `scv_msgs` |
| 통합본 | `main` | 전부 |

- 자기 팀 브랜치에서만 커밋합니다. `main` 에는 PM 이 통합합니다.
- **팀 브랜치에 `main` 을 merge 하지 않습니다** (다른 팀 패키지가 다시 들어옵니다). `scv_msgs` 나 문서가 바뀌면 PM 이 팀 브랜치에 맞춰 넣고, 팀원은 `git pull` 만 하면 됩니다.

## 폴더 구조

```text
B_0102_Final_Project/
├── README.md
├── docs/            문서 (일지 가이드 docs/DAILY_GUIDE.md, 일지 docs/daily/, 아이디어 docs/idea/)
├── scripts/         도구 (scripts/daily.sh)
└── ros2_ws/        ROS 2 워크스페이스 — 빌드는 여기서
    └── src/         ROS 패키지
```

빌드는 `ros2_ws` 안에서 한다. `build/`, `install/`, `log/` 가 그 안에만 생기고 git 에는 올라가지 않는다.

```bash
deactivate 2>/dev/null   # 가상환경(venv)이 켜져 있으면 끈다
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
```

가상환경이 켜진 채 빌드하면 `scv_msgs` 가 `No module named 'em'` 으로 실패한다. 인터페이스 문서는 `docs/interfaces.md`.

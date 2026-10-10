# B_0102_Final_Project

## 브랜치

팀마다 브랜치 하나를 씁니다. **모든 브랜치에 패키지 전체가 들어 있고**(`main` 과 같은 구조), 팀은 자기 패키지만 고칩니다. `main` 은 통합본입니다.

| 팀 | 브랜치 | 이 팀이 고치는 패키지 |
| --- | --- | --- |
| 비전·물리 인프라 | `feature/vision` | `scv_detection` |
| 주행·작업 실행 | `feature/driving` | `scv_nav` |
| 관제·작업 관리 | `feature/control` | `scv_manager`, `scv_monitor` |
| 통신 인프라·RSSI | `feature/survey` | `scv_survey` |
| PM + 통합 | `feature/pm` | `scv_bringup`, `scv_testbed`, `scv_msgs`, 여러 팀이 보는 문서 |
| 통합본 | `main` | (PM 이 팀 브랜치를 합침) |

- 자기 팀 브랜치에서만 커밋합니다. `main` 에는 PM 이 통합합니다.
- 로봇 PC·관제 PC·RPi 는 `main` 으로 돌립니다 (통합 시험도 `main`).
- 처음 한 번: `git config pull.rebase false`
- 다른 팀 패키지와 `scv_msgs`, 여러 팀이 보는 문서(`README.md`, `docs/interfaces.md`, `docs/DAILY_GUIDE.md`)는 팀 브랜치에서 고치지 않습니다. 고칠 것이 있으면 그 팀이나 PM 에게 말합니다.
- `main` 이 바뀌면 PM 이 팀 브랜치에 합쳐 넣습니다. 팀원은 `git pull` 만 하면 됩니다.

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

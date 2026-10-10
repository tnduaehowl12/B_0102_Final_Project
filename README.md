# B_0102_Final_Project
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

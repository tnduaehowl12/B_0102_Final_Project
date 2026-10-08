#!/usr/bin/env bash
# 오늘 일지 준비 / 커밋 (COOP Hub v1.13)
#   scripts/daily.sh [YYYY-MM-DD]        그날(기본 오늘) md + img/ + video/ 를 (없으면) 만든다
#   scripts/daily.sh done [YYYY-MM-DD]   크기·토큰 검사 뒤 docs/daily/<아이디>/ 만 커밋한다 (push는 직접)
#   scripts/daily.sh id <아이디>          GitHub 아이디를 바꾼다
#   --yes (또는 DAILY_YES=1)             묻지 않고 진행 (AI가 대신 돌릴 때). main 브랜치 경고도 넘어간다
set -euo pipefail
YES="${DAILY_YES:-0}"
ARGS=()
for a in "$@"; do
  case "$a" in --yes|-y) YES=1 ;; *) ARGS+=("$a") ;; esac
done
set -- "${ARGS[@]+"${ARGS[@]}"}"
interactive() { [ "$YES" != 1 ] && [ -t 0 ]; }
cd "$(git rev-parse --show-toplevel)"
DAY="$(TZ=Asia/Seoul date +%F)"
LIMIT_MB=5        # 노션에 바로 올라가는 크기
HARD_MB=50        # 이보다 크면 커밋하지 않는다

valid_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; }
valid_day() { [[ "$1" =~ ^20[0-9]{2}-[01][0-9]-[0-3][0-9]$ ]]; }
id_note() {   # GitHub 아이디에는 영문·숫자·- 만 들어간다. 폴더 이름으로는 그래도 쓸 수 있으니 경고만
  [[ "$1" =~ ^[A-Za-z0-9]([A-Za-z0-9]|-[A-Za-z0-9])*$ ]] && return 0
  echo "  (참고) '$1' 에는 GitHub 아이디에 못 쓰는 글자(_ . 또는 -- 등)가 있어요. 오타가 아닌지 확인하세요. 폴더 이름으로는 그대로 써요." >&2
}

ask_id() {
  local guess
  guess="$(git config --get coop.dailyid || true)"
  if [ -z "$guess" ]; then
    guess="$(git config --get user.email | sed -n 's/^\([0-9]*+\)\{0,1\}\([^@]*\)@users\.noreply\.github\.com$/\2/p')"
    if interactive; then
      read -r -p "내 GitHub 아이디 [${guess}]: " ans
      guess="${ans:-$guess}"
    elif [ -z "$guess" ]; then
      echo "아이디가 아직 없어요. 먼저: scripts/daily.sh id <GitHub아이디>" >&2; exit 1
    fi
    valid_id "$guess" || { echo "GitHub 아이디(영문·숫자·-)가 필요해요." >&2; exit 1; }
    id_note "$guess"
    git config coop.dailyid "$guess"
  fi
  echo "$guess"
}

case "${1:-}" in
  id)
    valid_id "${2:-}" || { echo "사용법: scripts/daily.sh id <GitHub아이디> (영문·숫자·-)"; exit 1; }
    id_note "$2"; git config coop.dailyid "$2"; echo "아이디: $2"; exit 0 ;;
esac

MODE=""
if [ "${1:-}" = "done" ]; then MODE=done; shift; fi
if [ -n "${1:-}" ]; then
  valid_day "$1" || { echo "날짜는 YYYY-MM-DD 형식이에요 (예: 자정 넘어 어제 일지면 scripts/daily.sh done 2026-10-07)"; exit 1; }
  DAY="$1"
fi
ID="$(ask_id)"
valid_id "$ID" || { echo "저장된 아이디($ID)가 이상해요: scripts/daily.sh id <GitHub아이디>"; exit 1; }
DIR="docs/daily/$ID"
FILE="$DIR/$DAY.md"

if [ "$MODE" = "done" ]; then
  [ -f "$FILE" ] || { echo "오늘 일지($FILE)가 아직 없어요. 먼저 scripts/daily.sh"; exit 1; }
  branch="$(git rev-parse --abbrev-ref HEAD)"
  case "$branch" in main|master|develop|integration)
    echo "⚠ 지금 브랜치가 '$branch'예요. 일지는 내 브랜치에 올려요."
    if [ "$YES" = 1 ]; then echo "  --yes 라서 그대로 진행해요."
    elif [ -t 0 ]; then read -r -p "그래도 계속할까요? [y/N] " a; [ "$a" = "y" ] || exit 1
    else echo "  묻지 않고 멈췄어요. 내 브랜치로 옮기거나(git switch <내 브랜치>), 정말 여기면 --yes 를 붙이세요."; exit 1
    fi ;;
  esac
  big=0
  while IFS= read -r -d '' f; do
    [ -f "$f" ] || continue
    sz=$(stat -c %s "$f" 2>/dev/null || stat -f %z "$f")
    if [ "$sz" -gt $((HARD_MB*1024*1024)) ]; then
      echo "✖ $f ($((sz/1048576)) MB) — ${HARD_MB} MB 넘는 파일은 저장소에 넣지 않아요. YouTube 링크로 바꿔 주세요."; big=1
    elif [ "$sz" -gt $((LIMIT_MB*1024*1024)) ]; then
      case "$f" in
        */video/*) echo "⚠ $f ($((sz/1048576)) MB) — 허브가 노션 한도에 맞게 줄여서 올려요 (허브에 ffmpeg 없으면 GitHub 링크로). 원본은 저장소에 그대로." ;;
        *)         echo "⚠ $f ($((sz/1048576)) MB) — 그림은 노션에 GitHub 링크로만 들어가요 (${LIMIT_MB} MB 이하면 바로 보임). 줄여서 다시 넣는 것을 권해요." ;;
      esac
    fi
  done < <({ git ls-files -z -o -m --exclude-standard -- "$DIR"; git diff --cached --name-only -z -- "$DIR"; })   # what this commit adds or changes
  [ "$big" = 0 ] || exit 1
  if grep -nE '(ghp_|github_pat_|ntn_|secret_|sk-|AKIA)[A-Za-z0-9_]{10,}' "$FILE" >/dev/null; then
    echo "✖ 일지에 토큰처럼 보이는 문자열이 있어요. 지우고 다시."; exit 1
  fi
  git add -- "$DIR"
  if git diff --cached --quiet -- "$DIR"; then echo "바뀐 것이 없어요."; exit 0; fi
  git commit -m "daily: $DAY $ID" -- "$DIR"
  echo "✔ 커밋했어요. 이제: git push   (허브는 5분 안에 확인해요)"
  exit 0
fi

mkdir -p "$DIR/img" "$DIR/video"
[ -e "$DIR/img/.gitkeep" ] || : > "$DIR/img/.gitkeep"
[ -e "$DIR/video/.gitkeep" ] || : > "$DIR/video/.gitkeep"
if [ -f "$FILE" ]; then
  echo "오늘 일지가 이미 있어요: $FILE"
else
  sed "s/^date: YYYY-MM-DD/date: $DAY/" docs/daily/_template.md > "$FILE"
  echo "만들었어요: $FILE"
fi
echo "그림 → $DIR/img/   영상(짧게, 50 MB 미만) → $DIR/video/   다 쓰면: scripts/daily.sh done"

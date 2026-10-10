#!/usr/bin/env bash
# PM: 일지 양식을 미리 만든다 (COOP Hub v1.15)
#   scripts/daily_prefill.sh <시작일> <끝일> <아이디>[=T번호] ... [옵션]
#     예) scripts/daily_prefill.sh 2026-10-11 2026-10-16 dongjun-lee=T4 jaemin=T4 --team 비전
#   아이디 = 허브 관리 → GitHub 연동 표의 「GitHub 아이디」 (docs/daily/<아이디>/ 폴더 이름)
#   만드는 것: docs/daily/<아이디>/<날짜>.md (_template.md에서 date:, work:만 채움) + img/.keep + video/.keep
#   이미 있는 파일은 절대 덮어쓰지 않는다. 만든 것만 출력한다. --commit 이 없으면 커밋하지 않는다.
#   옵션
#     --work T5        아이디 뒤에 =T번호가 없는 사람의 work: 값 (없으면 양식 값 그대로)
#     --weekdays       토·일은 건너뛴다 (기본: 모든 날)
#     --branch <이름>  그 브랜치에서 만든다 (지금 브랜치가 다르면 바꾼다. 커밋 안 된 변경이 있으면 멈춤)
#     --team <이름>    출력과 커밋 메시지에만 쓰는 이름표
#     --commit         만든 파일만 커밋한다 (push는 직접)
#   허브는 양식 그대로인 파일을 「양식만 있음」(미제출)으로 보고, 노션에 반영하지 않는다.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
TEMPLATE="docs/daily/_template.md"

usage() { sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-1}"; }
valid_id() { [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; }
valid_day() { [[ "$1" =~ ^20[0-9]{2}-[01][0-9]-[0-3][0-9]$ ]] && date -d "$1" +%F >/dev/null 2>&1; }
valid_work() { [[ "$1" =~ ^T[0-9]{1,4}(-[0-9]{1,3})?$ ]]; }

FROM="" TO="" WORK="" BRANCH="" TEAM="" COMMIT=0 WEEKDAYS=0
PEOPLE=()
while [ $# -gt 0 ]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --work) WORK="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --team) TEAM="${2:-}"; shift 2 ;;
    --commit) COMMIT=1; shift ;;
    --weekdays) WEEKDAYS=1; shift ;;
    -*) echo "모르는 옵션: $1" >&2; usage ;;
    *) if [ -z "$FROM" ]; then FROM="$1"; elif [ -z "$TO" ]; then TO="$1"; else PEOPLE+=("$1"); fi; shift ;;
  esac
done
[ -n "$FROM" ] && [ -n "$TO" ] && [ "${#PEOPLE[@]}" -gt 0 ] || usage
valid_day "$FROM" && valid_day "$TO" || { echo "날짜는 YYYY-MM-DD 형식이에요: $FROM $TO" >&2; exit 1; }
[[ "$FROM" < "$TO" || "$FROM" == "$TO" ]] || { echo "시작일($FROM)이 끝일($TO)보다 뒤예요." >&2; exit 1; }
n_days=$(( ( $(date -d "$TO" +%s) - $(date -d "$FROM" +%s) ) / 86400 + 1 ))
[ "$n_days" -le 31 ] || { echo "한 번에 31일까지만 만들어요 (지금 ${n_days}일)." >&2; exit 1; }
[ -z "$WORK" ] || valid_work "$WORK" || { echo "--work 는 T5 또는 T5-2 형식이에요: $WORK" >&2; exit 1; }
[ -f "$TEMPLATE" ] || { echo "$TEMPLATE 이 없어요. 저장소 최상위에서, 양식이 있는 브랜치에서 돌리세요." >&2; exit 1; }

IDS=() WORKS=()
for p in "${PEOPLE[@]}"; do
  id="${p%%=*}"; w=""
  [ "$p" = "$id" ] || w="${p#*=}"
  valid_id "$id" || { echo "GitHub 아이디 형식이 아니에요: $id (영문·숫자·._-)" >&2; exit 1; }
  [ -z "$w" ] || valid_work "$w" || { echo "$id 의 업무 번호는 T5 또는 T5-2 형식이에요: $w" >&2; exit 1; }
  IDS+=("$id"); WORKS+=("${w:-$WORK}")
done

if [ -n "$BRANCH" ]; then
  cur="$(git rev-parse --abbrev-ref HEAD)"
  if [ "$cur" != "$BRANCH" ]; then
    if ! git diff --quiet || ! git diff --cached --quiet; then
      echo "커밋 안 된 변경이 있어서 $BRANCH 로 바꾸지 않았어요. 정리한 뒤 다시 (지금 $cur)." >&2; exit 1
    fi
    git switch -q "$BRANCH" || { echo "$BRANCH 브랜치로 바꾸지 못했어요." >&2; exit 1; }
    echo "브랜치: $BRANCH"
    [ -f "$TEMPLATE" ] || { echo "$BRANCH 에는 $TEMPLATE 이 없어요." >&2; exit 1; }
  fi
fi

CREATED=()
keep() {   # img/ video/ 를 git에 남기는 빈 파일. 이미 .keep 이나 .gitkeep 이 있으면 그대로
  local d="$1"
  mkdir -p "$d"
  if [ ! -e "$d/.keep" ] && [ ! -e "$d/.gitkeep" ]; then : > "$d/.keep"; CREATED+=("$d/.keep"); fi
}
made=0 skipped=0
for i in "${!IDS[@]}"; do
  id="${IDS[$i]}"; w="${WORKS[$i]}"; dir="docs/daily/$id"
  for ((k = 0; k < n_days; k++)); do
    day="$(date -d "$FROM + $k day" +%F)"
    if [ "$WEEKDAYS" = 1 ] && [ "$(date -d "$day" +%u)" -ge 6 ]; then continue; fi
    f="$dir/$day.md"
    if [ -e "$f" ]; then
      echo "  이미 있어요 (그대로 둠): $f"; skipped=$((skipped + 1)); continue
    fi
    mkdir -p "$dir"
    if [ -n "$w" ]; then
      sed -e "s/^date:[[:space:]]*YYYY-MM-DD/date: $day/" -e "s/^work:[[:space:]]*[^[:space:]#]*/work: $w/" "$TEMPLATE" > "$f"
    else
      sed -e "s/^date:[[:space:]]*YYYY-MM-DD/date: $day/" "$TEMPLATE" > "$f"
    fi
    CREATED+=("$f"); made=$((made + 1))
    echo "  만들었어요: $f${w:+ (work: $w)}"
  done
  keep "$dir/img"; keep "$dir/video"
done
echo "${TEAM:+[$TEAM] }일지 양식 ${made}개 만듦, 이미 있던 ${skipped}개는 그대로 ($FROM ~ $TO, ${#IDS[@]}명)"
[ -n "$WORK" ] || for w in "${WORKS[@]}"; do [ -n "$w" ] || { echo "  (참고) work: 를 안 준 사람은 양식 값 그대로예요. 아이디=T5 또는 --work T5 로 채울 수 있어요."; break; }; done

if [ "$COMMIT" = 1 ]; then
  if [ "${#CREATED[@]}" -eq 0 ]; then echo "새로 만든 파일이 없어 커밋하지 않았어요."; exit 0; fi
  git add -- "${CREATED[@]}"
  git commit -q -m "daily: 일지 양식 미리 만들기 ${TEAM:+$TEAM }$FROM~$TO (${made}개)" -- "${CREATED[@]}"
  echo "✔ 커밋했어요 ($(git rev-parse --short HEAD)). 이제: git push"
else
  echo "커밋은 하지 않았어요. 확인 뒤 직접: git add docs/daily && git commit -m \"daily: 일지 양식\""
fi

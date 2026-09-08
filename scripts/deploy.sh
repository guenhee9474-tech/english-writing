#!/usr/bin/env bash
# 커밋 → GitHub 푸시(Pages) → Apps Script 푸시 → 기존 웹 앱 배포 갱신. 사용: bash scripts/deploy.sh "바꾼 내용"
set -e
cd "$(dirname "$0")/.."
MSG="${1:-update $(date +%Y-%m-%d_%H:%M)}"

echo "▶ 1/3 GitHub (Pages)"
git add -A
git commit -m "$MSG" >/dev/null 2>&1 && echo "   커밋: $MSG" || echo "   커밋할 변경 없음"
git push

echo "▶ 2/3 Apps Script push"
cd gas
[ -f .clasp.json ] || { echo "   gas/.clasp.json 이 없습니다. CLAUDE.md의 '처음 설정' 5번을 먼저 하세요."; exit 1; }
npx @google/clasp push -f

echo "▶ 3/3 웹 앱 재배포 (주소 유지)"
DEP_ID="$(tr -d '[:space:]' < .deployment-id 2>/dev/null || true)"
if [ -z "$DEP_ID" ]; then
  echo "   gas/.deployment-id 가 비어 있습니다. 'npx @google/clasp list-deployments' 결과 중 학생 페이지 주소에 든 ID를 넣으세요."; exit 1
fi
npx @google/clasp deploy -i "$DEP_ID" -d "$MSG"
echo "완료. Pages 반영은 최대 10분, Safari는 주소 뒤 ?v=숫자 로 새로고침."

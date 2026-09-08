#!/usr/bin/env bash
# 처음 한 번: clasp 설치·로그인, 스크립트 연결. 사용: bash scripts/setup.sh <스크립트ID>
set -e
cd "$(dirname "$0")/.."
SCRIPT_ID="$1"
command -v node >/dev/null || { echo "Node.js가 없습니다. https://nodejs.org 에서 LTS를 설치하세요."; exit 1; }
command -v git  >/dev/null || { echo "Git이 없습니다. https://git-scm.com 에서 설치하세요."; exit 1; }
echo "▶ clasp 설치"; npm install -g @google/clasp >/dev/null
echo "▶ Apps Script API가 켜져 있어야 합니다: https://script.google.com/home/usersettings"
echo "▶ 구글 로그인 (브라우저가 열립니다. 스크립트를 만든 계정으로 로그인)"; npx @google/clasp login
[ -n "$SCRIPT_ID" ] || { read -r -p "스크립트 ID (Apps Script 편집기 → 프로젝트 설정 → ID): " SCRIPT_ID; }
printf '{ "scriptId": "%s", "rootDir": "." }\n' "$SCRIPT_ID" > gas/.clasp.json
echo "▶ 배포 목록 (학생 페이지 주소에 든 ID가 gas/.deployment-id 와 같아야 합니다)"
( cd gas && npx @google/clasp list-deployments )
echo "현재 .deployment-id: $(cat gas/.deployment-id)"
pip install -r tests/requirements.txt >/dev/null 2>&1 && python -m playwright install chromium >/dev/null 2>&1 && echo "▶ 테스트 도구 설치됨" || echo "▶ (선택) 테스트 도구 설치 실패 — Python 3 필요"
echo "설정 끝. 배포는 bash scripts/deploy.sh \"설명\""

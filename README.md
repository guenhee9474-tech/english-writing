# 영어 쓰기 수행평가 작성 페이지 — 개발 세트

학생용 페이지(`docs/index.html`)와 서버(`gas/Code.gs`)를 **한 폴더에서** 고치고, 테스트하고, 한 번에 배포하기 위한 세트입니다.
이 폴더를 VS Code에서 열고 Claude Code에게 말하면, 붙여넣기 없이 "고쳐 줘 → 확인"으로 끝납니다.
프로젝트의 구조와 규칙은 `CLAUDE.md`에 적혀 있고 Claude Code가 먼저 읽습니다.

## 0. 한 번만 설치할 것 (30분)

1. **VS Code** — https://code.visualstudio.com
2. **Git** — Windows: https://git-scm.com/downloads/win (설치 옵션은 기본값). Mac: 터미널에서 `git`을 치면 설치 안내가 뜹니다.
3. **Node.js LTS** — https://nodejs.org (clasp가 필요로 함)
4. **Python 3** — https://www.python.org (자동 테스트용. Windows 설치 시 "Add to PATH" 체크)
5. **Claude Code**
   - Mac 터미널: `curl -fsSL https://claude.ai/install.sh | bash`
   - Windows PowerShell: `irm https://claude.ai/install.ps1 | iex`
   - 설치 후 터미널에서 `claude`를 실행하고 Claude 계정(Pro/Max)으로 로그인
6. **VS Code 확장** — VS Code에서 `Ctrl+Shift+X`(Mac `Cmd+Shift+X`) → "Claude Code" 검색 → 설치. (이 폴더를 열면 추천 확장으로도 뜹니다.)

## 1. 폴더 준비 (5분)

이미 GitHub 저장소(GitHub Pages로 학생 페이지를 올리던 곳)가 있으니, 그 저장소를 내 컴퓨터로 받아 온 뒤 이 세트를 덮어씁니다.

```bash
git clone https://github.com/<아이디>/<저장소이름>.git english-writing
cd english-writing
# 이 zip의 내용물(docs, gas, tests, scripts, CLAUDE.md, README.md, .gitignore, .vscode)을 이 폴더에 복사
```

GitHub 저장소 설정 → Pages → Branch `main`, 폴더를 **`/docs`** 로 바꿉니다. (전에 루트에 있던 `index.html`은 지웁니다.)

## 2. VS Code에서 Claude Code 시작 (처음 한 번)

VS Code로 `english-writing` 폴더를 열고, 터미널(`Ctrl+``)에서 `claude`를 실행한 뒤 이렇게 말합니다.

> CLAUDE.md의 "처음 설정"을 진행해 줘. 스크립트 ID는 ○○○이야.

스크립트 ID는 Apps Script 편집기 → 왼쪽 톱니(프로젝트 설정) → "스크립트 ID"에 있습니다.
Claude Code가 clasp 설치, 구글 로그인(브라우저가 열림), 스크립트 연결, 배포 ID 확인, 테스트, 첫 배포까지 순서대로 진행하고 필요한 것만 묻습니다.
중간에 https://script.google.com/home/usersettings 에서 **Google Apps Script API 사용**을 켜 달라고 하면 켜 주세요.

## 3. 평소에 쓰는 법

VS Code 터미널에서 `claude`를 열고 자연어로 말하면 됩니다. 예:

- "Word Bank에 'take part in'을 추가해 줘"
- "초안 시간을 25분으로 바꿔 줘"
- "초안 PDF가 안 만들어져. 오류 탭 보고 고쳐 줘"
- "테스트 돌리고 배포해 줘"

배포만 직접 하려면: `bash scripts/deploy.sh "무엇을 바꿨는지"`
테스트만: `python tests/mocktest.py` (마지막 줄 PASS 확인)

## 4. 어디에 무엇이 있나

```
english-writing/
├─ docs/index.html      학생 페이지 (GitHub Pages가 이 폴더를 서빙)
├─ gas/Code.gs          Apps Script 서버
├─ gas/appsscript.json  Apps Script 매니페스트
├─ gas/.deployment-id   웹 앱 배포 ID (학생 페이지 주소에 든 ID와 같아야 함)
├─ tests/mocktest.py    브라우저 자동 테스트
├─ scripts/deploy.sh    커밋·푸시·clasp 푸시·재배포 한 번에
├─ scripts/setup.sh     처음 설정을 손으로 할 때
└─ CLAUDE.md            Claude Code가 읽는 프로젝트 설명서
```

## 5. 주의

- `gas/.clasp.json`(스크립트 ID)과 구글 로그인 정보는 git에 올라가지 않습니다(.gitignore).
- 저장소가 공개라 `docs/index.html` 안의 교사 PIN·token은 누구나 볼 수 있습니다. 실수 방지용으로만 생각하세요.
- 수업 당일 아침에는 배포하지 않습니다. 전날 배포하고 아이패드로 로그인 화면 아래 버전 표시를 확인하세요.

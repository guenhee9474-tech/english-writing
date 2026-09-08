# 영어 쓰기 수행평가 작성 페이지 — 프로젝트 안내 (Claude Code용)

고등학교 1학년 영어 쓰기 수행평가를 학생 아이패드(디벗)에서 치르는 웹앱이다.
사용자는 영어 교사이며 개발자가 아니다. **항상 한국어로 답하고**, 명령을 실행하기 전에 무엇을 하는지 한 줄로 말한다.
"고쳐 줘 → 확인" 두 단계로 끝나는 것이 목표다. 사용자가 파일을 복사·붙여넣기 하게 만들지 않는다.

## 구성 (파일 두 개가 전부)

| 경로 | 역할 | 배포 |
|---|---|---|
| `docs/index.html` | 학생용 페이지. HTML+CSS+JS 한 파일. 외부 라이브러리 없음. | GitHub Pages (`main` 브랜치의 `/docs` 폴더) |
| `gas/Code.gs` | Google Apps Script 웹 앱. 저장·PDF·시트·사전. | `clasp push` → `clasp deploy -i <배포ID>` |

- `gas/appsscript.json` 매니페스트(V8, 웹앱: 나로 실행, 모든 사용자 접근). `gas/.clasp.json`은 스크립트 ID(설정 때 생성, git 제외).
- `gas/.deployment-id` 웹 앱 배포 ID. 이 ID로 재배포해야 학생 페이지에 박힌 주소가 그대로 유지된다. **새 배포를 만들지 말 것.**
- `tests/mocktest.py` 서버를 흉내 내는 브라우저 자동 테스트(Playwright). 페이지를 고치면 반드시 돌린다.
- `scripts/deploy.sh` 커밋·푸시·clasp 푸시·재배포를 한 번에.

## 두 회차 흐름 (단계 = state.phase)

`research`(조사·브레인스토밍, 외부 접속 허용) → 학생이 "초안 쓰기 시작" → `draft`(잠금) → 초안 제출 → `draftDone`
→ 다음 로그인 때 `final`(Step 1~3 읽기 전용, Step 4만 입력, 잠금) → 최종 제출 → `done`.
어느 단계를 열지는 서버에 저장된 학생 상태로 자동 결정된다. 회차 설정 같은 것은 없다.
단계별 제한 시간은 `CONFIG.phases`(조사 15 / 초안 20 / 최종 20분). 주소 뒤 `?r=&d=&f=`로 덮어쓸 수 있다.

## 신원과 저장

- 학번+이름이 ID. 첫 로그인 때 서버가 **기기 열쇠**(무작위)를 발급해 localStorage(`czkey:<학번>`)에 보관. 이후 모든 읽기·쓰기·사전 요청에 `key`가 붙고, 서버는 학번+열쇠가 맞는 줄만 다룬다.
- 같은 학번이 열쇠 없이 들어오면 기존 줄을 건드리지 않고 "중복" 표시된 새 줄을 만든다. 기기 교체는 시트에서 그 학생의 [기기열쇠] 칸을 지우면 다음 로그인 기기가 이어받는다.
- 작성 중 60초마다(`CONFIG.autosaveSec`) 서버에 자동 저장(`phase=save`). 초안 제출(`phase=draft`)과 최종 제출(`phase=final`)은 별도.
- 서버가 더 앞선 단계를 갖고 있으면 서버 것을 쓴다(`pickState`). 늦게 도착한 자동 저장이 단계를 되돌리지 못한다(`PHASE_ORDER`).

## 통신 방식 (바꾸지 말 것)

- 페이지 → 서버 쓰기: `fetch(scriptUrl, {method:"POST", mode:"no-cors", body: URLSearchParams})`. 응답을 읽을 수 없으므로 저장 직후 `action=check`로 읽어서 확인한다.
- 페이지 → 서버 읽기: **JSONP**(`<script src=...&callback=cb>`). Apps Script는 CORS 헤더를 주지 않으므로 fetch로 바꾸면 깨진다. 액션: `load`, `check`, `dict`.
- `token`은 소스에 보이는 값이라 보안 수단이 아니다(실수 방지용).

## 서버 시트 (제출명단 스프레드시트, 제출물 폴더 안)

| 탭 | 내용 |
|---|---|
| 제출명단 | 최종 제출 한 줄씩 (제출시각·학번·이름·문장수·표현수·이탈·한글·자동집계·파일·중복·열쇠) |
| 초안 | 학생 상태. 열 순서는 `DRAFT_HEADER`/`COL`에 고정. 헤더가 다르면 `초안_old_…`로 이름을 바꾸고 새로 만든다. 열을 추가하면 `DRAFT_HEADER`, `COL`, `draftSheet()`의 헤더 검사, `saveDraft` 세 곳을 같이 고친다. |
| 사전 | 단어 사전 조회 기록 |
| 총괄 / 반별 요약 | `rebuildOverview()`가 다시 쓴다. 초안·최종 제출 때 자동 갱신. "명단" 탭(학번, 이름)이 있으면 미접속 학생도 표시 |
| 오류 | `logError()`가 남기는 실패 기록. **문제가 생기면 여기부터 본다.** |

PDF는 `savePdf(d, "draft"|"final")`가 만든다. 반 폴더(`103반`) 안, 초안은 그 아래 `초안/`. 파일명 `학번_이름[_초안][_중복]_날짜.pdf`.
PDF 하이라이트 규칙(Word Bank 정규식)은 페이지가 제출 때 `bank`로 보내며 서버는 그것을 그대로 쓴다. 서버에 Word Bank 복사본을 두지 않는다.
`regeneratePdf("학번","draft"|"final")`은 시트 내용으로 PDF를 다시 만든다. 오류가 삼켜지지 않으므로 진단에 쓴다.

## 페이지 쪽 규칙

- 설정은 `docs/index.html` 안 `CONFIG` 한 곳. 내용(예시문, Word Bank, 단계 안내, 시간)은 여기만 고친다.
- 페이지를 고치면 `CONFIG.version`을 오늘 날짜로 올린다(로그인 화면 아래에 표시되어 캐시 확인에 쓴다).
- 잠금 단계(`draft`, `final`)에서만 이탈 기록·한글 선택 차단·사전 버튼이 활성화된다(`lockActive()`).
- iPad Safari는 글자 칸을 누르면 전체 화면이 풀리므로 iOS에서는 전체 화면을 강제하지 않는다(`ENV.ios`). 되돌리지 말 것.
- 창 blur는 1.2초 뒤에도 포커스가 없을 때만 이탈로 센다(키보드·글자 칸 탭 오인식 방지).
- 영어 칸에서는 붙여넣기, 자동 수정(`insertReplacementText`), 여러 글자 삽입(예측 텍스트 수락)을 `beforeinput`에서 막고 센다.
- 학생 글은 항상 `escapeHtml`로 표시한다.
- 학생 비밀번호(리로스쿨 등)를 입력받는 기능은 만들지 않는다.

## 명령

```bash
# 테스트 (페이지 수정 후 필수)
pip install -r tests/requirements.txt && python -m playwright install chromium   # 처음 한 번
python tests/mocktest.py

# 배포 (커밋 → GitHub Pages → clasp push → 기존 배포 갱신)
bash scripts/deploy.sh "무엇을 바꿨는지 한 줄"

# Apps Script만
cd gas && npx @google/clasp push -f && npx @google/clasp deploy -i "$(cat .deployment-id)" -d "설명"

# 서버 상태 확인
cd gas && npx @google/clasp list-deployments     # 배포 목록
cd gas && npx @google/clasp open-script           # 편집기 열기 (오류 탭 확인, testSubmit 실행 등)
```

GitHub Pages 반영은 최대 10분, Safari 캐시는 주소 뒤 `?v=숫자`로 우회. 수업 당일 아침에는 배포하지 않는다.

## 처음 설정 (사용자가 "첫 설정 진행해 줘"라고 하면 이 순서대로)

1. `node -v`, `git -v`, `python3 --version` 확인. 없으면 설치 안내(Node LTS, Git for Windows/Xcode CLT, Python 3).
2. `npm install -g @google/clasp`
3. 사용자에게 https://script.google.com/home/usersettings 에서 **Google Apps Script API를 "사용"으로** 켜 달라고 한다(없으면 clasp가 실패한다).
4. `npx @google/clasp login` — 브라우저가 열리고 사용자가 스크립트를 만든 구글 계정으로 로그인한다.
5. 사용자에게 **스크립트 ID**를 묻는다(Apps Script 편집기 → 왼쪽 톱니 "프로젝트 설정" → ID). `gas/.clasp.json`을 `{"scriptId":"…","rootDir":"."}`로 만든다.
6. `cd gas && npx @google/clasp list-deployments`로 배포 목록을 보여 주고, 학생 페이지 주소(`docs/index.html`의 `CONFIG.submit.scriptUrl`)에 들어 있는 ID와 같은 배포 ID가 `gas/.deployment-id`에 있는지 확인한다. 다르면 사용자에게 확인 후 파일을 고친다.
7. `git remote -v`로 GitHub 저장소가 연결되어 있는지 본다. 없으면 사용자의 저장소 주소를 물어 `git remote add origin …`. 저장소 설정 → Pages → 폴더를 `/docs`로 바꿔 달라고 안내한다(기존에 루트의 index.html로 쓰고 있었으면 그 파일은 지운다).
8. `pip install -r tests/requirements.txt && python -m playwright install chromium` 후 `python tests/mocktest.py`가 통과하는지 확인.
9. `bash scripts/deploy.sh "첫 설정"`으로 배포. 끝나면 사용자에게 학생 페이지를 열어 로그인 화면 아래 버전 글자를 확인해 달라고 한다.

## 문제가 생겼을 때

1. 제출명단 파일의 **오류** 탭을 본다(`npx @google/clasp open-script` → 편집기 → 실행 로그도 함께).
2. PDF 문제는 편집기에서 `regeneratePdf("학번","draft")`를 실행해 실제 오류 메시지를 본다.
3. 제출명단 파일이 안 보이면 `whereIsLogSheet()`, 그래도 아니면 `relinkLogSheet()`.
4. 학생 화면이 옛 버전이면 `CONFIG.version` 표시를 확인하고 캐시/Pages 반영을 의심한다.

## 보류된 과제 (사용자와 상의 후 진행)

- 보안: 페이지 소스에 교사 PIN과 token이 보인다. 교사 기능을 서버 검증으로 옮기고 요청별 총량 제한을 두는 작업이 남아 있다.
- 리로스쿨 등 학교 계정과의 연동(OAuth/LTI)은 업체 답변 대기 중. 학교 구글 계정이 있으면 구글 로그인이 대안.
- 학생 기기의 예측 텍스트·자동 수정은 MDM 제한 프로필로 끄는 것이 근본 해결.

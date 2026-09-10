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
- 자동 저장은 `buildLiveMeta()`를 보낸다. **이탈·한글·대량·사전 횟수가 여기 들어가야 수업 중 총괄에 보인다.** 이름표는 `buildMeta`와 똑같이 맞춰야 서버 정규식이 읽는다. 이탈이 생기면 `flushSoon()`이 60초를 기다리지 않고 바로 보낸다(10초에 한 번 제한).
- 작성 중 60초마다(`CONFIG.autosaveSec`) 서버에 자동 저장(`phase=save`). 초안 제출(`phase=draft`)과 최종 제출(`phase=final`)은 별도.
- 열쇠가 없으면 서버가 모든 쓰기를 거절한다(`NO_KEY`). 페이지는 이때 저장을 시도하지 않고 학생에게 배너로 알린다.
- 서버가 더 앞선 단계를 갖고 있으면 서버 것을 쓴다(`pickState`는 페이지 쪽). 늦게 도착한 자동 저장은 **단계 칸만** 그대로 두고 글은 저장한다(`PHASE_ORDER`, `saveDraft`). 저장 전체를 버리면 교사가 "제출 취소"로 되돌린 뒤 다시 쓴 글이 사라진다.

## 통신 방식 (바꾸지 말 것)

- **모든 요청은 `credentials:"omit"` 으로 보낸다. 이것이 이 프로젝트에서 가장 중요한 규칙이다.**
  쿠키를 보내면 구글이 계정을 고르려고 주소를 `/macros/u/1/s/...` 로 바꾸고, 그 계정에 권한이 없으면 "파일을 열 수 없습니다"가 뜨면서 **아무것도 동작하지 않는다**(2026-09-10 실제로 겪음). 구글 계정이 두 개 이상 로그인된 기기에서 발생한다. 쿠키를 안 보내면 익명 요청이 되어 이 문제가 아예 없다.
- 페이지 → 서버 쓰기: `sendToServer(body)` — `fetch(scriptUrl, {method:"POST", credentials:"omit", body})`. **응답을 읽을 수 있다**(`OK_SAVE`/`OK_DRAFT`/`OK`/`OK_REOPEN`, 실패는 `NO_KEY`/`UNKNOWN_KEY`/`BAD_TOKEN`/`BAD_PHASE`/`ERROR`). 실패 답이 오면 곧바로 실패로 처리하고, 답을 못 읽었을 때만 `action=check`로 확인한다.
  `keepalive` 는 64KB 상한이 있어 본문이 크면 끄고 보낸다.
- **확인은 반드시 `check`의 `draftAt`([초안제출시각] 칸)과 `phase`를 함께 본다.** `[저장시각]`(`COL.at`)을 쓰면 60초마다 도는 자동 저장 때문에 제출이 실패해도 항상 성공으로 보인다. `tests/mocktest.py`의 T0가 이것을 검사한다.
- `phase` 값: `save`(자동 저장) / `draft` / `final` / `reopen`(교사 제출 취소, `to=`로 되돌릴 단계). 그 밖의 값은 서버가 `BAD_PHASE`로 거절한다.
- 페이지 → 서버 읽기: `askServer(params)` — 쿠키 없는 `fetch`. **Apps Script 는 CORS 를 허용한다**(2026-09-10 실측: `r.type === "cors"`, 본문 읽힘). `callback` 이 없으면 서버가 그냥 JSON 을 돌려준다.
  JSONP(`<script src=…&callback=cb>`)는 **예비 수단으로만** 남아 있다. `<script>` 태그는 쿠키를 함께 보내므로 위 문제가 그대로 재현된다. 되돌리지 말 것. 테스트가 JSONP 로 새는지 검사한다.
  액션: `load`, `check`, `dict`, `monitor`(교사 현황 화면).
- `token`은 소스에 보이는 값이라 보안 수단이 아니다(실수 방지용).

## 서버 시트 (제출명단 스프레드시트, 제출물 폴더 안)

| 탭 | 내용 |
|---|---|
| 제출명단 | 최종 제출 한 줄씩 (제출시각·학번·이름·문장수·표현수·이탈·한글·자동집계·파일·중복·열쇠) |
| 초안 | 학생 상태. 열 순서는 `DRAFT_HEADER`/`COL`에 고정. 헤더가 다르면 `초안_old_…`로 이름을 바꾸고 새로 만든다. 열을 추가하면 `DRAFT_HEADER`, `COL`, `draftSheet()`의 헤더 검사, `saveDraft` 세 곳을 같이 고친다. |
| 사전 | 단어 사전 조회 기록. [확인] 칸에 되돌림 검증 결과가 남는다 |
| 총괄 / **반별 탭** / 반별 요약 | `rebuildOverview()`가 다시 쓴다. 반마다 탭이 하나씩 생긴다(`1학년 3반` …). 수업 들어가서 그 반 탭만 본다. 그리는 것은 `writeStatusSheet()` 한 곳이고, 색 규칙은 `leaveColor`/`strictColor`/`dictColor`/`countColor`. 열 위치가 어긋나면 엉뚱한 색이 찍히므로 `HEAD` 와 본문 배열을 함께 고친다(테스트 T0b가 검사). **저절로 갱신된다** — 학생 요청이 들어온 김에 `maybeRebuildOverview()`가 다시 쓴다. 마지막 갱신에서 `OV_INTERVAL_SEC`(60초)이 지났을 때만 돌므로, 30명이 몰려도 그 중 한 명의 요청만 비용을 낸다. 그 요청은 몇 초 길어지지만 `no-cors`라 학생 화면은 기다리지 않는다. **`ScriptApp`(시간 트리거)은 쓰지 않는다** — 웹 앱에 `script.scriptapp` 권한이 없어 매번 실패한다(2026-09-09 실제로 겪음). `rebuildOverview()`는 잠금을 잡지 않는다(갱신 몇 초 동안 학생 저장이 줄을 서지 않게). 수업이 없으면 아무것도 돌지 않는다. **선생님이 켜고 끌 것은 없다.** 총괄이 안 바뀌면 `resetOverviewSchedule()` 한 번. 새 권한이 필요한 API(트리거·UrlFetch 등)를 넣으면 사용자가 웹 앱을 다시 승인해야 하므로 수업 전에는 넣지 않는다. "명단" 탭(학번, 이름)이 있으면 미접속 학생도 표시 |
| 오류 | `logError()`가 남기는 실패 기록. **문제가 생기면 여기부터 본다.** |

PDF는 `savePdf(d, "draft"|"final")`가 만든다. 반 폴더(`103반`) 안, 초안은 그 아래 `초안/`. 파일명 `학번_이름[_초안][_중복]_날짜.pdf`.
PDF 하이라이트 규칙(Word Bank 정규식)은 페이지가 제출 때 `bank`로 보내며 서버는 그것을 그대로 쓴다. 서버에 Word Bank 복사본을 두지 않는다.
`regeneratePdf("학번","draft"|"final"[,"열쇠앞부분"])`은 시트 내용으로 PDF를 다시 만든다. 오류가 삼켜지지 않으므로 진단에 쓴다.
같은 학번 줄이 여러 개면 세 번째 값으로 지정해야 한다. 저장된 최종본이 비어 있거나 JSON이 깨져 있으면 만들지 않고 멈춘다(멀쩡한 PDF 링크를 지우지 않기 위해).
`savePdf`는 파일 **목록**을 돌려준다(`savePdf(d,"draft")[0]`). Word(.docx) 내보내기는 새 권한 승인이 필요해서 넣지 않았다.

## 페이지 쪽 규칙

- 설정은 `docs/index.html` 안 `CONFIG` 한 곳. 내용(예시문, Word Bank, 단계 안내, 시간)은 여기만 고친다.
- 페이지를 고치면 `CONFIG.version`을 오늘 날짜로 올린다(로그인 화면 아래에 표시되어 캐시 확인에 쓴다).
- 잠금 단계(`draft`, `final`)에서만 이탈 기록·한글 선택 차단·사전 버튼이 활성화된다(`lockActive()`).
- iPad Safari는 글자 칸을 누르면 전체 화면이 풀리므로 iOS에서는 전체 화면을 강제하지 않는다(`ENV.ios`). 되돌리지 말 것.
- 창 blur는 1.2초 뒤에도 포커스가 없을 때만 이탈로 센다(키보드·글자 칸 탭 오인식 방지).
- 영어 칸에서는 붙여넣기, 자동 수정(`insertReplacementText`), 여러 글자 삽입(예측 텍스트 수락)을 `beforeinput`에서 막고 센다.
- 학생 글은 항상 `escapeHtml`로 표시한다.
- 칸을 새로 만들거나 값을 채운 뒤에는 `seedField()`로 기준값을 다시 심는다. 빼먹으면 새로고침 뒤 첫 글자가 "대량 입력"·"한글 입력"으로 잘못 기록된다.
- 문장 수는 어디서나 `splitSentences()` 한 가지 기준으로 센다(`draftSentenceCount()` 포함).
- 학생 비밀번호(리로스쿨 등)를 입력받는 기능은 만들지 않는다.

## 사전 (구글 번역)

`LanguageApp.translate` 는 문맥 없는 단어 하나에 약하다. "배고픈" → "empty" 가 실제로 나왔다(2026-09-10).
`dictTranslate(q)` 가 보완한다: 원래 단어로 먼저 번역 → 결과를 되돌려 `sameWord()` 로 확인 → 안 맞으면 `koBaseForm(q)`(배고픈→배고프다)로 재시도.
원래 단어를 먼저 확인하고 통과하면 멈추므로 명사에 기본형 규칙이 잘못 걸려도(손→소다) 쓰이지 않는다. `trCached()` 가 6시간 보관해 호출을 줄인다.
확인이 안 된 뜻은 학생 화면에 경고가 붙는다. **신뢰도를 직접 보려면 편집기에서 `testDict()` 를 실행**하고 실행 로그의 표를 본다.

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

## 수업 전 점검

회차마다 할 일은 없다. 코드를 고쳤을 때만 아래를 한다.

1. `python tests/mocktest.py` → 마지막 줄 PASS.
2. 아이패드 한 대로 로그인해 화면 아래 버전 글자가 `CONFIG.version`과 같은지 확인.
3. 수업 중 문제가 보이면 제출명단 파일의 **오류** 탭을 먼저 본다. 잠금 실패·PDF 실패·시트 기록 실패·이름 불일치·JSON 초과·총괄 갱신 실패가 모두 여기 남는다.

총괄 시트는 학생이 쓰기 시작하면 1~2분 간격으로 저절로 갱신된다. 9반 18회차 동안 손댈 것이 없다.

## 보류된 과제 (사용자와 상의 후 진행)

- 보안: 페이지 소스에 교사 PIN과 token이 보인다. 교사 기능을 서버 검증으로 옮기고 요청별 총량 제한을 두는 작업이 남아 있다. PIN 은 6202(2026-09-09 변경). 저장소가 공개라 소스에 보이므로 실수 방지용으로만 본다.
- 리로스쿨 등 학교 계정과의 연동(OAuth/LTI)은 업체 답변 대기 중. 학교 구글 계정이 있으면 구글 로그인이 대안.
- 학생 기기의 예측 텍스트·자동 수정은 MDM 제한 프로필로 끄는 것이 근본 해결.

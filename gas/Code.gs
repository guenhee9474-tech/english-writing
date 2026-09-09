/**
 * 영어 쓰기 수행평가 - 제출물 받기
 * 학생이 작성 페이지에서 "제출"을 누르면 이 스크립트가 받아서
 *   1) 구글 문서를 만들고  2) PDF(또는 Word)로 변환해  3) 지정한 드라이브 폴더에 올리고
 *   4) 명단 시트에 한 줄 기록합니다. (메일 발송은 선택)
 *
 * ── 먼저 폴더 준비 ────────────────────────────────────────
 * 공유 드라이브(또는 공유한 일반 폴더)에 제출물 폴더를 하나 만들고 그 폴더를 엽니다.
 * 주소창이 https://drive.google.com/drive/folders/1AbC...xyz 이면 folders/ 뒤의 긴 문자열이 폴더 ID입니다.
 * 공유 드라이브라면 이 스크립트를 실행하는 계정이 "콘텐츠 관리자" 또는 "기여자"여야 파일을 올릴 수 있습니다.
 *
 * ── 설치 방법 ─────────────────────────────────────────────
 * 1. script.google.com 접속 → "새 프로젝트"
 * 2. 편집기의 기존 코드를 모두 지우고 이 파일 내용을 붙여넣기
 * 3. 아래 CFG 의 folderId 에 위에서 복사한 폴더 ID를 넣기 (나머지는 그대로 두어도 됩니다)
 * 4. 오른쪽 위 "배포" → "새 배포" → 유형 선택(톱니바퀴) → "웹 앱"
 *      다음 사용자 인증 정보로 실행: 나
 *      액세스 권한이 있는 사용자: 모든 사용자      ← 반드시 이것
 *    → "배포" → 권한 검토 → 계정 선택 → "고급" → "...(안전하지 않음)으로 이동" → 허용
 *    (본인이 만든 스크립트라 뜨는 경고입니다.)
 * 5. 나오는 "웹 앱 URL"(https://script.google.com/macros/s/.../exec)을 복사
 * 6. 작성 페이지 HTML의 CONFIG.submit.scriptUrl 에 붙여넣고 CONFIG.submit.token 을 아래 CFG.token 과 똑같이 맞춘 뒤
 *    GitHub에 다시 업로드
 *
 * ── 코드를 고친 뒤에는 ────────────────────────────────────
 * "배포" → "배포 관리" → 연필(수정) → 버전 "새 버전" → "배포"를 눌러야 반영됩니다. URL은 그대로입니다.
 *
 * ── 기기 열쇠 ────────────────────────────────────────────
 * 학생이 처음 로그인하면 서버가 무작위 열쇠를 만들어 그 기기에만 저장합니다. 이후 모든 읽기·쓰기는 학번+열쇠가 맞아야 합니다.
 * 같은 학번이 열쇠 없이(다른 기기에서) 들어오면 기존 줄을 건드리지 않고 "중복" 표시가 된 새 줄에 따로 저장합니다.
 * 기기가 바뀐 학생: "초안" 탭에서 그 학생 줄의 [기기열쇠] 칸을 지우세요. 다음에 로그인하는 기기가 그 줄을 이어받습니다.
 *
 * ── 총괄 시트 ────────────────────────────────────────────
 * 제출명단 파일 안에 "총괄" 탭(학생별 한 줄: 반·학번·이름·상태·제출 시각·문장/표현/이탈·PDF 링크)과
 * "반별 요약" 탭(반별 접속·초안·최종 제출 인원)이 자동으로 만들어지고, 초안·최종 제출 때마다 갱신됩니다.
 * 즉시 갱신하려면 함수 목록에서 rebuildOverview 를 실행하세요.
 * 같은 파일에 "명단" 탭을 만들어 A열 학번, B열 이름을 붙여 넣으면(1행은 제목) 한 번도 접속하지 않은 학생도
 * "미접속"으로 표시되고, 명단에 없는 학번으로 들어온 학생은 "명단에 없음"으로 표시됩니다.
 *
 * ── 두 번에 나눠 하는 활동 (학번+이름 = 학생 ID) ─────────────
 * 학생이 작성하는 동안 1분마다, 그리고 초안을 제출할 때 학생 상태 전체가 "초안" 시트(제출명단 파일의 두 번째 탭)에
 * 저장됩니다. 학생이 같은 학번·이름으로 다시 로그인하면 이 시트의 상태로 이어지므로 다른 아이패드에서도 됩니다.
 *   - 초안 제출 전이면 1회차(조사 → 초안)가 열리고, 초안을 제출했으면 2회차(최종 글쓰기)가 열립니다.
 *   - 학번은 같은데 이름이 다르면 기존 줄을 넘겨주지 않고 "중복" 표시가 된 새 줄을 만듭니다(두 학생 글이 모두 남습니다).
 *     시험 중에 못 들어가게 막지는 않습니다. "오류" 탭과 총괄의 [명단 확인] 칸에서 확인하세요.
 * 2회차(최종 제출)에 PDF를 만들고 제출명단에 기록합니다.
 *
 * 단어 사전: 작성 페이지의 "사전" 버튼은 단어 하나만 여기로 보내고, 구글 번역으로 뜻을 받아 갑니다.
 *   띄어쓰기가 있거나 20자를 넘으면 서버가 거절하므로 문장 번역기로는 쓸 수 없습니다.
 *   찾은 단어는 "사전" 탭과 학생 제출물의 자동집계에 모두 남습니다. 끄려면 CFG.dict.enabled: false
 *
 * 최종 단계 열고 닫기(선택): 초안을 일찍 낸 학생이 같은 시간에 최종까지 써 버리는 것을 막고 싶으면
 *   함수 목록에서 closeFinal 을 실행해 두고, 2회차 수업 때 openFinal 을 실행하세요. 기본은 열림입니다.
 *
 * ── 미리 확인하기 ─────────────────────────────────────────
 * 위쪽 함수 목록에서 testSubmit 을 골라 "실행"하면 샘플 제출물이 하나 폴더에 올라갑니다.
 */

const CFG = {
  folderId: "1sfIusHdcvCeiSJwvli1YL2ynPq75KF-0", // ★ 제출물을 올릴 드라이브 폴더 ID. 비워 두면 내 드라이브에 folderName 폴더를 만듭니다.
  folderName: "영어쓰기_수행평가_제출물",        // folderId 를 비워 둘 때만 사용

  subfolderByClass: true,                       // true: 학번 앞 세 자리(예: 10315 → "103")로 반별 하위 폴더를 만들어 정리
  format: "pdf",                                // "pdf" 만 지원합니다. (Word 내보내기는 새 권한 승인이 필요해서 넣지 않았습니다)

  logSheet: true,                               // true: 같은 폴더에 "제출명단" 시트를 만들어 한 줄씩 기록
  logSheetName: "제출명단",
  draftSheetName: "초안",                        // 학생 상태(자동 저장·초안)를 보관하는 시트 (제출명단 파일 안의 두 번째 탭)
  draftPdf: true,                               // true: 1회차 초안 제출 때도 PDF를 만들어 반 폴더 안 "초안" 폴더에 저장
  overview: { name: "총괄", summaryName: "반별 요약", rosterName: "명단" },   // 총괄 시트 탭 이름

  notifyEmail: "",                              // 메일도 받고 싶을 때만 주소 입력 (예: "guenhee9474@snu.ac.kr"). 비우면 메일 없음
  attachToEmail: true,                          // 메일에 파일 첨부 여부
  subjectPrefix: "[영어 쓰기 수행평가]",

  // 단어 사전: 작성 페이지의 사전 버튼이 여기로 단어 하나를 보내면 구글 번역(LanguageApp)으로 뜻을 돌려주고 기록합니다.
  dict: { enabled: true, maxLen: 20, maxPerStudent: 80, logSheetName: "사전" },

  token: "gfa2026",                             // 작성 페이지의 CONFIG.submit.token 과 같아야 함
  maxChars: 20000,                              // 한 항목당 글자 수 상한 (장난 제출 방지)

  // 선생님 현황 화면 주소. 편집기에서 newTeacherKey() 를 실행하면 이 주소에 열쇠를 붙여 알려 줍니다.
  teacherPage: "https://guenhee9474-tech.github.io/english-writing/teacher.html"
};

/* ────────────────────────── 잠금 · 시트 손잡이 ──────────────────────────
   30명이 한꺼번에 저장하면 "읽고 → 고쳐서 → 쓰기" 사이에 다른 학생 요청이 끼어들어
   방금 쓴 내용이 지워질 수 있습니다. 그래서 그 구간은 반드시 잠금을 잡고 들어갑니다.
   잠금을 못 잡았는데 그냥 진행하면 안 되는 곳(required)은 오류를 내서 제출을 실패로 만들고,
   학생 화면이 "확인되지 않았습니다"를 보여 주도록 합니다. 조용히 망가지는 것보다 낫습니다. */

function withLock(ms, label, fn, required) {
  const lock = LockService.getScriptLock();
  let got = false;
  try { got = lock.tryLock(ms); } catch (e) { got = false; }
  if (!got) {
    if (required) { logError("잠금 실패(" + label + ")", new Error("다른 요청이 " + ms + "ms 안에 끝나지 않았습니다"), ""); throw new Error("BUSY"); }
    return fn();                                 // 줄을 새로 붙이기만 하는 곳은 잠금 없이도 안전합니다
  }
  try { return fn(); } finally { try { lock.releaseLock(); } catch (e) {} }
}

// 한 번 실행되는 동안 같은 시트를 여러 번 열지 않도록 손잡이를 보관합니다 (제출이 몰릴 때 속도 차이가 큽니다).
let _sheetCache = {};
function cachedSheet(name, make) {
  if (!_sheetCache[name]) _sheetCache[name] = make();
  return _sheetCache[name];
}
// 시트에 학생 글을 쓸 때 "=" 로 시작하는 값이 수식으로 해석되지 않게 합니다.
function safeCell(v) { const s = String(v == null ? "" : v); return /^[=+\-@]/.test(s) ? "'" + s : s; }
// 이름 비교용 (공백·대소문자 무시)
function nameKey(s) { return String(s || "").replace(/\s+/g, "").toLowerCase(); }

/* ────────────────────────── 제출 받기 ────────────────────────── */

function doPost(e) {
  try {
    const p = (e && e.parameter) || {};
    if (CFG.token && p.token !== CFG.token) return textOut("BAD_TOKEN");

    const data = {
      sid: cut(p.sid || "학번없음", 40),
      name: cut(p.name || "이름없음", 40),
      key: cut(p.key || "", 64),
      title: cut(p.title || "영어 쓰기 수행평가", 120),
      subtitle: cut(p.subtitle || "", 120),
      brainstorm: cut(p.brainstorm || "", CFG.maxChars),
      draft: cut(p.draft || "", CFG.maxChars),
      final: cut(p.final || "", CFG.maxChars),
      meta: cut(p.meta || "", 4000),
      bank: parseBank(p.bank)
    };
    if (!data.key) return textOut("NO_KEY");           // 열쇠 없는 저장은 받지 않음 (로그인 때 발급됨)
    const sh0 = draftSheet();
    const row = findRow(sh0, data.sid, data.key);
    if (!row) return textOut("UNKNOWN_KEY");
    data.dup = String(sh0.getRange(row, COL.dup).getValue() || "") === "Y";

    if (p.phase === "save") {                          // 작성 중 자동 저장: 상태 + 읽을 수 있는 텍스트
      saveDraft(data, p.data || "", phaseOf(p.data), "");
      maybeRebuildOverview(false);                     // 수업 중에도 총괄이 저절로 갱신되게
      return textOut("OK_SAVE");
    }
    // 교사 메뉴 "제출 취소 (다시 열기)": 단계만 되돌립니다. 학생이 다시 쓴 글은 이후 자동 저장으로 정상 저장됩니다.
    if (p.phase === "reopen") {
      const to = String(p.to || "");
      if (!PHASE_ORDER.hasOwnProperty(to)) return textOut("BAD_PHASE");
      saveDraft(data, p.data || "", to, "", { allowRegress: true });
      return textOut("OK_REOPEN");
    }
    if (p.bank) { try { PropertiesService.getScriptProperties().setProperty("bank", p.bank); } catch (eb) {} }   // 재생성용
    if (p.phase === "draft") {                         // 1회차 초안 제출: (선택) PDF + 상태 저장
      let link = "";
      if (CFG.draftPdf) {
        try { link = savePdf(data, "draft")[0].getUrl(); }
        catch (e0) { logError("초안 PDF", e0, data.sid); link = "PDF 실패: " + String(e0 && e0.message || e0).slice(0, 120); }
      }
      saveDraft(data, p.data || "", "draftDone", link, { allowRegress: true });
      maybeRebuildOverview(true);   // 제출은 바로 보여야 합니다 (기다리면 마지막 제출이 화면에 안 남습니다)
      return textOut("OK_DRAFT");
    }
    if (p.phase !== "final") return textOut("BAD_PHASE");   // 모르는 단계 값을 최종 제출로 처리하지 않는다

    // 최종 단계를 닫아 둔 상태에서 들어온 제출도 받습니다(학생 글을 버리는 것이 더 나쁩니다). 대신 오류 탭에 남겨 둡니다.
    if (!isFinalOpen()) logError("최종 닫힘 상태에서 최종 제출", new Error("closeFinal 중 제출됨"), data.sid + " " + data.name);

    // 2회차: PDF + 명단. PDF가 실패해도 시트 기록과 상태 저장은 반드시 해서 학생 글이 사라지지 않게 합니다.
    let files = [];
    try { files = savePdf(data, "final"); }
    catch (e0) { logError("최종 PDF", e0, data.sid); files = []; }
    if (CFG.logSheet) { try { logRow(data, files); } catch (e1) { logError("제출명단 기록", e1, data.sid); } }
    try { saveDraft(data, p.data || "", "done", files[0] ? files[0].getUrl() : "", { allowRegress: true }); } catch (e3) { logError("최종 상태 저장", e3, data.sid); }
    if (CFG.notifyEmail) { try { sendMail(data, files); } catch (e2) { logError("메일 보내기", e2, data.sid); } }
    // 총괄 시트는 여기서 직접 쓰지 않고 "잠시 뒤 한 번" 예약합니다.
    // 제출이 몰릴 때 여기서 바로 쓰면 가장 무거운 작업이 30번 겹쳐 실행 시간 제한을 넘깁니다.
    maybeRebuildOverview(true);   // 제출은 바로 보여야 합니다
    return textOut("OK");
  } catch (err) {
    // 실패해도 학생 화면이 멈추지 않도록 항상 응답합니다. 오류는 "오류" 탭(과 설정한 메일)에 남깁니다.
    logError("제출 처리", err, (e && e.parameter && (e.parameter.phase + " " + e.parameter.sid)) || "");
    try {
      if (CFG.notifyEmail) MailApp.sendEmail(CFG.notifyEmail, CFG.subjectPrefix + " 제출 처리 오류",
        String(err) + "\n\n" + JSON.stringify((e && e.parameter) || {}).slice(0, 3000));
    } catch (ignore) {}
    return textOut("ERROR");
  }
}

// 작성 페이지가 읽어 가는 정보 (JSONP). 브라우저로 그냥 열면 상태 문구만 보입니다.
function doGet(e) {
  const p = (e && e.parameter) || {};
  const cb = p.callback;
  if (!cb) return textOut("작성 페이지의 제출을 받는 주소입니다. 정상 작동 중. 최종 단계: " + (isFinalOpen() ? "열림" : "닫힘"));
  let out = {};
  try {
    // 선생님 현황 화면은 학생용 token 이 아니라 자기 열쇠(k)로 확인합니다. 그래서 token 검사보다 먼저 봅니다.
    if (p.action === "monitor") out = monitorData(p.cls || "", p.k || "");
    else if (CFG.token && p.token !== CFG.token) out = { error: "BAD_TOKEN" };
    else if (p.action === "load") {                 // 로그인: 열쇠 확인·발급 + 저장된 상태 + 최종 제출 여부 + 최종 단계 열림 여부
      out = loadOrRegister(p.sid, p.name, p.key);
      out.finalOpen = isFinalOpen();
      out.finalAt = null;
      try { out.finalAt = checkStatus(p.sid, out.key).finalAt; } catch (e) {}
    }
    else if (p.action === "dict") out = dictLookup(p);
    else if (p.action === "check") out = checkStatus(p.sid, p.key);
    else if (p.action === "session") out = { session: 1, finalOpen: isFinalOpen() };
    else out = { ok: true };
  } catch (err) { out = { error: String(err) }; }
  const js = String(cb).replace(/[^\w$.]/g, "") + "(" + JSON.stringify(out) + ");";
  return ContentService.createTextOutput(js).setMimeType(ContentService.MimeType.JAVASCRIPT);
}

/* ────────────────────────── 단어 사전 ────────────────────────── */

// 단어 하나만 받는다. 띄어쓰기가 있거나 길면 거절 → 문장 번역기로 쓸 수 없음.
function dictLookup(p) {
  const c = CFG.dict || {};
  if (!c.enabled) return { error: "DISABLED" };
  const q = String(p.q || "").trim();
  if (!q || /\s/.test(q) || q.length > (c.maxLen || 20) || !/^[A-Za-z가-힣ㄱ-ㅎㅏ-ㅣ'\-]+$/.test(q)) return { error: "BAD_QUERY" };
  const sid = String(p.sid || "");
  if (!findRow(draftSheet(), sid, String(p.key || ""))) return { error: "NO_KEY" };   // 로그인한 기기에서만
  // 학생별 하루 조회 상한 (캐시 6시간)
  const cache = CacheService.getScriptCache();
  const key = "dict_" + sid;
  const used = Number(cache.get(key) || 0);
  if (c.maxPerStudent && used >= c.maxPerStudent) return { error: "LIMIT" };
  const ko = /[가-힣ㄱ-ㅎㅏ-ㅣ]/.test(q);
  let a = "";
  try { a = LanguageApp.translate(q, ko ? "ko" : "en", ko ? "en" : "ko"); } catch (e) { return { error: "TRANSLATE_FAIL" }; }
  a = String(a || "").trim();
  cache.put(key, String(used + 1), 21600);
  try {
    const sh = dictSheet();
    sh.appendRow([new Date(), sid, String(p.name || ""), String(p.phase || ""), q, a]);
  } catch (e) {}
  return { q: q, a: a, dir: ko ? "ko→en" : "en→ko" };
}
function dictSheet() {
  const ss = SpreadsheetApp.openById(getLogSheet().getParent().getId());
  let sh = ss.getSheetByName(CFG.dict.logSheetName || "사전");
  if (!sh) {
    sh = ss.insertSheet(CFG.dict.logSheetName || "사전");
    sh.appendRow(["시각", "학번", "이름", "단계", "찾은 단어", "결과"]);
    sh.setFrozenRows(1);
  }
  return sh;
}

/* ────────────────────────── 최종 단계 열고 닫기 ────────────────────────── */

function isFinalOpen() { return PropertiesService.getScriptProperties().getProperty("finalOpen") !== "0"; }
function openFinal()  { PropertiesService.getScriptProperties().setProperty("finalOpen", "1"); Logger.log("최종 단계 열림"); }
function closeFinal() { PropertiesService.getScriptProperties().setProperty("finalOpen", "0"); Logger.log("최종 단계 닫힘 (초안 제출까지만 가능)"); }
function phaseOf(json) { try { return String(JSON.parse(json).phase || ""); } catch (e) { return ""; } }

/* ────────────────────────── 초안 보관 (1회차) ────────────────────────── */

// 초안 시트 열
const DRAFT_HEADER = ["학번", "이름", "기기열쇠", "등록시각", "저장시각", "단계", "초안 문장수", "자동집계", "브레인스토밍", "초안", "초안 PDF", "데이터(JSON)", "중복", "초안제출시각", "최종제출시각", "최종 PDF"];
const COL = { sid: 1, name: 2, key: 3, reg: 4, at: 5, phase: 6, count: 7, meta: 8, brain: 9, draft: 10, pdf: 11, json: 12, dup: 13, draftAt: 14, finalAt: 15, finalPdf: 16 };
function draftSheet() { return cachedSheet("draft", draftSheetFresh); }
function draftSheetFresh() {
  const ss = SpreadsheetApp.openById(getLogSheet().getParent().getId());
  let sh = ss.getSheetByName(CFG.draftSheetName);
  if (sh) {
    const h = sh.getRange(1, 1, 1, DRAFT_HEADER.length).getValues()[0];
    if (String(h[COL.key - 1]) !== "기기열쇠" || String(h[COL.finalPdf - 1]) !== "최종 PDF") {
      sh.setName(CFG.draftSheetName + "_old_" + Utilities.formatDate(new Date(), "Asia/Seoul", "MMdd_HHmm"));
      sh = null;
    }
  }
  if (!sh) {
    sh = ss.insertSheet(CFG.draftSheetName);
    sh.appendRow(DRAFT_HEADER);
    sh.setFrozenRows(1);
    sh.setColumnWidth(COL.brain, 260); sh.setColumnWidth(COL.draft, 420); sh.hideColumns(COL.json);
  }
  return sh;
}
function allRows(sh) {
  const last = sh.getLastRow();
  return last < 2 ? [] : sh.getRange(2, 1, last - 1, DRAFT_HEADER.length).getValues();
}
// 총괄 시트용: 큰 칸(브레인스토밍·초안·데이터JSON)은 읽지 않고 자리만 비워 둔다.
// 한 학생 줄의 99%가 그 세 칸이고 갱신이 1~2분마다 도므로 차이가 크다. 열 위치는 COL 그대로 유지된다.
function overviewRows(sh) {
  const last = sh.getLastRow();
  const n = last - 1;
  if (n < 1) return [];
  const a = sh.getRange(2, 1, n, 8).getValues();              // 학번 … 자동집계 (1-8)
  const b = sh.getRange(2, COL.pdf, n, 1).getValues();        // 초안 PDF (11)
  const c = sh.getRange(2, COL.dup, n, 4).getValues();        // 중복 … 최종 PDF (13-16)
  const out = [];
  for (let i = 0; i < n; i++) {
    out.push(a[i].concat(["", "", b[i][0], ""], c[i]));        // 9,10 = 빈칸 / 12 = 빈칸
  }
  return out;
}
// 학번·이름·열쇠 칸만 읽습니다 (브레인스토밍·초안·JSON 같은 큰 칸을 건드리지 않아 훨씬 가볍습니다)
function idRows(sh) {
  const last = sh.getLastRow();
  return last < 2 ? [] : sh.getRange(2, 1, last - 1, COL.key).getValues();
}
// 학번 + 열쇠가 모두 맞는 줄
function findRow(sh, sid, key) {
  if (!key) return 0;
  const rows = idRows(sh);
  for (let i = 0; i < rows.length; i++) if (String(rows[i][COL.sid - 1]) === String(sid) && String(rows[i][COL.key - 1]) === String(key)) return i + 2;
  return 0;
}
function newKey() { return Utilities.getUuid().replace(/-/g, "").slice(0, 20); }

// 로그인: 열쇠가 맞으면 그 줄을, 없으면 (열쇠 칸이 비어 있는 같은 학번 줄이 있으면 이어받고) 아니면 새 줄을 만든다
function loadOrRegister(sid, name, key) {
  sid = String(sid || "").trim(); name = String(name || "").trim();
  if (!/^\d{3,}$/.test(sid) || !name) return { found: false, error: "BAD_ID" };
  return withLock(30000, "로그인 " + sid, function () {
    const sh = draftSheet();
    const r = findRow(sh, sid, key);
    if (r) {                                     // 열쇠가 맞는 줄 = 같은 기기. 그 줄을 그대로 이어 준다
      const v = sh.getRange(r, 1, 1, DRAFT_HEADER.length).getValues()[0];
      return { found: !!v[COL.json - 1], data: v[COL.json - 1] || null, at: v[COL.at - 1], phase: v[COL.phase - 1] || "", key: key,
               name: String(v[COL.name - 1] || name), dup: String(v[COL.dup - 1] || "") === "Y" };
    }
    // 열쇠가 없거나 모르는 열쇠: 이어받을 줄(열쇠 칸이 빈 같은 학번)이 있는지 본다
    const ids = idRows(sh);
    const fresh = newKey();
    let nameBlocked = "";
    for (let i = 0; i < ids.length; i++) {
      if (String(ids[i][COL.sid - 1]) !== String(sid) || String(ids[i][COL.key - 1] || "")) continue;
      const storedName = String(ids[i][COL.name - 1] || "");
      // 학번은 같은데 이름이 다르면 남의 줄을 넘겨주지 않는다. 막지는 않고 아래에서 새 줄을 만든다
      // (시험 중에 학생을 못 들어오게 하는 것보다, 두 사람 글을 모두 살리고 "중복"으로 표시하는 것이 안전하다)
      if (storedName && nameKey(storedName) !== nameKey(name)) { nameBlocked = storedName; continue; }
      const rr = i + 2;
      const v = sh.getRange(rr, 1, 1, DRAFT_HEADER.length).getValues()[0];
      sh.getRange(rr, COL.key).setValue(fresh);
      return { found: !!v[COL.json - 1], data: v[COL.json - 1] || null, at: v[COL.at - 1], phase: v[COL.phase - 1] || "", key: fresh,
               name: storedName || name, dup: String(v[COL.dup - 1] || "") === "Y", transferred: true };
    }
    // 새 등록. 같은 학번이 이미 있으면 중복 표시
    const exists = ids.some((row) => String(row[COL.sid - 1]) === String(sid));
    sh.appendRow([sid, name, fresh, new Date(), new Date(), "research", "", "", "", "", "", "", exists ? "Y" : "", "", "", ""]);
    if (nameBlocked) logError("이름이 달라 새 줄로 등록", new Error("학번 " + sid + ": 시트에는 \"" + nameBlocked + "\", 입력은 \"" + name + "\""), "기존 줄은 그대로 두었습니다");
    return { found: false, key: fresh, name: name, dup: exists, nameMismatch: !!nameBlocked };
  }, true);
}

const PHASE_ORDER = { research: 0, draft: 1, draftDone: 2, final: 3, done: 4 };
function saveDraft(d, json, phase, pdfLink, opts) {
  opts = opts || {};
  return withLock(30000, "저장 " + d.sid, function () {
    const sh = draftSheet();
    const r = findRow(sh, d.sid, d.key);
    if (!r) return;
    const old = sh.getRange(r, 1, 1, DRAFT_HEADER.length).getValues()[0];
    const prev = String(old[COL.phase - 1] || "");
    // 늦게 도착한 자동 저장이 단계를 되돌리지 못하게 합니다. 단, 글은 그대로 저장합니다.
    // (예전에는 저장 전체를 버렸습니다. 그래서 교사가 "제출 취소"로 되돌린 뒤 다시 쓴 글이 서버에 안 남았습니다.)
    let ph = phase || "";
    if (!opts.allowRegress && (PHASE_ORDER[prev] || 0) > (PHASE_ORDER[ph] || 0)) ph = prev;
    const now = new Date();
    // 상태(JSON)가 칸 크기를 넘으면 잘라 넣지 않습니다. 자르면 다음 로그인 때 읽을 수 없게 되기 때문에
    // 이전에 저장된 온전한 값을 그대로 두고 오류 탭에 남깁니다.
    let js = String(json == null ? "" : json);
    if (js.length > 45000) {
      logError("상태(JSON)가 너무 커서 저장하지 않음", new Error("길이 " + js.length + " (상한 45000)"), d.sid);
      js = String(old[COL.json - 1] || "");
    }
    const row = [d.sid, old[COL.name - 1] || d.name, d.key, old[COL.reg - 1] || now, now, ph,
      num(d.meta, /초안 문장 (\d+)/), safeCell(d.meta), safeCell(String(d.brainstorm || "").slice(0, 20000)), safeCell(String(d.draft || "").slice(0, 20000)),
      (phase === "draftDone" && pdfLink) ? pdfLink : String(old[COL.pdf - 1] || ""), js, old[COL.dup - 1] || "",
      phase === "draftDone" ? now : (old[COL.draftAt - 1] || ""), phase === "done" ? now : (old[COL.finalAt - 1] || ""),
      (phase === "done" && pdfLink) ? pdfLink : String(old[COL.finalPdf - 1] || "")];
    sh.getRange(r, 1, 1, row.length).setValues([row]);
  }, true);
}
function readDraft(sid, key) {
  const sh = draftSheet();
  const r = findRow(sh, sid, key);
  if (!r) return { found: false };
  const v = sh.getRange(r, 1, 1, DRAFT_HEADER.length).getValues()[0];
  return { found: !!v[COL.json - 1], data: v[COL.json - 1], at: v[COL.at - 1], phase: v[COL.phase - 1] || "" };
}
// 학생 화면이 "정말 저장됐나?"를 확인할 때 쓰는 값들.
// draftAt 은 반드시 [초안제출시각] 칸이어야 합니다. [저장시각]을 돌려주면 1분마다 도는 자동 저장 때문에
// 초안 제출이 실패했는데도 항상 "저장되었습니다"가 나옵니다.
function checkStatus(sid, key) {
  const out = { draftAt: null, finalAt: null, draftPdf: "", finalPdf: "", phase: "", savedAt: null };
  if (!String(key || "")) return out;            // 열쇠가 없으면 확인해 주지 않는다 (같은 학번인 남의 줄이 잡힐 수 있다)
  try {
    const sh = draftSheet(); const r = findRow(sh, sid, key);
    if (r) {
      const v = sh.getRange(r, 1, 1, DRAFT_HEADER.length).getValues()[0];
      out.draftAt = v[COL.draftAt - 1] || null;
      out.savedAt = v[COL.at - 1] || null;
      out.phase = String(v[COL.phase - 1] || "");
      out.draftPdf = String(v[COL.pdf - 1] || "");
      out.finalPdf = String(v[COL.finalPdf - 1] || "");
    }
  } catch (e) { logError("상태 확인(초안 시트)", e, sid); }
  try {
    const sh = getLogSheet();
    const last = sh.getLastRow();
    if (last >= 2) {
      const rows = sh.getRange(2, 1, last - 1, 11).getValues();
      const kp = String(key).slice(0, 6);
      for (let i = rows.length - 1; i >= 0; i--) if (String(rows[i][1]) === String(sid) && String(rows[i][10] || "") === kp) { out.finalAt = rows[i][0]; break; }
    }
  } catch (e) { logError("상태 확인(제출명단)", e, sid); }
  return out;
}

/* ────────────────────────── 문서 만들기 (PDF) ────────────────────────── */

const C_INK = "#1B2436", C_MUTED = "#5D6675", C_LINE = "#D8DEE7", C_BG = "#F2F4F7", C_MARK = "#FFE58A", C_ACCENT = "#0E7C66", C_DANGER = "#B42318";

// kind: "final" | "draft"  →  만들어진 파일 목록을 돌려줍니다 (지금은 PDF 한 개)
function savePdf(d, kind) {
  const isFinal = kind === "final";
  const base = targetFolder(d.sid);
  let folder = base;
  if (!isFinal) { const it = base.getFoldersByName("초안"); folder = it.hasNext() ? it.next() : base.createFolder("초안"); }
  const stamp = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyyMMdd_HHmm");
  const name = d.sid + "_" + d.name + (isFinal ? "" : "_초안") + (d.dup ? "_중복" : "") + "_" + stamp;

  const doc = DocumentApp.create(name);
  const body = doc.getBody();
  body.setMarginTop(48).setMarginBottom(48).setMarginLeft(56).setMarginRight(56);
  body.setAttributes({ [DocumentApp.Attribute.FONT_FAMILY]: "Arial", [DocumentApp.Attribute.FONT_SIZE]: 10.5, [DocumentApp.Attribute.FOREGROUND_COLOR]: C_INK });

  const finalStats = analyzeText(d.final, d.bank);
  const draftStats = analyzeText(draftPlain(d.draft), d.bank);
  const stats = isFinal ? finalStats : draftStats;

  // 제목
  para(body, d.title, { size: 20, bold: true, after: 2 });
  para(body, (d.subtitle ? d.subtitle + "  ·  " : "") + (isFinal ? "최종 제출" : "1회차 초안 제출"), { size: 10, color: C_MUTED, after: 8 });

  // 학생 정보 + 채점 요약 (한 표)
  const when = Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm");
  const rows = [
    ["학번", d.sid, "이름", d.name + (d.dup ? "  (중복 학번)" : "")],
    ["제출", when, "단계", isFinal ? "최종 글쓰기" : "초안"],
    [isFinal ? "최종 문장 수" : "초안 문장 수", String(stats.sentences.length), "Word Bank 표현", stats.used.length + " / " + (d.bank.length || 0)]
  ];
  if (isFinal) rows.push(["초안 문장 수", String(draftStats.sentences.length), "소요", pick(d.meta, /소요 ([^|]+)/)]);
  rows.push(["화면 이탈", pick(d.meta, /화면이탈 (\d+회)/), "한글 입력 / 선택", pick(d.meta, /한글입력 (\d+회)/) + " / " + pick(d.meta, /한글선택 (\d+회)/)]);
  rows.push(["사전 조회", pick(d.meta, /사전 (\d+회)/), "자동완성 차단 / 대량 입력", pick(d.meta, /자동완성차단 (\d+회)/) + " / " + pick(d.meta, /대량입력 (\d+회)/)]);
  infoTable(body, rows);

  // Word Bank 사용 현황
  para(body, "Word Bank", { size: 11, bold: true, before: 12, after: 3 });
  wordBankLine(body, d.bank, stats.used);

  // 본문
  if (isFinal) {
    heading(body, "Step 4. 최종본");
    if (stats.sentences.length) stats.sentences.forEach((sen, i) => numbered(body, i + 1, sen, d.bank, 12));
    else para(body, "(비어 있음)", { color: C_MUTED });
  }
  heading(body, "Step 3. 초안");
  draftBlock(body, d.draft, d.bank);
  heading(body, "Step 1-2. 예시 분석 및 브레인스토밍");
  brainstormBlock(body, d.brainstorm);

  // 자동 집계 (감사용)
  heading(body, "자동 집계");
  para(body, d.meta || "-", { size: 8.5, color: C_MUTED });
  para(body, "이 문서는 작성 페이지의 제출 시점에 자동 생성되었습니다. 노란 표시 = Word Bank 표현.", { size: 8, color: C_MUTED, before: 6 });

  doc.saveAndClose();
  const docFile = DriveApp.getFileById(doc.getId());
  const pdf = folder.createFile(docFile.getAs("application/pdf").setName(name + ".pdf"));
  docFile.setTrashed(true);
  return [pdf];
}

// ---- 문서 조각 ----
function para(body, text, o) {
  o = o || {};
  const p = body.appendParagraph(String(text || ""));
  p.setSpacingBefore(o.before || 0).setSpacingAfter(o.after == null ? 2 : o.after);
  const t = p.editAsText();
  t.setFontSize(o.size || 10.5).setBold(!!o.bold).setForegroundColor(o.color || C_INK);
  if (o.font) t.setFontFamily(o.font);
  return p;
}
function heading(body, text) {
  const p = para(body, text, { size: 12, bold: true, before: 14, after: 4 });
  return p;
}
function infoTable(body, rows) {
  const t = body.appendTable(rows);
  t.setBorderColor(C_LINE).setBorderWidth(0.75);
  for (let r = 0; r < t.getNumRows(); r++) {
    const row = t.getRow(r);
    for (let c = 0; c < row.getNumCells(); c++) {
      const cell = row.getCell(c);
      cell.setPaddingTop(3).setPaddingBottom(3).setPaddingLeft(6).setPaddingRight(6);
      const tx = cell.editAsText();
      tx.setFontSize(9.5);
      if (c % 2 === 0) { cell.setBackgroundColor(C_BG); tx.setBold(true).setForegroundColor(C_MUTED); cell.setWidth(78); }
      else { tx.setForegroundColor(C_INK); }
    }
  }
  return t;
}
function wordBankLine(body, bank, used) {
  const p = body.appendParagraph("");
  p.setSpacingAfter(2);
  const t = p.editAsText();
  let pos = 0;
  bank.forEach((w, i) => {
    const label = (used.indexOf(i) >= 0 ? "✓ " : "") + w.label;
    t.appendText(label);
    const end = pos + label.length - 1;
    t.setFontSize(pos, end, 10);
    if (used.indexOf(i) >= 0) { t.setBackgroundColor(pos, end, C_MARK).setBold(pos, end, true).setForegroundColor(pos, end, C_INK); }
    else { t.setBold(pos, end, false).setForegroundColor(pos, end, C_MUTED).setBackgroundColor(pos, end, "#FFFFFF"); }
    pos = end + 1;
    if (i < bank.length - 1) { t.appendText("   "); t.setBackgroundColor(pos, pos + 2, "#FFFFFF"); pos += 3; }
  });
  return p;
}
// 번호가 붙은 문장 한 줄 (영문은 Georgia), Word Bank 구간을 노란 배경으로
function numbered(body, n, text, bank, size) {
  const prefix = "(" + n + ")  ";
  const p = body.appendParagraph(prefix + text);
  p.setSpacingAfter(3).setLineSpacing(1.35);
  const t = p.editAsText();
  t.setFontSize(size || 11.5).setFontFamily("Georgia").setForegroundColor(C_INK);
  t.setFontSize(0, prefix.length - 1, 9).setForegroundColor(0, prefix.length - 1, C_MUTED);
  matchRanges(text, bank).forEach((r) => { t.setBackgroundColor(prefix.length + r.s, prefix.length + r.e - 1, C_MARK); });
  return p;
}
function draftBlock(body, draftText, bank) {
  const lines = String(draftText || "").split("\n");
  if (!lines.join("").trim()) { para(body, "(비어 있음)", { color: C_MUTED }); return; }
  lines.forEach((line) => {
    const m = line.match(/^\((\d+)\)\s?(.*)$/);
    if (m) {
      if (!m[2].trim()) { para(body, "(" + m[1] + ")  ", { size: 9, color: C_MUTED, font: "Georgia" }); return; }
      numbered(body, m[1], m[2], bank, 11);
    } else if (line.trim()) {
      para(body, line, { size: 10, bold: true, before: 6, after: 2, color: C_MUTED });
    }
  });
}
function brainstormBlock(body, text) {
  const lines = String(text || "").split("\n");
  if (!lines.join("").trim()) { para(body, "(비어 있음)", { color: C_MUTED }); return; }
  lines.forEach((line) => {
    if (!line.trim()) return;
    if (/^\[.*\]$/.test(line.trim())) { para(body, line.trim().replace(/[\[\]]/g, ""), { size: 10, bold: true, before: 6, after: 2, color: C_MUTED }); return; }
    const m = line.match(/^([^:]{1,40}:|\d\.\s[^\s]+(?:\s[A-Za-z→\d ]+)?)\s*(.*)$/);
    const p = body.appendParagraph(line);
    p.setSpacingAfter(2);
    const t = p.editAsText(); t.setFontSize(10.5);
    if (m && m[1]) { t.setBold(0, m[1].length - 1, true).setForegroundColor(0, m[1].length - 1, C_MUTED); }
  });
}
function draftPlain(draftText) {
  return String(draftText || "").split("\n").map((l) => { const m = l.match(/^\(\d+\)\s?(.*)$/); return m ? m[1] : ""; }).filter((x) => x.trim()).join(" ");
}
function pick(meta, re) { const m = String(meta || "").match(re); return m ? m[1].trim() : "-"; }

// ---- 분석 (작성 페이지와 같은 규칙) ----
function parseBank(json) {
  try {
    const arr = JSON.parse(json || "[]");
    return arr.map((w) => ({ label: String(w.label || ""), re: new RegExp(w.source, String(w.flags || "i").replace("g", "")) })).filter((w) => w.label);
  } catch (e) { return []; }
}
function splitSentences(text) {
  const t = String(text || "").replace(/\s+/g, " ").trim();
  if (!t) return [];
  const out = []; const re = /[^.!?]+(?:[.!?]+["')\]]*|$)/g; let m;
  while ((m = re.exec(t)) !== null) {
    if (m.index === re.lastIndex) { re.lastIndex++; continue; }
    const s = m[0].trim(); if (/[A-Za-z]{2,}/.test(s)) out.push(s);
  }
  return out;
}
function analyzeText(text, bank) {
  const used = [];
  (bank || []).forEach((w, i) => { if (w.re.test(String(text || ""))) used.push(i); });
  return { sentences: splitSentences(text), used: used };
}
function matchRanges(text, bank) {
  const ranges = [];
  (bank || []).forEach((w) => {
    const g = new RegExp(w.re.source, w.re.flags.includes("g") ? w.re.flags : w.re.flags + "g"); let m;
    while ((m = g.exec(text)) !== null) { if (!m[0].length) { g.lastIndex++; continue; } ranges.push({ s: m.index, e: m.index + m[0].length }); }
  });
  ranges.sort((a, b) => a.s - b.s || b.e - a.e);
  const out = []; let pos = 0;
  ranges.forEach((r) => { if (r.s < pos) return; out.push(r); pos = r.e; });
  return out;
}

function baseFolder() {
  if (CFG.folderId) return DriveApp.getFolderById(CFG.folderId);
  // 잠금을 못 잡아도 진행합니다. 최악의 경우 같은 이름 폴더가 하나 더 생기는 것이고, 글이 사라지지는 않습니다.
  return withLock(20000, "기본 폴더", function () {
    const it = DriveApp.getFoldersByName(CFG.folderName);
    return it.hasNext() ? it.next() : DriveApp.createFolder(CFG.folderName);
  }, false);
}

// 학번 앞 세 자리로 반별 하위 폴더 (10315 → "103")
function targetFolder(sid) {
  const base = baseFolder();
  if (!CFG.subfolderByClass) return base;
  const m = String(sid).match(/^\d{3}/);
  if (!m) return base;
  const name = m[0] + "반";
  return withLock(20000, "반 폴더 " + name, function () {
    const it = base.getFoldersByName(name);
    return it.hasNext() ? it.next() : base.createFolder(name);
  }, false);
}

/* ────────────────────────── 제출 명단 시트 ────────────────────────── */

function logRow(d, files) {
  // 줄을 맨 아래에 새로 붙이기만 하므로 잠금을 못 잡아도 안전합니다. 제출을 놓치는 것이 더 나쁩니다.
  return withLock(20000, "제출명단 " + d.sid, function () {
    const sheet = getLogSheet();
    sheet.appendRow([
      new Date(), d.sid, safeCell(d.name),
      num(d.meta, /최종 문장 (\d+)/), num(d.meta, /표현 (\d+)/),
      num(d.meta, /화면이탈 (\d+)/), num(d.meta, /한글입력 (\d+)/),
      safeCell(d.meta),
      files.length && files[0] ? files[0].getUrl() : "PDF 없음",
      d.dup ? "중복" : "", String(d.key || "").slice(0, 6)
    ]);
  }, false);
}

function getLogSheet() { return cachedSheet("log", getLogSheetFresh); }
function getLogSheetFresh() {
  const props = PropertiesService.getScriptProperties();
  const folder = baseFolder();
  const saved = props.getProperty("logSheetId");
  if (saved) {
    try {
      const f = DriveApp.getFileById(saved);
      if (!f.isTrashed()) {
        // 예전 테스트 때 다른 폴더(내 드라이브 등)에 만들어졌으면 제출물 폴더로 옮긴다
        let inFolder = false; const ps = f.getParents();
        while (ps.hasNext()) { if (ps.next().getId() === folder.getId()) inFolder = true; }
        if (!inFolder) { try { f.moveTo(folder); } catch (e) {} }
        return logTab(SpreadsheetApp.openById(saved));
      }
    } catch (e) {}
    props.deleteProperty("logSheetId");
  }
  const it = folder.getFilesByName(CFG.logSheetName);
  while (it.hasNext()) {
    const f = it.next();
    if (f.getMimeType() === MimeType.GOOGLE_SHEETS) { props.setProperty("logSheetId", f.getId()); return logTab(SpreadsheetApp.openById(f.getId())); }
  }
  const ss = SpreadsheetApp.create(CFG.logSheetName);
  try { DriveApp.getFileById(ss.getId()).moveTo(folder); } catch (e) {}
  props.setProperty("logSheetId", ss.getId());
  const sheet = ss.getSheets()[0];
  sheet.setName(CFG.logSheetName);
  sheet.appendRow(["제출시각", "학번", "이름", "문장수", "표현수", "화면이탈", "한글입력", "자동집계", "파일", "중복", "열쇠"]);
  sheet.setFrozenRows(1);
  return sheet;
}
// 제출명단 파일 안의 "제출명단" 탭 (없으면 첫 탭)
function logTab(ss) { return ss.getSheetByName(CFG.logSheetName) || ss.getSheets()[0]; }
// 제출명단 파일이 어디 있는지 알려 줍니다. 실행 후 아래 "실행 로그"에 뜨는 주소를 클릭하세요.
function whereIsLogSheet() {
  const sh = getLogSheet();
  const ss = sh.getParent();
  const f = DriveApp.getFileById(ss.getId());
  const parents = []; const ps = f.getParents();
  while (ps.hasNext()) parents.push(ps.next().getName());
  let owner = "(공유 드라이브)";
  try { const o = f.getOwner(); if (o) owner = o.getEmail(); } catch (e) {}
  Logger.log("제출명단 파일 주소: " + ss.getUrl());
  Logger.log("들어 있는 폴더: " + (parents.length ? parents.join(", ") : "(내 드라이브 최상위)"));
  Logger.log("소유 계정: " + owner + "   휴지통: " + (f.isTrashed() ? "예" : "아니오"));
  Logger.log("탭: " + ss.getSheets().map(function (x) { return x.getName(); }).join(", "));
  return ss.getUrl();
}
// 제출명단 파일을 못 찾을 때 한 번 실행: 저장된 연결을 지우고 폴더에서 다시 찾거나 새로 만듭니다.
function relinkLogSheet() {
  PropertiesService.getScriptProperties().deleteProperty("logSheetId");
  _sheetCache = {};                              // 보관해 둔 손잡이도 버리고 처음부터 다시 찾습니다
  whereIsLogSheet();
}

function num(text, re) { const m = String(text || "").match(re); return m ? Number(m[1]) : ""; }

/* ────────────────────────── 총괄 시트 ────────────────────────── */

const STATUS_LABEL = { research: "조사 중", draft: "초안 작성 중", draftDone: "초안 제출", final: "최종 작성 중", done: "최종 제출" };
const STATUS_COLOR = { "미접속": "#EEEEEE", "조사 중": "#E9F0FC", "초안 작성 중": "#DCE7FA", "초안 제출": "#FFF4CC", "최종 작성 중": "#FFE9B0", "최종 제출": "#DDF2EC" };

/* ── 색 규칙 ────────────────────────────────────────────────────
   숫자가 커질수록 진해집니다. 흰 칸 = 아무 일 없음. 선생님이 훑어볼 때 눈에 걸리게 하는 것이 목적입니다. */
const C_OK = "#FFFFFF", C_W1 = "#FFF8DC", C_W2 = "#FFE0B2", C_W3 = "#F8C9C4";
const C_HEAD = "#1B2436", C_HEADTX = "#FFFFFF", C_SUB = "#F2F4F7", C_STALE = "#F8C9C4", C_DUP = "#FCE4E1";

// 이탈: 1-2회 연노랑, 3-5회 주황, 6회 이상 빨강
function leaveColor(n) { n = Number(n) || 0; return n === 0 ? C_OK : n <= 2 ? C_W1 : n <= 5 ? C_W2 : C_W3; }
// 한글 입력·대량 입력처럼 한 번만 나와도 눈에 띄어야 하는 것
function strictColor(n) { n = Number(n) || 0; return n === 0 ? C_OK : n <= 2 ? C_W2 : C_W3; }
function dictColor(n) { n = Number(n) || 0; return n <= 20 ? C_OK : n <= 50 ? C_W1 : C_W2; }
// 반별 요약의 "이탈 있는 학생" 처럼 사람 수를 셀 때 (한 반 30명 기준)
function countColor(n) { n = Number(n) || 0; return n === 0 ? C_OK : n <= 3 ? C_W1 : n <= 8 ? C_W2 : C_W3; }

function classOf(sid) {
  const m = String(sid).match(/^(\d)(\d{2})/);
  return m ? (Number(m[1]) + "학년 " + Number(m[2]) + "반") : "기타";
}
function fmt(d) { return (d instanceof Date && !isNaN(d)) ? Utilities.formatDate(d, "Asia/Seoul", "MM-dd HH:mm") : (d ? String(d) : ""); }

/* 학생 현황 한 판을 그립니다. "총괄"(전체)과 반별 탭이 같은 함수를 씁니다.
   수업 중에 훑어보는 화면이므로 왼쪽부터 [이름 · 상태 · 이탈 · 한글 · 대량]을 놓고,
   숫자가 커질수록 칸 색이 진해집니다. 제출 시각·PDF 같은 것은 오른쪽에 둡니다. */
function writeStatusSheet(ss, sheetName, title, recs, withClass) {
  const HEAD = (withClass ? ["반"] : []).concat(
    ["학번", "이름", "상태", "이탈", "한글", "대량", "사전", "초안 문장", "표현", "최종 문장",
     "마지막 저장", "조용함", "첫 접속", "초안 제출", "최종 제출", "소요", "확인", "초안 PDF", "최종 PDF"]);
  const WIDTH = (withClass ? [80] : []).concat(
    [70, 96, 110, 62, 62, 62, 62, 76, 56, 76, 100, 66, 100, 100, 100, 116, 90, 130, 130]);
  // withClass=true 는 전체를 모은 "총괄", false 는 반별 탭.
  // 반별 탭은 수업 중에 훑어보는 화면이라 글자와 줄 높이를 키웁니다.
  const BIG = !withClass;

  let sh = ss.getSheetByName(sheetName);
  let fresh = false;
  if (!sh) { sh = ss.insertSheet(sheetName); fresh = true; }
  sh.clear();

  const stamp = Utilities.formatDate(new Date(), "Asia/Seoul", "MM-dd HH:mm:ss");
  const on = recs.filter((r) => r.status !== "미접속").length;
  const leaved = recs.filter((r) => Number(r.leave) > 0).length;
  const drafted = recs.filter((r) => r.phase === "draftDone" || r.phase === "final" || r.phase === "done").length;
  const doneN = recs.filter((r) => r.phase === "done").length;
  const staleN = recs.filter((r) => r.stale).length;

  // 1행: 제목 + 갱신 시각 / 2행: 한 줄 요약
  // 셀을 병합하지 않습니다. 병합한 줄이 고정 열 경계를 가로지르면
  // "병합된 셀의 일부만 포함된 열을 고정할 수 없습니다" 오류가 나면서 갱신이 통째로 멈춥니다.
  // 대신 배경색만 줄 전체에 칠하고 글자는 A열에 둡니다(옆 칸이 비어 있어 그대로 흘러 보입니다).
  sh.getRange(1, 1, 1, HEAD.length).setBackground(C_HEAD);
  sh.getRange(1, 1).setValue(title + "  ·  마지막 갱신 " + stamp)
    .setFontSize(13).setFontWeight("bold").setFontColor(C_HEADTX).setVerticalAlignment("middle");
  sh.setRowHeight(1, 30);
  // 이탈한 학생 이름을 바로 적어 둡니다. 표를 훑지 않아도 누구인지 보이게.
  const leaveNames = recs.filter((r) => Number(r.leave) > 0)
    .sort((a, b) => Number(b.leave) - Number(a.leave))
    .map((r) => r.name + " " + r.leave).slice(0, 12).join(", ");
  const staleNames = recs.filter((r) => r.stale).map((r) => r.name).slice(0, 8).join(", ");
  sh.getRange(2, 1, 1, HEAD.length).setBackground(leaved ? "#FFF1F0" : C_SUB);
  sh.getRange(2, 1).setValue(
    "인원 " + recs.length + "   접속 " + on + "   초안 제출 " + drafted + "   최종 제출 " + doneN +
    (leaved ? "        ⚠ 이탈 " + leaved + "명: " + leaveNames : "        이탈 없음") +
    (staleN ? "        ⏸ 조용함: " + staleNames : ""))
    .setFontSize(BIG ? 12 : 11).setFontWeight(leaved ? "bold" : "normal")
    .setFontColor(leaved ? "#B42318" : "#1B2436")
    .setVerticalAlignment("middle");
  sh.setRowHeight(2, BIG ? 32 : 24);

  // 3행: 열 이름
  sh.getRange(3, 1, 1, HEAD.length).setValues([HEAD])
    .setFontWeight("bold").setFontColor(C_HEADTX).setBackground("#3A4761")
    .setHorizontalAlignment("center").setVerticalAlignment("middle");
  sh.setRowHeight(3, 26);

  const body = recs.map((r) => (withClass ? [r.cls] : []).concat(
    [r.sid, r.name, r.status, r.leave, r.hangul, r.burst, r.dict, r.dCount, r.expr, r.fCount,
     r.at, r.stale ? r.stale + "분" : "", r.reg, r.draftAt, r.finalAt, r.spent,
     (r.dup ? "중복" : "") + (r.dup && r.note ? " · " : "") + r.note, r.pdf, r.finalPdf]));

  if (body.length) {
    const rng = sh.getRange(4, 1, body.length, HEAD.length);
    rng.setValues(body);
    // 색은 한 번에 칠합니다 (칸마다 부르면 갱신이 느려집니다)
    const o = withClass ? 1 : 0;
    const bg = recs.map((r) => {
      const row = new Array(HEAD.length).fill(C_OK);
      row[o + 2] = STATUS_COLOR[r.status] || C_OK;      // 상태
      row[o + 3] = leaveColor(r.leave);                 // 이탈
      row[o + 4] = strictColor(r.hangul);               // 한글
      row[o + 5] = strictColor(r.burst);                // 대량
      row[o + 6] = dictColor(r.dict);                   // 사전
      if (r.stale) { row[o + 10] = C_STALE; row[o + 11] = C_STALE; }   // 마지막 저장 / 조용함
      if (r.dup || r.note) row[o + 16] = C_DUP;         // 확인
      return row;
    });
    rng.setBackgrounds(bg);
    rng.setFontColors(recs.map((r) => {
      const row = new Array(HEAD.length).fill("#1B2436");
      if (Number(r.leave) > 5) row[o + 3] = "#B42318";
      if (Number(r.hangul) > 2) row[o + 4] = "#B42318";
      return row;
    }));
    // 숫자 칸은 가운데로, 이름은 왼쪽
    sh.getRange(4, o + 4, body.length, 7).setHorizontalAlignment("center");
    sh.getRange(4, o + 1, body.length, 1).setHorizontalAlignment("center");
    sh.getRange(4, 1, body.length, HEAD.length).setVerticalAlignment("middle");
    if (body.length > 1) sh.getRange(4, 1, body.length, HEAD.length).setBorder(null, null, null, null, null, true, "#E4E8EF", SpreadsheetApp.BorderStyle.SOLID);
    if (BIG) {
      // 이름·상태·이탈은 멀리서도 보이게 키웁니다
      sh.getRange(4, 1, body.length, HEAD.length).setFontSize(12);
      sh.getRange(4, o + 2, body.length, 1).setFontSize(14).setFontWeight("bold");   // 이름
      sh.getRange(4, o + 3, body.length, 1).setFontSize(13).setFontWeight("bold");   // 상태
      sh.getRange(4, o + 4, body.length, 1).setFontSize(16).setFontWeight("bold");   // 이탈
      sh.setRowHeights(4, body.length, 34);   // 한 줄씩 부르면 갱신이 느려집니다
    }
  }
  sh.setFrozenRows(3);
  sh.setFrozenColumns(withClass ? 3 : 2);
  // 열 너비는 clear() 로 지워지지 않으므로 시트를 처음 만들 때만 정합니다 (갱신이 1~2분마다 도니까)
  if (fresh) WIDTH.forEach((w, i) => sh.setColumnWidth(i + 1, w));
  return sh;
}

// "총괄"·반별 탭·"반별 요약"을 처음부터 다시 씁니다. 학생 요청이 오면 maybeRebuildOverview() 가 알아서 부릅니다.
function rebuildOverview() {
  // 잠금을 잡지 않습니다. 총괄·반별 탭은 학생 상태를 쓰는 "초안" 시트와 다른 탭이라 서로 안 부딪히고,
  // 여기서 잠금을 잡으면 갱신하는 몇 초 동안 30명의 저장이 줄을 서게 됩니다.
  // 갱신이 겹쳐 도는 것은 maybeRebuildOverview 의 시간 간격이 막아 줍니다.
  {
    const ss = SpreadsheetApp.openById(getLogSheet().getParent().getId());
    const ov = CFG.overview || {};
    const rows = overviewRows(draftSheet());

    // 명단(선택): A열 학번, B열 이름
    const roster = {};
    const rs = ss.getSheetByName(ov.rosterName || "명단");
    if (rs && rs.getLastRow() >= 2) {
      rs.getRange(2, 1, rs.getLastRow() - 1, 2).getValues().forEach((r) => { const id = String(r[0] || "").trim(); if (/^\d{3,}$/.test(id)) roster[id] = String(r[1] || "").trim(); });
    }
    const hasRoster = Object.keys(roster).length > 0;

    // 학생 한 명 = 기록 하나
    const recs = [];
    const seen = {};
    const now = Date.now();
    rows.forEach((r) => {
      const sid = String(r[COL.sid - 1] || "").trim(); if (!sid) return;
      seen[sid] = true;
      const meta = String(r[COL.meta - 1] || "");
      const phase = String(r[COL.phase - 1] || "research");
      const name = String(r[COL.name - 1] || "");
      const at = r[COL.at - 1];
      const writing = phase === "research" || phase === "draft" || phase === "final";
      // 쓰고 있어야 하는데 3분 넘게 저장이 없으면 기기가 끊어진 것일 수 있습니다.
      const quietMin = (at instanceof Date && !isNaN(at)) ? Math.floor((now - at.getTime()) / 60000) : -1;
      recs.push({
        cls: classOf(sid), sid: sid, name: name, status: STATUS_LABEL[phase] || phase, phase: phase,
        leave: num(meta, /화면이탈 (\d+)/), hangul: num(meta, /한글입력 (\d+)/), hangulSel: num(meta, /한글선택 (\d+)/),
        burst: num(meta, /대량입력 (\d+)/), auto: num(meta, /자동완성차단 (\d+)/), dict: num(meta, /사전 (\d+)/),
        dCount: r[COL.count - 1] || "", fCount: phase === "done" ? num(meta, /최종 문장 (\d+)/) : "",
        expr: phase === "done" ? num(meta, /표현 (\d+)/) : num(meta, /\(표현 (\d+)\)/),
        reg: fmt(r[COL.reg - 1]), at: fmt(at), draftAt: fmt(r[COL.draftAt - 1]), finalAt: fmt(r[COL.finalAt - 1]),
        spent: pick(meta, /소요 ([^|]+)/) === "-" ? "" : pick(meta, /소요 ([^|]+)/).replace(/조사|초안|최종/g, "").replace(/\s+/g, " ").trim(),
        dup: String(r[COL.dup - 1] || "") === "Y",
        note: hasRoster ? (roster[sid] ? (roster[sid] === name.trim() ? "" : "이름 다름") : "명단에 없음") : "",
        stale: writing && quietMin >= 3 ? quietMin : 0,
        pdf: String(r[COL.pdf - 1] || ""), finalPdf: String(r[COL.finalPdf - 1] || "")
      });
    });
    if (hasRoster) Object.keys(roster).forEach((sid) => {
      if (seen[sid]) return;
      recs.push({ cls: classOf(sid), sid: sid, name: roster[sid], status: "미접속", phase: "", leave: "", hangul: "", hangulSel: "",
        burst: "", auto: "", dict: "", dCount: "", fCount: "", expr: "", reg: "", at: "", draftAt: "", finalAt: "",
        spent: "", dup: false, note: "", stale: 0, pdf: "", finalPdf: "" });
    });
    recs.sort((a, b) => (Number(a.sid) - Number(b.sid)) || ((a.dup ? 1 : 0) - (b.dup ? 1 : 0)));

    writeStatusSheet(ss, ov.name || "총괄", "전체", recs, true);

    // 반별 탭: 수업 들어가서 그 반 탭만 보면 됩니다
    const classes = {};
    recs.forEach((r) => { (classes[r.cls] || (classes[r.cls] = [])).push(r); });
    Object.keys(classes).sort().forEach((cls) => {
      if (cls === "기타") return;
      writeStatusSheet(ss, cls, cls, classes[cls], false);
    });

    // 반별 요약 (학생 단위로 셈: 같은 학번의 여러 줄은 가장 앞선 상태 하나로)
    const RANK = { "미접속": 0, "조사 중": 1, "초안 작성 중": 2, "초안 제출": 3, "최종 작성 중": 4, "최종 제출": 5 };
    const best = {};
    recs.forEach((r) => {
      if (!best[r.sid] || (RANK[r.status] || 0) > (RANK[best[r.sid].status] || 0)) best[r.sid] = { cls: r.cls, status: r.status, dup: best[r.sid] ? best[r.sid].dup : false, leave: r.leave };
      if (r.dup) best[r.sid].dup = true;
      if (Number(r.leave) > Number(best[r.sid].leave || 0)) best[r.sid].leave = r.leave;
    });
    const byClass = {};
    Object.keys(best).forEach((k) => {
      const b = best[k];
      const c = byClass[b.cls] || (byClass[b.cls] = { total: 0, on: 0, draft: 0, done: 0, dup: 0, leave: 0 });
      c.total++;
      if ((RANK[b.status] || 0) >= 1) c.on++;
      if ((RANK[b.status] || 0) >= 3) c.draft++;
      if ((RANK[b.status] || 0) >= 5) c.done++;
      if (b.dup) c.dup++;
      if (Number(b.leave) > 0) c.leave++;
    });
    const sum = Object.keys(byClass).sort().map((k) => [k, byClass[k].total, byClass[k].on, byClass[k].draft, byClass[k].done, byClass[k].leave, byClass[k].dup]);
    let ssh = ss.getSheetByName(ov.summaryName || "반별 요약");
    let sfresh = false;
    if (!ssh) { ssh = ss.insertSheet(ov.summaryName || "반별 요약"); sfresh = true; }
    ssh.clear();
    const sumHead = ["반", hasRoster ? "명단 인원" : "접속 인원(명단 없음)", "접속", "초안 제출", "최종 제출", "이탈 있는 학생", "중복"];
    ssh.getRange(1, 1, 1, sumHead.length).setValues([sumHead]).setFontWeight("bold").setFontColor(C_HEADTX).setBackground(C_HEAD);
    if (sum.length) {
      ssh.getRange(2, 1, sum.length, sumHead.length).setValues(sum);
      ssh.getRange(2, 2, sum.length, sumHead.length - 1).setHorizontalAlignment("center");
      ssh.getRange(2, 6, sum.length, 1).setBackgrounds(sum.map((x) => [countColor(x[5])]));
    }
    ssh.setFrozenRows(1);
    if (sfresh) [90, 90, 60, 80, 80, 100, 60].forEach((w, i) => ssh.setColumnWidth(i + 1, w));
    ssh.getRange(sum.length + 3, 1).setValue("마지막 갱신 " + Utilities.formatDate(new Date(), "Asia/Seoul", "MM-dd HH:mm:ss"));
  }
}

/* ── 총괄 시트 자동 갱신 (선생님이 아무것도 하지 않아도 됩니다) ──────────────
   학생 요청이 들어온 김에 총괄을 다시 씁니다. 단, 마지막 갱신에서 OV_INTERVAL_SEC 이 지났을 때만.
   그래서 30명이 한꺼번에 저장하거나 제출해도 그 중 딱 한 명의 요청만 갱신 비용을 냅니다.
   그 요청은 몇 초 길어지지만 no-cors 로 보내는 저장이라 학생 화면은 기다리지 않습니다.

   ※ 예전에는 시간 트리거(ScriptApp.newTrigger)로 예약했는데, 웹 앱에 script.scriptapp 권한이 없어서
     매번 실패했습니다(오류 탭에 "권한이 없습니다"). 권한을 다시 승인받게 하는 대신, 권한이 필요 없는
     이 방식으로 바꿨습니다. 이 파일에서 ScriptApp 을 다시 쓰면 같은 문제가 납니다. */

const OV_INTERVAL_SEC = 60;       // 이 시간에 한 번만 총괄을 다시 씁니다

function maybeRebuildOverview(force) {
  try {
    const props = PropertiesService.getScriptProperties();
    const now = Date.now();
    if (!force) {
      const at = Number(props.getProperty("ovAt") || 0);
      if (at && (now - at) < OV_INTERVAL_SEC * 1000) return;    // 아직 이릅니다
    }
    props.setProperty("ovAt", String(now));   // 먼저 찍어 둡니다 (겹쳐 들어온 요청이 또 돌지 않게)
    rebuildOverview();
  } catch (e) { logError("총괄 갱신", e, ""); }
}
// 총괄이 안 바뀔 때 편집기에서 한 번 실행하면 지금 즉시 다시 씁니다.
function resetOverviewSchedule() {
  try { PropertiesService.getScriptProperties().deleteProperty("ovAt"); } catch (e) {}
  maybeRebuildOverview(true);
  Logger.log("총괄을 지금 다시 썼습니다.");
}

/* ────────────────────────── 선생님 현황 화면 ──────────────────────────
   docs/teacher.html 이 몇 초마다 이 함수를 읽어 갑니다. 시트를 쓰지 않고 읽기만 하므로 자주 불러도 됩니다.

   학생 이름·학번이 보이는 화면이라 아무나 열면 안 됩니다. 열쇠는 **코드에 적지 않습니다**.
   이 파일은 공개 저장소에 올라가므로 코드에 적으면 누구나 볼 수 있습니다. 스크립트 속성에 보관합니다.
   편집기에서 newTeacherKey() 를 한 번 실행하면 열쇠를 만들고 열 주소를 실행 로그에 찍어 줍니다. */

function newTeacherKey() {
  const k = (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, "").slice(0, 40);
  PropertiesService.getScriptProperties().setProperty("teacherKey", k);
  Logger.log("─────────────────────────────────────────────");
  Logger.log("선생님 현황 화면 주소입니다. 북마크해 두세요:");
  Logger.log(CFG.teacherPage + "?k=" + k);
  Logger.log("─────────────────────────────────────────────");
  Logger.log("이 주소를 아는 사람은 학생 현황을 볼 수 있습니다. 학생에게 알려 주지 마세요.");
  Logger.log("주소가 새 나갔다고 생각되면 newTeacherKey() 를 다시 실행하면 예전 주소는 막힙니다.");
  return k;
}
function teacherKey() { try { return PropertiesService.getScriptProperties().getProperty("teacherKey") || ""; } catch (e) { return ""; } }
function ms(d) { return (d instanceof Date && !isNaN(d)) ? d.getTime() : 0; }

function monitorData(cls, key) {
  const want = teacherKey();
  if (!want) return { error: "NO_TEACHER_KEY" };            // 아직 newTeacherKey() 를 실행하지 않음
  if (String(key || "") !== want) return { error: "BAD_KEY" };
  const out = { ok: true, at: Date.now(), cls: cls || "", classes: [], students: [] };
  try {
    const sh = draftSheet();
    const last = sh.getLastRow();
    const seenCls = {};
    const seenSid = {};
    if (last >= 2) {
      const n = last - 1;
      const a = sh.getRange(2, 1, n, 8).getValues();          // 학번 … 자동집계
      const b = sh.getRange(2, COL.dup, n, 3).getValues();    // 중복, 초안제출시각, 최종제출시각
      for (let i = 0; i < n; i++) {
        const sid = String(a[i][COL.sid - 1] || "").trim();
        if (!sid) continue;
        const c = classOf(sid);
        if (!seenCls[c]) { seenCls[c] = true; out.classes.push(c); }
        if (cls && c !== cls) continue;
        seenSid[sid] = true;
        const meta = String(a[i][COL.meta - 1] || "");
        out.students.push({
          sid: sid, nm: String(a[i][COL.name - 1] || ""), ph: String(a[i][COL.phase - 1] || "research"),
          lv: Number(num(meta, /화면이탈 (\d+)/) || 0), hg: Number(num(meta, /한글입력 (\d+)/) || 0),
          bs: Number(num(meta, /대량입력 (\d+)/) || 0), dc: Number(num(meta, /사전 (\d+)/) || 0),
          sn: Number(a[i][COL.count - 1] || 0),
          at: ms(a[i][COL.at - 1]), dr: ms(b[i][1]), fn: ms(b[i][2]),
          dup: String(b[i][0] || "") === "Y"
        });
      }
    }
    // "명단" 탭이 있으면 아직 한 번도 안 들어온 학생도 보여 줍니다 (누가 안 들어왔는지가 제일 급하므로)
    const ss = SpreadsheetApp.openById(getLogSheet().getParent().getId());
    const rs = ss.getSheetByName((CFG.overview || {}).rosterName || "명단");
    if (rs && rs.getLastRow() >= 2) {
      rs.getRange(2, 1, rs.getLastRow() - 1, 2).getValues().forEach((r) => {
        const id = String(r[0] || "").trim();
        if (!/^\d{3,}$/.test(id)) return;
        const c = classOf(id);
        if (!seenCls[c]) { seenCls[c] = true; out.classes.push(c); }
        if (cls && c !== cls) return;
        if (seenSid[id]) return;
        out.students.push({ sid: id, nm: String(r[1] || "").trim(), ph: "", lv: 0, hg: 0, bs: 0, dc: 0, sn: 0, at: 0, dr: 0, fn: 0, dup: false });
      });
    }
    out.classes.sort();
    out.students.sort((x, y) => Number(x.sid) - Number(y.sid));
  } catch (e) {
    logError("현황 화면 읽기", e, cls);
    return { error: "READ_FAIL" };
  }
  return out;
}

/* ────────────────────────── 오류 기록 · PDF 다시 만들기 ────────────────────────── */

function logError(where, err, extra) {
  try {
    const ss = SpreadsheetApp.openById(getLogSheet().getParent().getId());
    let sh = ss.getSheetByName("오류");
    if (!sh) { sh = ss.insertSheet("오류"); sh.appendRow(["시각", "위치", "오류", "상세"]); sh.setFrozenRows(1); }
    sh.appendRow([new Date(), where, String(err && err.message || err), (String(err && err.stack || "").slice(0, 1500) + " | " + String(extra || "").slice(0, 300))]);
  } catch (e) {}
}

// 학생 한 명의 초안 PDF(또는 최종 PDF)를 시트에 저장된 내용으로 다시 만듭니다. 편집기에서 학번을 넣어 실행하세요.
// 예) regeneratePdf("10315", "draft")  /  regeneratePdf("10315", "final")
// 같은 학번 줄이 여러 개(중복)면 세 번째 값으로 [기기열쇠] 앞부분을 넣어 어느 줄인지 지정하세요.
//   예) regeneratePdf("10315", "final", "a1b2c3")
function regeneratePdf(sid, kind, keyPrefix) {
  kind = kind || "draft";
  const sh = draftSheet();
  const rows = allRows(sh);
  const hits = [];
  for (let i = 0; i < rows.length; i++) if (String(rows[i][COL.sid - 1]) === String(sid)) hits.push(i);
  if (!hits.length) throw new Error("학번 " + sid + " 줄이 없습니다.");
  let idx;
  if (keyPrefix) {
    const pick2 = hits.filter((i) => String(rows[i][COL.key - 1] || "").indexOf(String(keyPrefix)) === 0);
    if (!pick2.length) throw new Error("학번 " + sid + " 에서 열쇠가 \"" + keyPrefix + "\" 로 시작하는 줄이 없습니다.");
    idx = pick2[0];
  } else if (hits.length > 1) {
    throw new Error("학번 " + sid + " 줄이 " + hits.length + "개입니다(중복). 세 번째 값으로 열쇠 앞부분을 넣어 지정하세요: " +
      hits.map((i) => String(rows[i][COL.key - 1] || "(빈 열쇠)").slice(0, 6)).join(", "));
  } else idx = hits[0];

  const r = rows[idx];
  // 깨진 데이터를 조용히 넘기면 빈 PDF를 만들어 멀쩡한 링크를 덮어씁니다. 그래서 여기서 멈춥니다.
  let st = {};
  const raw = String(r[COL.json - 1] || "");
  if (raw) {
    try { st = JSON.parse(raw); }
    catch (e) { throw new Error("데이터(JSON) 칸을 읽을 수 없습니다 (길이 " + raw.length + "). 최종본이 여기에만 있으므로 PDF를 만들지 않았습니다. 오류: " + e.message); }
  }
  const finalText = String(st.final || "");
  if (kind === "final" && !finalText.trim()) throw new Error("저장된 최종본이 비어 있습니다. 기존 PDF 링크를 지우지 않으려고 만들지 않았습니다.");

  const bank = parseBank(PropertiesService.getScriptProperties().getProperty("bank") || "[]");
  const d = { sid: String(r[COL.sid - 1]), name: String(r[COL.name - 1] || ""), key: String(r[COL.key - 1] || ""), title: st.title || "영어 쓰기 수행평가", subtitle: st.subtitle || "",
    brainstorm: String(r[COL.brain - 1] || ""), draft: String(r[COL.draft - 1] || ""), final: finalText, meta: String(r[COL.meta - 1] || ""), bank: bank,
    dup: String(r[COL.dup - 1] || "") === "Y" };
  const files = savePdf(d, kind);   // 오류가 나면 편집기에 그대로 표시됩니다
  const url = files[0].getUrl();
  sh.getRange(idx + 2, kind === "final" ? COL.finalPdf : COL.pdf).setValue(url);
  Logger.log("만들어졌습니다: " + url);
  return url;
}

/* ────────────────────────── 메일 보내기 ────────────────────────── */

function sendMail(d, files) {
  const subject = CFG.subjectPrefix + " " + d.sid + " " + d.name;
  const bodyText =
    "학번: " + d.sid + "\n이름: " + d.name + "\n" +
    "제출: " + Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm") + "\n\n" +
    "[자동 집계]\n" + (d.meta || "-") + "\n\n" +
    "[최종본]\n" + (d.final || "(비어 있음)") + "\n";
  const opts = { to: CFG.notifyEmail, subject: subject, body: bodyText };
  if (CFG.attachToEmail) opts.attachments = files.map(function (f) { return f.getAs(f.getMimeType()); });
  MailApp.sendEmail(opts);
}

/* ────────────────────────── 도우미 ────────────────────────── */

function cut(s, n) { s = String(s); return s.length > n ? s.slice(0, n) + " …(생략)" : s; }
function textOut(msg) { return ContentService.createTextOutput(msg).setMimeType(ContentService.MimeType.TEXT); }

/* ────────────────────────── 테스트 ──────────────────────────
   함수 목록에서 testSubmit 을 고르고 "실행"을 누르면 샘플이 하나 처리됩니다. */

function testDraft() {
  const reg = loadOrRegister("10315", "김하늘", "");
  const bank = JSON.stringify([{ label: "rely on", source: "\\brel(?:y|ies|ied|ying)\\s+on\\b", flags: "i" }, { label: "a place where", source: "\\bplace\\s+where\\b", flags: "i" }]);
  doPost({ parameter: { token: CFG.token, phase: "draft", sid: "10315", name: "김하늘", key: reg.key,
    title: "Good for All of Us: A Place for Everyone", subtitle: "1학년 2학기 영어 쓰기 수행평가", bank: bank,
    brainstorm: "[Step 1]\nOpening: 1-4\n\n[Step 2]\n1. Place 학교 도서관\n2. Problem 입구에 계단이 있다",
    draft: "Part 1. Opening\n(1) Our school library is a place where many students study.\n(2) Many students rely on it.\n(3) \n\nPart 2. Suggestions & Expected Effects\n(4) First, we should build a ramp.",
    meta: "초안 문장 3 (표현 2) | 화면이탈 0회 | 한글입력 0회 | 한글선택 0회 | 대량입력 0회 | 사전 1회 [경사로→ramp]",
    data: JSON.stringify({ sid: "10315", name: "김하늘", phase: "draftDone", savedAt: Date.now(), draft: [["Our school library is a place where many students study.", "Many students rely on it.", ""], ["First, we should build a ramp.", "", "", ""], ["", ""]], final: "" }) } });
  Logger.log(JSON.stringify(loadOrRegister("10315", "김하늘", reg.key)).slice(0, 200));
}

function testSubmit() {
  const reg = loadOrRegister("10315", "김하늘", "");
  const bank = JSON.stringify([{ label: "rely on", source: "\\brel(?:y|ies|ied|ying)\\s+on\\b", flags: "i" }, { label: "make it easier for A to B", source: "\\bmake\\s+it\\s+easier\\b", flags: "i" }, { label: "regardless of", source: "\\bregardless\\s+of\\b", flags: "i" }]);
  doPost({ parameter: {
    token: CFG.token, phase: "final", key: reg.key,
    sid: "10315", name: "김하늘",
    title: "Good for All of Us: A Place for Everyone",
    subtitle: "1학년 2학기 영어 쓰기 수행평가", bank: bank,
    brainstorm: "[Step 1]\nOpening: 1-4\n\n[Step 2]\n1. Place 학교 도서관\n2. Problem 입구에 계단이 있다",
    draft: "Part 1. Opening\n(1) Our school library is a place where many students study.\n(2) Many students rely on it.",
    final: "Our school library is a place where many students study. Many students rely on it. However, the entrance has three steps. First, we should build a ramp. This will make it easier for everyone to enter. They will benefit everyone, regardless of age.",
    meta: "최종 문장 6 | 표현 3/9 (rely on, make it easier for A to B, regardless of) | 초안 문장 2 (표현 1) | 화면이탈 1회 [14:02 탭/앱 전환(초안)] | 한글입력 0회 | 한글선택 0회 | 대량입력 0회 | 사전 2회 [경사로→ramp, 표지판→sign] | 환경 홈화면앱 | 소요 조사 12분 / 초안 18분 / 최종 15분"
  }});
}

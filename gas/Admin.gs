/* ────────────────────────── 선생님 정리 (교사 열쇠) ──────────────────────────
   2026-10-29: 수업이 끝난 뒤 남은 줄을 정리하려고 만들었습니다. 현황 화면과 같은 교사 열쇠로만 됩니다.
   바꾸는 일(rename/hide/mergeFinal)은 오늘 백업(op=backup)을 먼저 해야만 합니다.
   한 일은 오류 탭에 "선생님 정리(정상 처리)"로 남습니다.

   op=inspect  sids=10208,10233   그 학번 줄들의 상태(글 내용 없이: 단계·시각·자동집계·단계 기록·교사 조작)와 오류 탭의 그 학번 줄
   op=backup                      제출명단 파일 전체를 같은 폴더에 복사 ("백업 MMdd-HHmm …")
   op=rename   sid kp name        이름 고치기 (시트·데이터 칸, 명단 확인 표시 지움, PDF 다시 만듦)
   op=hide     sid kp             남은 줄 숨기기 (중복 칸 "이어받음", 열쇠 칸 "이어받음 정리 …") — 지우지 않음
   op=mergeFinal sid kp fsid fkp  다른 줄(fsid/fkp)의 최종 글을 이 줄에 붙이고 최종 PDF 를 이 줄 이름·학번으로 다시 만든 뒤 그 줄은 숨김
   kp = [기기열쇠] 앞 6자 (inspect 로 확인) */
function adminFix(p) {
  const want = teacherKey();
  if (!want || String(p.k || "") !== want) return { error: "BAD_KEY" };
  const op = String(p.op || "");
  if (op === "inspect") return adminInspect(String(p.sids || "").split(",").map((s) => s.trim()).filter(Boolean).slice(0, 20));
  if (op === "backup") return adminBackup();
  if (!adminBackedUpToday()) return { error: "NO_BACKUP", hint: "op=backup 을 먼저 하세요" };
  return withLock(30000, "선생님 정리 " + op, function () {
    const sh = draftSheet();
    const rows = allRows(sh);
    const find = (sid, kp) => {
      const hits = [];
      for (let i = 0; i < rows.length; i++) {
        if (String(rows[i][COL.sid - 1]).trim() === String(sid).trim() && String(rows[i][COL.key - 1] || "").indexOf(String(kp || "")) === 0 && !isMerged(rows[i])) hits.push(i);
      }
      return hits.length === 1 ? hits[0] : -1;
    };
    const stamp = Utilities.formatDate(new Date(), "Asia/Seoul", "MM-dd HH:mm");
    const i = find(p.sid, p.kp);
    if (i < 0 || String(p.kp || "").length < 6) return { error: "NO_ROW", hint: "학번과 열쇠 앞 6자로 줄 하나를 정확히 가리켜 주세요" };
    const rowNo = i + 2, r = rows[i];
    const key = String(r[COL.key - 1] || "");
    const clearRm = () => { try { PropertiesService.getScriptProperties().deleteProperty("rmiss:" + key); } catch (e) {} };
    const done = (what) => {
      try { CacheService.getScriptCache().remove("mon_all"); } catch (e) {}
      logError("선생님 정리(정상 처리)", new Error("학번 " + p.sid + " " + rowNo + "행: " + what), "");
    };

    if (op === "hide") {
      sh.getRange(rowNo, COL.key).setValue("이어받음 정리 " + stamp);
      sh.getRange(rowNo, COL.dup).setValue("이어받음");
      clearRm();
      done("숨김");
      return { ok: true, row: rowNo };
    }

    if (op === "rename") {
      const name = String(p.name || "").trim();
      if (!name || name.length > 20) return { error: "BAD_NAME" };
      sh.getRange(rowNo, COL.name).setValue(safeCell(name));
      const raw = String(r[COL.json - 1] || "");
      if (raw) {
        const st = JSON.parse(raw);           // 깨져 있으면 여기서 멈춤 (아무것도 덮지 않게)
        st.name = name;
        sh.getRange(rowNo, COL.json).setValue(JSON.stringify(st));
      }
      clearRm();
      SpreadsheetApp.flush();
      const ph = String(r[COL.phase - 1] || "");
      const pdfs = {};
      if (r[COL.pdf - 1] && (PHASE_ORDER[ph] || 0) >= PHASE_ORDER.draftDone) pdfs.draft = regeneratePdf(String(p.sid), "draft", String(p.kp));
      if (r[COL.finalPdf - 1] && ph === "done") pdfs.final = regeneratePdf(String(p.sid), "final", String(p.kp));
      done("이름 고침, PDF " + Object.keys(pdfs).join("·"));
      return { ok: true, row: rowNo, pdfs: Object.keys(pdfs) };
    }

    if (op === "mergeFinal") {
      const j = find(p.fsid, p.fkp);
      if (j < 0 || j === i || String(p.fkp || "").length < 6) return { error: "NO_SOURCE" };
      const s = rows[j];
      if (String(s[COL.phase - 1]) !== "done") return { error: "SOURCE_NOT_DONE" };
      if (nameKey(s[COL.name - 1]) !== nameKey(r[COL.name - 1])) return { error: "NAME_DIFFERS" };
      if ((PHASE_ORDER[String(r[COL.phase - 1])] || 0) >= PHASE_ORDER.final) return { error: "TARGET_HAS_FINAL" };
      const sst = JSON.parse(String(s[COL.json - 1] || "{}"));
      const tst = JSON.parse(String(r[COL.json - 1] || "{}"));
      if (!String(sst.final || "").trim()) return { error: "SOURCE_EMPTY" };
      tst.final = sst.final;
      tst.phase = "done"; tst.submitted = true; tst.submittedAt = sst.submittedAt || ms(s[COL.finalAt - 1]); tst.submitReason = sst.submitReason || "";
      tst.phaseLog = Object.assign({}, tst.phaseLog || {}, { finalStart: (sst.phaseLog || {}).finalStart, finalEnd: (sst.phaseLog || {}).finalEnd, finalFrom: String(p.fsid) + " 줄에서 옮김 " + stamp });
      tst.leaves = (tst.leaves || []).concat(sst.leaves || []);
      tst.hangul = (tst.hangul || 0) + (sst.hangul || 0); tst.hangulSel = (tst.hangulSel || 0) + (sst.hangulSel || 0);
      tst.lookups = (tst.lookups || []).concat(sst.lookups || []);
      tst.tlog = (tst.tlog || []).concat([{ t: Date.now(), m: "선생님 정리: 2회차 글을 " + p.fsid + " 줄에서 옮김" }]);
      sh.getRange(rowNo, COL.json).setValue(JSON.stringify(tst));
      sh.getRange(rowNo, COL.phase).setValue("done");
      sh.getRange(rowNo, COL.at).setValue(s[COL.at - 1]);
      sh.getRange(rowNo, COL.finalAt).setValue(s[COL.finalAt - 1]);
      sh.getRange(rowNo, COL.meta).setValue(safeCell(String(r[COL.meta - 1] || "") + " / 2회차: " + p.fsid + " 줄에서 옮김(" + String(s[COL.meta - 1] || "").slice(0, 400) + ")"));
      sh.getRange(j + 2, COL.key).setValue("이어받음 정리 " + stamp);
      sh.getRange(j + 2, COL.dup).setValue("이어받음");
      try { PropertiesService.getScriptProperties().deleteProperty("rmiss:" + String(s[COL.key - 1] || "")); } catch (e) {}
      SpreadsheetApp.flush();
      const url = regeneratePdf(String(p.sid), "final", String(p.kp));
      done("2회차 글을 " + p.fsid + " " + (j + 2) + "행에서 옮김, 최종 PDF 다시 만듦");
      return { ok: true, row: rowNo, from: j + 2, finalPdf: !!url };
    }
    return { error: "BAD_OP" };
  }, true);
}

function adminBackedUpToday() {
  const v = PropertiesService.getScriptProperties().getProperty("adminBackup") || "";
  return v.indexOf(Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd")) === 0;
}

function adminBackup() {
  const ss = logBook();
  const file = DriveApp.getFileById(ss.getId());
  const parents = file.getParents();
  const name = "백업 " + Utilities.formatDate(new Date(), "Asia/Seoul", "MMdd-HHmm") + " " + file.getName();
  const copy = parents.hasNext() ? file.makeCopy(name, parents.next()) : file.makeCopy(name);
  PropertiesService.getScriptProperties().setProperty("adminBackup", Utilities.formatDate(new Date(), "Asia/Seoul", "yyyy-MM-dd HH:mm") + " " + copy.getId());
  logError("선생님 정리(정상 처리)", new Error("백업 만듦: " + name), "");
  return { ok: true, name: name, id: copy.getId() };
}

// 글 내용(조사·초안·최종·사전 검색어)은 돌려주지 않습니다. 길이·개수·시각만.
function adminInspect(sids) {
  const want = {}; sids.forEach((s) => { want[s] = true; });
  const rows = allRows(draftSheet());
  const props = PropertiesService.getScriptProperties();
  const t = (v) => (v instanceof Date && !isNaN(v)) ? Utilities.formatDate(v, "Asia/Seoul", "MM-dd HH:mm:ss") : (typeof v === "number" && v ? Utilities.formatDate(new Date(v), "Asia/Seoul", "MM-dd HH:mm:ss") : String(v || ""));
  const out = { ok: true, rows: [], errors: [] };
  rows.forEach((r, i) => {
    const sid = String(r[COL.sid - 1]).trim();
    if (!want[sid]) return;
    let st = {}, broken = false;
    try { st = JSON.parse(String(r[COL.json - 1] || "{}")) || {}; } catch (e) { broken = true; }
    const L = st.phaseLog || {};
    const pl = {}; Object.keys(L).forEach((k) => { pl[k] = typeof L[k] === "number" ? t(L[k]) : String(L[k]).slice(0, 80); });
    out.rows.push({
      row: i + 2, sid: sid, kp: String(r[COL.key - 1] || "").slice(0, 6), dup: String(r[COL.dup - 1] || ""),
      reg: t(r[COL.reg - 1]), at: t(r[COL.at - 1]), phase: String(r[COL.phase - 1] || ""), dr: t(r[COL.draftAt - 1]), fn: t(r[COL.finalAt - 1]),
      count: r[COL.count - 1], meta: String(r[COL.meta - 1] || "").slice(0, 600), rm: props.getProperty("rmiss:" + String(r[COL.key - 1] || "")) || "",
      json: broken ? "깨짐" : { phase: st.phase, startedAt: t(st.startedAt), phaseStartedAt: t(st.phaseStartedAt), savedAt: t(st.savedAt), env: st.env,
        submitted: st.submitted, draftReason: st.draftReason, submitReason: st.submitReason, phaseLog: pl,
        hangul: st.hangul, hangulSel: st.hangulSel, bursts: st.bursts, autoText: st.autoText, leaves: (st.leaves || []).length, lookups: (st.lookups || []).length,
        tlog: (st.tlog || []).map((x) => t(x.t) + " " + String(x.m || x.a || "").slice(0, 60)),
        finalLen: String(st.final || "").length, draftLines: (st.draft || []).reduce((a, p) => a + (p || []).filter((x) => String(x).trim()).length, 0) }
    });
  });
  const es = logBook().getSheetByName("오류");
  if (es && es.getLastRow() >= 2) {
    es.getRange(2, 1, es.getLastRow() - 1, 4).getValues().forEach((e) => {
      const s = String(e[2]) + " " + String(e[3]);
      if (sids.some((x) => s.indexOf(x) >= 0)) out.errors.push(t(e[0]) + " | " + e[1] + " | " + String(e[2]).slice(0, 200));
    });
  }
  return out;
}

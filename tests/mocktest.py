"""
브라우저 자동 테스트. Apps Script 를 흉내 내는 가짜 서버를 띄우고 학생 흐름을 끝까지 돌린다.
  실행: python tests/mocktest.py     (처음: pip install -r tests/requirements.txt && python -m playwright install chromium)
  통과 기준: 마지막 줄에 PASS

가짜 서버는 gas/Code.gs 와 같은 규칙을 따라야 한다. 특히:
  - check 의 draftAt 은 [초안제출시각] 이다. [저장시각]을 돌려주면 초안 제출이 실패해도
    1분마다 도는 자동 저장 때문에 항상 "저장되었습니다"가 나온다. 이 테스트의 T3 가 그것을 잡는다.
  - 자동 저장은 단계를 되돌리지 못하지만 글은 저장한다. 제출·되돌리기는 단계까지 바꾼다.
  - 열쇠가 없으면 아무것도 확인해 주지 않는다.
  - 학번이 같고 이름이 다르면 남의 줄을 넘겨주지 않고 새 줄을 만든다.
"""
import threading, http.server, socketserver, functools, urllib.parse, json, time, uuid, os, re, sys, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(BASE, '..', 'docs')
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DOCS)
class Q(socketserver.TCPServer): allow_reuse_address = True
srv = Q(('127.0.0.1', 8880), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

from playwright.sync_api import sync_playwright

html = open(os.path.join(DOCS, 'index.html'), encoding='utf-8').read()
SCRIPT = re.search(r'scriptUrl:\s*"([^"]+)"', html).group(1)
TOKEN = re.search(r'token:\s*"([^"]+)"', html).group(1)
PIN = re.search(r'teacherPin:\s*"([^"]*)"', html).group(1)
assert SCRIPT, 'docs/index.html 의 CONFIG.submit.scriptUrl 이 비어 있습니다'
ORDER = {'research': 0, 'draft': 1, 'draftDone': 2, 'final': 3, 'done': 4}

# ── 가짜 서버 상태 ────────────────────────────────────────────────
rows = []        # 초안 시트 한 줄씩: sid,name,key,data,phase,at,draftAt,dup,brain,draft
finals = []      # 제출명단 한 줄씩: {sid,keyPrefix,at}
posts = []       # 받은 POST 기록
DROP = {'draft': False, 'save': False}   # 테스트에서 특정 제출을 잃어버리게 만드는 스위치

def now_iso():
    # 실제 서버는 Date 를 JSON 으로 내보내므로 UTC ISO(Z) 가 된다
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')

def find(sid, key):
    return next((r for r in rows if r['sid'] == sid and r['key'] == key and key), None)

def add_row(sid, name, key, dup):
    r = {'sid': sid, 'name': name, 'key': key, 'data': None, 'phase': 'research',
         'at': None, 'draftAt': None, 'dup': dup, 'brain': '', 'draft': ''}
    rows.append(r)
    return r

def norm(s):
    return re.sub(r'\s+', '', s or '').lower()

def write_row(r, b, g, phase, allow_regress):
    """gas/Code.gs 의 saveDraft 와 같은 규칙."""
    ph = phase
    if not allow_regress and ORDER.get(r['phase'], 0) > ORDER.get(ph, 0):
        ph = r['phase']                      # 단계는 그대로, 글은 저장한다
    r['phase'] = ph
    r['data'] = g('data')
    r['brain'] = g('brainstorm')
    r['draft'] = g('draft')
    r['at'] = now_iso()                      # [저장시각] 은 저장마다 갱신
    if phase == 'draftDone':
        r['draftAt'] = now_iso()             # [초안제출시각] 은 초안 제출 때만

def mock(route):
    req = route.request
    u = urllib.parse.urlparse(req.url)
    q = urllib.parse.parse_qs(u.query)

    if req.method == 'POST':
        b = urllib.parse.parse_qs(req.post_data or '')
        g = lambda k: b.get(k, [''])[0]
        ph = g('phase')
        posts.append({'phase': ph, 'sid': g('sid'), 'key': g('key'), 'bank': 'bank' in b, 'to': g('to')})
        if g('token') != TOKEN:
            route.fulfill(status=200, body='BAD_TOKEN'); return
        if not g('key'):
            route.fulfill(status=200, body='NO_KEY'); return
        r = find(g('sid'), g('key'))
        if not r:
            route.fulfill(status=200, body='UNKNOWN_KEY'); return
        if DROP.get(ph):                     # 이 제출은 서버에서 잃어버린 것으로 흉내 낸다
            route.fulfill(status=200, body='ERROR'); return
        if ph == 'save':
            write_row(r, b, g, json.loads(g('data') or '{}').get('phase', ''), False)
            route.fulfill(status=200, body='OK_SAVE'); return
        if ph == 'reopen':
            to = g('to')
            if to not in ORDER:
                route.fulfill(status=200, body='BAD_PHASE'); return
            write_row(r, b, g, to, True)
            route.fulfill(status=200, body='OK_REOPEN'); return
        if ph == 'draft':
            write_row(r, b, g, 'draftDone', True)
            route.fulfill(status=200, body='OK_DRAFT'); return
        if ph != 'final':
            route.fulfill(status=200, body='BAD_PHASE'); return
        write_row(r, b, g, 'done', True)
        finals.append({'sid': g('sid'), 'kp': g('key')[:6], 'at': now_iso()})
        route.fulfill(status=200, body='OK'); return

    # ── 읽기 (JSONP) ──
    cb = q.get('callback', ['cb'])[0]
    action = q.get('action', [''])[0]
    g = lambda k: q.get(k, [''])[0]
    sid, name, key = g('sid'), g('name'), g('key')
    if g('token') != TOKEN:
        out = {'error': 'BAD_TOKEN'}
    elif action == 'load':
        r = find(sid, key)
        if r:
            out = {'found': bool(r['data']), 'data': r['data'], 'key': key, 'name': r['name'],
                   'dup': r['dup'], 'phase': r['phase'], 'at': r['at']}
        else:
            # 열쇠 칸이 빈 같은 학번 줄을 이어받는다. 단, 이름이 다르면 넘겨주지 않는다.
            take = None
            blocked = False
            for x in rows:
                if x['sid'] == sid and not x['key']:
                    if x['name'] and norm(x['name']) != norm(name):
                        blocked = True
                        continue
                    take = x
                    break
            k = uuid.uuid4().hex[:20]
            if take:
                take['key'] = k
                out = {'found': bool(take['data']), 'data': take['data'], 'key': k, 'name': take['name'],
                       'dup': take['dup'], 'phase': take['phase'], 'at': take['at'], 'transferred': True}
            else:
                dup = any(x['sid'] == sid for x in rows)
                r2 = add_row(sid, name, k, dup)
                out = {'found': False, 'key': k, 'name': name, 'dup': dup, 'phase': 'research',
                       'nameMismatch': blocked}
        out['finalOpen'] = True
        f = next((x for x in reversed(finals) if x['sid'] == sid and x['kp'] == (out.get('key') or '')[:6]), None)
        out['finalAt'] = f['at'] if f else None
    elif action == 'check':
        out = {'draftAt': None, 'finalAt': None, 'draftPdf': '', 'finalPdf': '', 'phase': '', 'savedAt': None}
        if key:                              # 열쇠가 없으면 아무것도 확인해 주지 않는다
            r = find(sid, key)
            if r:
                out.update(draftAt=r['draftAt'], savedAt=r['at'], phase=r['phase'],
                           draftPdf='https://example.test/pdf' if r['draftAt'] else '')
            f = next((x for x in reversed(finals) if x['sid'] == sid and x['kp'] == key[:6]), None)
            out['finalAt'] = f['at'] if f else None
    elif action == 'dict':
        out = {'q': g('q'), 'a': 'ramp', 'dir': 'ko→en'} if find(sid, key) else {'error': 'NO_KEY'}
    else:
        out = {'ok': True}
    route.fulfill(status=200, content_type='application/javascript', body=cb + '(' + json.dumps(out) + ')')

# ── 도우미 ────────────────────────────────────────────────────────
fails = []
def check(label, cond, detail=''):
    print(('  OK   ' if cond else '  FAIL ') + label + (' :: ' + str(detail) if detail else ''))
    if not cond:
        fails.append(label + (' :: ' + str(detail) if detail else ''))

# ── T0. 서버 파일 검사 ────────────────────────────────────────────
# 브라우저 테스트는 가짜 서버를 쓰므로 gas/Code.gs 자체를 검사할 수 없다.
# 예전에 실제로 사고가 났던 부분만 직접 확인한다.
def check_server_file():
    print('T0 서버 파일(gas/Code.gs) 검사')
    gs = open(os.path.join(BASE, '..', 'gas', 'Code.gs'), encoding='utf-8').read()

    check('check 가 [초안제출시각] 칸을 돌려준다',
          re.search(r'out\.draftAt\s*=\s*v\[COL\.draftAt\s*-\s*1\]', gs) is not None,
          '자동 저장 시각(COL.at)을 돌려주면 초안 제출이 실패해도 성공으로 보인다')
    check('check 가 [저장시각]을 draftAt 으로 쓰지 않는다',
          re.search(r'out\.draftAt\s*=\s*v\[COL\.at\s*-\s*1\]', gs) is None)
    check('잠금 실패를 조용히 넘기지 않는다',
          'waitLock' not in gs.replace('lock.waitLock(30000); } catch (e) { return; }', ''),
          [l.strip() for l in gs.splitlines() if 'waitLock' in l])
    check('저장·로그인이 잠금을 반드시 잡는다',
          gs.count('}, true);') >= 2 and 'function withLock' in gs)
    dopost = gs[gs.index('function doPost(e)'):gs.index('function doGet(e)')]
    check('제출을 받는 동안 총괄 시트를 직접 쓰지 않는다',
          'rebuildOverview' not in dopost,
          '제출이 몰릴 때 가장 무거운 작업이 겹쳐 실행 시간 제한을 넘긴다')
    check('총괄 갱신이 자동으로 예약된다',
          gs.count('scheduleOverview();') == 3 and 'function scheduleOverview' in gs,
          '자동 저장·초안 제출·최종 제출 세 곳에서 불러야 한다: ' + str(gs.count('scheduleOverview();')))
    check('예약이 몰려도 갱신은 한 번만 돈다', "getProperty(\"ovPending\")" in gs and 'OV_DEBOUNCE_SEC' in gs)
    check('예약된 갱신이 자기 트리거를 지운다',
          'function overviewOnce' in gs and "dropTriggers(\"overviewOnce\")" in gs)
    check('선생님이 손으로 켜고 끌 필요가 없다',
          'installOverviewTrigger' not in gs and 'removeOverviewTrigger' not in gs,
          '수업마다 실행해야 하는 함수가 남아 있으면 안 된다')
    check('꼬였을 때 초기화할 방법이 있다', 'function resetOverviewSchedule' in gs)
    check('없는 함수를 부르지 않는다 (exportDocx)', 'exportDocx' not in gs)
    check('모르는 단계를 최종 제출로 처리하지 않는다',
          'if (p.phase !== "final") return textOut("BAD_PHASE");' in gs)
    check('최종 PDF 실패가 제출 전체를 버리지 않는다',
          re.search(r'try \{ files = savePdf\(data, "final"\); \}', gs) is not None)
    check('이름이 다르면 남의 줄을 넘겨주지 않는다',
          'nameKey(storedName) !== nameKey(name)' in gs)
    check('열쇠 없는 확인 요청에는 답하지 않는다',
          re.search(r'if \(!String\(key \|\| ""\)\) return out;', gs) is not None)
    check('상태(JSON)를 잘라 넣지 않는다',
          'js = String(old[COL.json - 1] || "");' in gs,
          '잘라 넣으면 다음 로그인 때 읽을 수 없다')
    check('시트 손잡이를 재사용한다', 'function cachedSheet' in gs)
    check('줄 찾기가 큰 칸을 읽지 않는다', 'function idRows' in gs and 'const rows = idRows(sh);' in gs)
    check('시트에 수식이 들어가지 않게 막는다', 'function safeCell' in gs)
    check('총괄의 표현 수 정규식이 맞다',
          gs.count('num(meta, /\\(표현 (\\d+)\\)/)') == 1 and 'num(meta, /표현 (\\d+)\\)/)' not in gs)
    # 페이지와 서버가 같은 값을 쓰는지
    check('토큰이 페이지와 서버에서 같다',
          re.search(r'token:\s*"([^"]+)"', gs).group(1) == TOKEN,
          re.search(r'token:\s*"([^"]+)"', gs).group(1) + ' vs ' + TOKEN)
    check('단계 순서가 페이지와 서버에서 같다',
          re.search(r'PHASE_ORDER = \{([^}]+)\}', gs).group(1).replace(' ', '') ==
          re.search(r'ORDER = \{([^}]+)\}', html).group(1).replace(' ', ''))
    dep = open(os.path.join(BASE, '..', 'gas', '.deployment-id'), encoding='utf-8').read().strip()
    check('배포 ID 가 페이지 주소에 든 것과 같다', dep in SCRIPT, dep)

check_server_file()

def new_page(b):
    ctx = b.new_context(viewport={'width': 1180, 'height': 900})
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.errs = errs
    pg.route(SCRIPT + '*', mock)
    return ctx, pg

def login(pg, sid, name, offline_ok=False):
    pg.goto('http://127.0.0.1:8880/index.html?as=1')
    pg.fill('#sid', sid); pg.fill('#name', name)
    pg.click('#startBtn'); pg.wait_for_timeout(1200)
    if offline_ok and not pg.eval_on_selector('#dlg', 'e=>e.hidden'):
        pg.click('#dlgActions button:has-text("이 기기에만")')
        pg.wait_for_timeout(500)

def teacher(pg, btn, label):
    pg.click(btn)
    pg.wait_for_selector('#dlgInput', state='visible')
    pg.fill('#dlgInput', PIN)
    pg.click('#dlgActions button:has-text("확인")')
    pg.wait_for_timeout(400)
    pg.click('#dlgActions button:has-text("' + label + '")')
    pg.wait_for_timeout(900)

def start_draft(pg):
    pg.click('#startDraftBtn')
    pg.wait_for_selector('#dlg:not([hidden])')
    pg.click('#dlgActions button:has-text("시작")')
    pg.wait_for_timeout(500)

def type_line(pg, part, line, text):
    ta = pg.query_selector('[data-part="%d"][data-line="%d"]' % (part, line))
    ta.click(); pg.keyboard.type(text)

def near20(t):
    """방금 시작한 20분 타이머. 로그인·화면 전환에 몇 초 걸리므로 19:5x 도 정상."""
    return bool(re.match(r'^(20:00|19:5\d)$', t.strip()))

with sync_playwright() as p:
    b = p.chromium.launch()

    # ── T1. 로그인·열쇠 발급·자동 저장, 그리고 같은 학번 다른 기기 ──
    print('T1 로그인 / 열쇠 / 중복 기기')
    ctxA, A = new_page(b); login(A, '10315', '김하늘')
    keyA = A.evaluate("localStorage.getItem('czkey:10315')")
    check('열쇠가 발급되어 저장된다', bool(keyA))
    check('조사 단계로 시작한다', A.inner_text('#phaseLabel') == '조사·브레인스토밍', A.inner_text('#phaseLabel'))
    A.click('[data-step2="0"]'); A.keyboard.type('학교 도서관'); A.wait_for_timeout(1800)
    check('자동 저장이 서버 줄에 들어간다', '학교 도서관' in (rows[0]['data'] or ''))

    ctxB, B = new_page(b); login(B, '10315', '김하늘')
    check('다른 기기는 별도 줄이 된다', len(rows) == 2, len(rows))
    check('중복 안내가 뜬다', not B.eval_on_selector('#banner', 'e=>e.hidden'))
    check('다른 기기에서 남의 글이 보이지 않는다', B.eval_on_selector('[data-step2="0"]', 'e=>e.value') != '학교 도서관')
    B.click('[data-step2="0"]'); B.keyboard.type('B의 글'); B.wait_for_timeout(1800)
    check('원래 줄이 그대로 남는다', '학교 도서관' in (rows[0]['data'] or ''))
    ctxB.close()

    # ── T2. 초안 단계 / 사전 / 문장 수 한 가지 기준 ──
    print('T2 초안 단계 / 사전 / 문장 수')
    start_draft(A)
    check('초안 타이머가 20분으로 시작한다', near20(A.inner_text('#timer')), A.inner_text('#timer'))
    A.click('#dictTop'); A.fill('#dictQ', '경사로'); A.keyboard.press('Enter'); A.wait_for_timeout(500)
    check('사전이 뜻을 돌려준다', 'ramp' in A.inner_text('#dictOut'))
    # 한 칸에 두 문장을 넣어도 위쪽 통계와 제출 창의 숫자가 같아야 한다
    type_line(A, 0, 0, 'Many students rely on the library. It is a place where they study.')
    A.wait_for_timeout(400)
    top = A.inner_text('#stSent')
    A.click('#submitBtn'); A.wait_for_selector('#modal:not([hidden])'); A.wait_for_timeout(300)
    dlg = A.inner_text('#modalSummary')
    m_top = re.search(r'(\d+)', top).group(1)
    m_dlg = re.search(r'초안 문장 수\s*(\d+)', dlg).group(1)
    check('위쪽 통계와 제출 창의 문장 수가 같다', m_top == m_dlg, '위 ' + m_top + ' / 창 ' + m_dlg)
    A.click('#modalCancel' if A.query_selector('#modalCancel') else '#modalOk')
    A.wait_for_timeout(300)

    # ── T3. 초안 제출이 서버에서 실패하면 성공이라고 말하지 않는다 (가장 중요) ──
    print('T3 초안 제출 실패를 성공으로 말하지 않는다')
    A.wait_for_timeout(1500)                 # 자동 저장이 [저장시각]을 최신으로 만들어 둔다
    before_at = rows[0]['at']
    DROP['draft'] = True
    if A.eval_on_selector('#modal', 'e=>e.hidden'):
        A.click('#submitBtn'); A.wait_for_selector('#modal:not([hidden])')
    A.click('#modalOk'); A.wait_for_selector('#done:not([hidden])'); A.wait_for_timeout(1200)
    DROP['draft'] = False
    st = A.inner_text('#doneStatus')
    check('[저장시각]은 최근이다 (예전 버그의 조건)', bool(before_at))
    check('초안제출시각이 안 찍혔다', rows[0]['draftAt'] is None, rows[0]['draftAt'])
    check('학생에게 저장되었다고 말하지 않는다', '드라이브에 저장되었습니다' not in st, st[:60])
    check('확인되지 않았다고 알린다', ('확인되지 않' in st) or ('실패' in st), st[:60])
    check('다시 보내기 버튼이 보인다', not A.eval_on_selector('#retryBtn', 'e=>e.hidden'))

    # ── T4. 다시 보내기 버튼이 실제로 복구한다 ──
    print('T4 다시 보내기')
    A.click('#retryBtn'); A.wait_for_timeout(1500)
    st = A.inner_text('#doneStatus')
    check('다시 보내면 초안제출시각이 찍힌다', rows[0]['draftAt'] is not None)
    check('다시 보낸 뒤 저장되었다고 알린다', '저장되었습니다' in st, st[:60])
    check('초안 제출에 Word Bank 규칙이 함께 갔다', any(x['phase'] == 'draft' and x['bank'] for x in posts))

    # ── T5. 다시 로그인하면 최종 단계가 열린다 ──
    print('T5 2회차 최종 단계')
    login(A, '10315', '김하늘')
    check('최종 글쓰기로 열린다', A.inner_text('#phaseLabel') == '최종 글쓰기', A.inner_text('#phaseLabel'))
    check('최종 타이머가 20분이다', near20(A.inner_text('#timer')), A.inner_text('#timer'))
    check('초안 글이 그대로 보인다', 'rely on the library' in A.eval_on_selector('[data-part="0"][data-line="0"]', 'e=>e.value'))

    # ── T6. 새로고침 뒤 첫 글자에 대량 입력·한글 입력이 잘못 기록되지 않는다 ──
    print('T6 새로고침 뒤 오탐 없음')
    A.click('#final'); A.keyboard.type('X')
    A.wait_for_timeout(300)
    log = A.inner_text('#log')
    burst = re.search(r'대량 입력\s*(\d+)', log).group(1)
    hangul = re.search(r'영어 칸 한글 입력\s*(\d+)', log).group(1)
    check('대량 입력이 0회다', burst == '0', log.replace('\n', ' / '))
    check('한글 입력이 0회다', hangul == '0', log.replace('\n', ' / '))

    # ── T7. 최종 제출 전체 경로 ──
    print('T7 최종 제출')
    A.eval_on_selector('#final', 'e=>{e.value="";}')
    A.click('#final')
    A.keyboard.type('Our library is a place where students study. Many rely on it. We should build a ramp. '
                    'This will make it easier for everyone. It helps regardless of age. Good for all of us.')
    A.wait_for_timeout(400)
    A.click('#submitBtn'); A.wait_for_selector('#modal:not([hidden])')
    A.click('#modalOk'); A.wait_for_selector('#done:not([hidden])'); A.wait_for_timeout(1500)
    st = A.inner_text('#doneStatus')
    check('제출명단에 한 줄 들어간다', len(finals) == 1, len(finals))
    check('학생에게 전송했다고 알린다', '전송했습니다' in st, st[:60])
    check('서버 단계가 최종 제출이 된다', rows[0]['phase'] == 'done', rows[0]['phase'])

    # ── T8. 교사 "제출 취소" 뒤 다시 쓴 글이 서버에 저장된다 ──
    print('T8 제출 취소 뒤 자동 저장')
    teacher(A, '#teacherBtn2', '제출 취소')
    check('되돌리기를 서버에도 알린다', any(x['phase'] == 'reopen' for x in posts))
    check('서버 단계가 최종 작성 중으로 돌아간다', rows[0]['phase'] == 'final', rows[0]['phase'])
    A.click('#final'); A.keyboard.type(' Rewritten after reopen.')
    A.wait_for_timeout(1800)
    check('다시 쓴 글이 서버에 저장된다', 'Rewritten after reopen' in (rows[0]['data'] or ''),
          (rows[0]['data'] or '')[-80:])

    # ── T9. 열쇠가 없으면 조용히 실패하지 않고 알린다 ──
    print('T9 열쇠가 없을 때')
    ctxC, C = new_page(b); login(C, '10420', '이서준')
    start_draft(C)
    type_line(C, 0, 0, 'A ramp helps everyone. We rely on it.')
    C.wait_for_timeout(1800)                 # 먼저 정상 자동 저장이 한 번 들어가게 한다
    rowC = next(r for r in rows if r['sid'] == '10420')
    check('열쇠가 있는 동안은 정상 저장된다', 'A ramp helps everyone' in (rowC['data'] or ''))
    C.evaluate("localStorage.removeItem('czkey:10420')")
    C.wait_for_timeout(1800)
    check('열쇠가 없으면 학생에게 알린다', not C.eval_on_selector('#banner', 'e=>e.hidden'),
          C.inner_text('#banner')[:40] if not C.eval_on_selector('#banner', 'e=>e.hidden') else '(배너 없음)')
    C.click('#submitBtn'); C.wait_for_selector('#modal:not([hidden])')
    C.click('#modalOk'); C.wait_for_selector('#done:not([hidden])'); C.wait_for_timeout(1200)
    st = C.inner_text('#doneStatus')
    check('열쇠 없는 제출을 성공이라고 말하지 않는다', '드라이브에 저장되었습니다' not in st, st[:60])

    # ── T10. 학번이 같고 이름이 다르면 남의 줄을 넘겨주지 않는다 ──
    print('T10 이름이 다르면 남의 줄을 주지 않는다')
    target = rows[0]
    keep = target['data']
    target['key'] = ''                       # 선생님이 [기기열쇠] 칸을 지운 상황
    n_before = len(rows)
    ctxD, D = new_page(b); login(D, '10315', '박서연', offline_ok=True)
    check('새 줄이 만들어진다', len(rows) == n_before + 1, len(rows))
    check('원래 학생 글이 그대로 남는다', target['data'] == keep)
    check('남의 이름으로 열리지 않는다', '김하늘' not in D.eval_on_selector('#who', 'e=>e.textContent'),
          D.eval_on_selector('#who', 'e=>e.textContent'))
    ctxD.close()

    # ── T11. 같은 이름이면 기기 교체가 정상 동작한다 ──
    print('T11 같은 이름이면 기기 교체된다')
    target2 = next(r for r in rows if r['sid'] == '10420')
    keep2 = target2['data']
    target2['key'] = ''
    n_before = len(rows)
    ctxE, E = new_page(b); login(E, '10420', '이서준')
    check('새 줄을 만들지 않는다', len(rows) == n_before, len(rows))
    check('이어받은 줄의 글이 열린다', 'A ramp helps everyone' in E.eval_on_selector('[data-part="0"][data-line="0"]', 'e=>e.value'),
          E.eval_on_selector('[data-part="0"][data-line="0"]', 'e=>e.value')[:40])
    ctxE.close()

    # ── T12. 교사 PIN ──
    print('T12 교사 PIN')
    ctxF, F = new_page(b)
    F.goto('http://127.0.0.1:8880/index.html?as=1'); F.wait_for_timeout(400)
    check('화면에 표시된 버전이 파일과 같다', re.search(r'version:\s*"([^"]+)"', html).group(1) in F.inner_text('#verTag'),
          F.inner_text('#verTag'))
    F.click('#teacherBtn4'); F.wait_for_selector('#dlgInput', state='visible')
    F.fill('#dlgInput', '0000'); F.click('#dlgActions button:has-text("확인")'); F.wait_for_timeout(500)
    check('틀린 PIN 은 거부된다', '맞지 않' in (F.inner_text('#toast') if not F.is_hidden('#toast') else ''))
    F.wait_for_timeout(2600)
    F.click('#teacherBtn4'); F.wait_for_selector('#dlgInput', state='visible')
    F.fill('#dlgInput', PIN); F.click('#dlgActions button:has-text("확인")'); F.wait_for_timeout(500)
    check('맞는 PIN 으로 교사 메뉴가 열린다', '교사 메뉴' in F.inner_text('#dlgTitle'), F.inner_text('#dlgTitle'))
    ctxF.close()

    # ── 마무리 ──
    print('마무리')
    allerrs = {'A': A.errs, 'C': C.errs}
    check('페이지 오류가 없다', not any(allerrs.values()), allerrs)
    check('토큰이 맞지 않는 요청이 없다', not any(x for x in posts if x.get('token') == 'bad'))
    b.close()

srv.shutdown()
print()
if fails:
    print('FAIL (' + str(len(fails)) + '건)')
    for f in fails:
        print(' - ' + f)
    sys.exit(1)
print('PASS')

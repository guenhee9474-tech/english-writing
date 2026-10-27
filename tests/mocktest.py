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

# 윈도우 기본 콘솔(cp949)에서 이모지·특수문자 때문에 출력이 죽지 않게 한다
try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception: pass

from playwright.sync_api import sync_playwright

html = open(os.path.join(DOCS, 'index.html'), encoding='utf-8').read()
SCRIPT = re.search(r'scriptUrl:\s*"([^"]+)"', html).group(1)
TOKEN = re.search(r'token:\s*"([^"]+)"', html).group(1)
import hashlib
PIN = '424242'                       # 시험용 PIN (실제 PIN 은 소스에 없고 지문만 있음)
PIN_HASH = hashlib.pbkdf2_hmac('sha256', PIN.encode(), b'czpin-2026', 150000).hex()
REAL_HASH = re.search(r'teacherPinHash:\s*"([0-9a-f]{64})"', html).group(1)
TEST_HTML = html.replace(REAL_HASH, PIN_HASH)
assert PIN_HASH in TEST_HTML
assert SCRIPT, 'docs/index.html 의 CONFIG.submit.scriptUrl 이 비어 있습니다'
ORDER = {'research': 0, 'draft': 1, 'draftDone': 2, 'final': 3, 'done': 4}

# ── 가짜 서버 상태 ────────────────────────────────────────────────
rows = []        # 초안 시트 한 줄씩: sid,name,key,data,phase,at,draftAt,dup,brain,draft
finals = []      # 제출명단 한 줄씩: {sid,keyPrefix,at}
posts = []       # 받은 POST 기록
pdfs = []        # PDF 요청 (학번, 종류)
DROP = {'draft': False, 'save': False, 'net': False}   # 테스트에서 특정 제출을 잃어버리게 만드는 스위치 (net: 와이파이 끊김)
TAKEN = set()    # "기존 기록 잇기" 뒤 아직 다시 로그인하지 않은 열쇠
TKEY = 'teacher-key-for-test'
ROSTER = {}      # "명단" 탭 흉내. 비어 있으면 누구나 등록
BUSY = {'n': 0}  # 남은 "동시 실행 너무 많음" 응답 수
CMDS = {}        # 현황판 조작: 학번 -> [조작]
FINAL = {'default': True}   # 2회차 기본 열림 (예전 시험들용). T22 에서 실제처럼 닫힘으로 바꿈
OPEN = {}        # 'c:1학년 3반' / 's:10315' -> 열림 끝 시각(ms)
def cls_of(sid): return sid[0] + '학년 ' + str(int(sid[1:3])) + '반'
def final_open_for(sid):
    now = time.time() * 1000
    return FINAL['default'] or OPEN.get('s:' + sid, 0) > now or OPEN.get('c:' + cls_of(sid), 0) > now

CORS = {'Access-Control-Allow-Origin': '*'}
# 읽기를 어떤 방식으로 했는지 센다. 새 방식(쿠키 없는 fetch)이 실제로 쓰여야 한다.
uses = {'fetch': 0, 'jsonp': 0}

def now_iso():
    # 실제 서버는 Date 를 JSON 으로 내보내므로 UTC ISO(Z) 가 된다
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')

def find(sid, key):
    return next((r for r in rows if r['sid'] == sid and r['key'] == key and key), None)

def add_row(sid, name, key, dup):
    r = {'sid': sid, 'name': name, 'key': key, 'data': None, 'phase': 'research',
         'at': None, 'draftAt': None, 'finalAt': None, 'dup': dup, 'brain': '', 'draft': ''}
    rows.append(r)
    return r

def norm(s):
    return re.sub(r'\s+', '', s or '').lower()

def ahead_of(r):
    """gas/Code.gs 의 staleRows 와 같은 규칙: r 이 조사·초안 작성 중이고 같은 학번·이름의 다른 줄이 초안 이상이면 그 줄."""
    if r['dup'] == '이어받음' or ORDER.get(r['phase'], 0) >= ORDER['draftDone']:
        return None
    c = [x for x in rows[rows.index(r) + 1:] if x['sid'] == r['sid'] and x['dup'] != '이어받음' and norm(x['name']) == norm(r['name'])]
    best = max(c, key=lambda x: ORDER.get(x['phase'], 0), default=None)
    return best if best and ORDER.get(best['phase'], 0) >= ORDER['draftDone'] else None

def write_row(r, b, g, phase, allow_regress):
    """gas/Code.gs 의 saveDraft 와 같은 규칙."""
    ph = phase
    if not allow_regress and ORDER.get(r['phase'], 0) > ORDER.get(ph, 0):
        return 'STALE'                       # 서버가 더 앞선 단계면 아무것도 쓰지 않는다
    r['phase'] = ph
    r['data'] = g('data')
    r['brain'] = g('brainstorm')
    r['draft'] = g('draft')
    r['at'] = now_iso()                      # [저장시각] 은 저장마다 갱신
    if phase == 'draftDone':
        r['draftAt'] = now_iso()             # [초안제출시각] 은 초안 제출 때만
    if phase == 'done':
        r['finalAt'] = now_iso()             # [최종제출시각] 은 최종 제출(글 저장 성공) 때만
    return 'OK'

def mock(route):
    req = route.request
    if DROP['net']:                          # 와이파이가 끊긴 상황: 어떤 요청도 닿지 않는다
        route.abort(); return
    if BUSY['n'] > 0:                        # 구글 "동시 실행이 너무 많음" 화면 (스크립트가 돌기 전에 돌려보냄)
        BUSY['n'] -= 1
        route.fulfill(status=200, content_type='text/html', headers=CORS,
                      body='<!DOCTYPE html><html><body>이 Google 사용자 계정에 대해 너무 많은 스크립트가 동시에 실행되고 있습니다.</body></html>'); return
    u = urllib.parse.urlparse(req.url)
    q = urllib.parse.parse_qs(u.query)

    if req.method == 'POST':
        b = urllib.parse.parse_qs(req.post_data or '')
        g = lambda k: b.get(k, [''])[0]
        ph = g('phase')
        posts.append({'phase': ph, 'sid': g('sid'), 'key': g('key'), 'bank': 'bank' in b, 'to': g('to'), 'meta': g('meta')})
        if g('token') != TOKEN:
            route.fulfill(status=200, headers=CORS, body='BAD_TOKEN'); return
        if not g('key'):
            route.fulfill(status=200, headers=CORS, body='NO_KEY'); return
        r = find(g('sid'), g('key'))
        if not r:
            route.fulfill(status=200, headers=CORS, body='UNKNOWN_KEY'); return
        if DROP.get(ph):                     # 이 제출은 서버에서 잃어버린 것으로 흉내 낸다
            route.fulfill(status=200, headers=CORS, body='ERROR'); return
        dphase = json.loads(g('data') or '{}').get('phase', '') if g('data') else ''
        if (ph == 'final' or (ph == 'save' and dphase == 'final')) and not final_open_for(g('sid')) and r['phase'] in ('research', 'draft', 'draftDone'):
            route.fulfill(status=200, headers=CORS, body='CLOSED'); return
        if ph == 'save':
            if g('key') in TAKEN:
                route.fulfill(status=200, headers=CORS, body='TAKEN'); return
            res = write_row(r, b, g, json.loads(g('data') or '{}').get('phase', ''), False)
            route.fulfill(status=200, headers=CORS, body='STALE' if res == 'STALE' else 'OK_SAVE'); return
        if ph == 'pdf':
            kind = g('kind')
            if kind == 'final' and r['phase'] != 'done':
                route.fulfill(status=200, headers=CORS, body='BAD_PHASE'); return
            r['finalPdf' if kind == 'final' else 'pdf'] = 'https://example.test/' + kind + '.pdf'
            pdfs.append((g('sid'), kind))
            route.fulfill(status=200, headers=CORS, body='OK_PDF\n' + json.dumps(check_out(r))); return
        if ph == 'reopen':
            to = g('to')
            if to not in ORDER:
                route.fulfill(status=200, headers=CORS, body='BAD_PHASE'); return
            write_row(r, b, g, to, True)
            route.fulfill(status=200, headers=CORS, body='OK_REOPEN'); return
        if ph == 'draft':
            if ORDER.get(r['phase'], 0) >= ORDER['final']:   # 이미 2회차면 늦게 온 초안 제출은 무시
                route.fulfill(status=200, headers=CORS, body='OK_DRAFT'); return
            write_row(r, b, g, 'draftDone', True)
            route.fulfill(status=200, headers=CORS, body='OK_DRAFT\n' + json.dumps(check_out(r))); return
        if ph != 'final':
            route.fulfill(status=200, headers=CORS, body='BAD_PHASE'); return
        write_row(r, b, g, 'done', True)
        finals.append({'sid': g('sid'), 'kp': g('key')[:6], 'at': now_iso()})
        route.fulfill(status=200, headers=CORS, body='OK\n' + json.dumps(check_out(r))); return

    # ── 읽기 (JSONP) ──
    cb = q.get('callback', ['cb'])[0]
    action = q.get('action', [''])[0]
    g = lambda k: q.get(k, [''])[0]
    sid, name, key = g('sid'), g('name'), g('key')
    if action == 'monitor':
        out = monitor(g('k'))
    elif action == 'takeover':
        out = takeover(g('k'), sid, g('kp'))
    elif action == 'tcmd':                   # gas/Code.gs 의 teacherCommand 와 같은 규칙
        if g('k') != TKEY:
            out = {'error': 'BAD_KEY'}
        else:
            if g('cmd') in ('openfinal', 'closefinal'):
                tk = ('c:' + g('cls')) if g('cls') else ('s:' + sid)
                if g('cmd') == 'openfinal': OPEN[tk] = time.time() * 1000 + 3 * 3600 * 1000
                else: OPEN.pop(tk, None)
            targets = [x['sid'] for x in monitor(TKEY)['students'] if x['c'] == g('cls') and x['ph'] and x['ph'] != 'done'] if g('cls') else [sid]
            if g('cmd') == 'closefinal': targets = []
            item = {'id': uuid.uuid4().hex[:8], 'cmd': g('cmd'), 'arg': g('arg'), 't': int(time.time() * 1000)}
            for t in dict.fromkeys(targets):
                CMDS.setdefault(t, []).append(item)
            out = {'ok': True, 'n': len(dict.fromkeys(targets))} if targets or g('cmd') in ('openfinal', 'closefinal') else {'error': 'NO_TARGET'}
    elif g('token') != TOKEN:
        out = {'error': 'BAD_TOKEN'}
    elif action == 'load':
        r = find(sid, key)
        if r and r['name'] and norm(r['name']) != norm(name) and g('nameOk') != '1':
            out = {'found': False, 'error': 'NAME_MISMATCH', 'hint': r['name'][0] + '*' * max(1, len(r['name']) - 1)}
        elif r and ahead_of(r):
            a = ahead_of(r)                  # 멈춘 줄의 기기로 들어옴: 앞선 줄로 이어 줌
            r['key'] = '이어받음'; r['dup'] = '이어받음'
            out = {'found': bool(a['data']), 'data': a['data'], 'key': a['key'], 'name': a['name'],
                   'dup': False, 'phase': a['phase'], 'at': a['at'], 'transferred': True}
        elif r:
            out = {'found': bool(r['data']), 'data': r['data'], 'key': key, 'name': r['name'],
                   'dup': r['dup'], 'phase': r['phase'], 'at': r['at'], 'taken': key in TAKEN}
            TAKEN.discard(key)
        elif ROSTER and g('rosterOk') != '1' and (sid not in ROSTER or norm(ROSTER[sid]) != norm(name)):
            out = {'found': False, 'error': 'ROSTER_CHECK', 'why': '명단에 없는 학번' if sid not in ROSTER else '명단의 이름과 다름'}
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
                prior = any(x['sid'] == sid and norm(x['name']) == norm(name) and x['dup'] != '이어받음' and ORDER.get(x['phase'], 0) >= ORDER['draftDone'] for x in rows)
                r2 = add_row(sid, name, k, dup)
                if ROSTER and (sid not in ROSTER or norm(ROSTER[sid]) != norm(name)):
                    r2['rm'] = '명단에 없는 학번' if sid not in ROSTER else '명단의 이름과 다름'
                out = {'found': False, 'key': k, 'name': name, 'dup': dup, 'phase': 'research',
                       'nameMismatch': blocked, 'priorSubmitted': prior}
        out['finalOpen'] = final_open_for(sid)
        rr = find(sid, out.get('key') or '')
        out['finalAt'] = rr['finalAt'] if rr and rr['phase'] == 'done' else None
    elif action == 'cmd':
        out = {'cmds': CMDS.get(sid, [])}
    elif action == 'check':
        out = {'draftAt': None, 'finalAt': None, 'draftPdf': '', 'finalPdf': '', 'phase': '', 'savedAt': None}
        if key:                              # 열쇠가 없으면 아무것도 확인해 주지 않는다
            r = find(sid, key)
            if r:
                out.update(draftAt=r['draftAt'], savedAt=r['at'], phase=r['phase'],
                           draftPdf='https://example.test/pdf' if r['draftAt'] else '',
                           finalAt=r['finalAt'] if r['phase'] == 'done' else None)
    elif action == 'dict':
        # 실제 서버처럼 확인 여부(sure)와 쓴 기본형(base)을 함께 돌려준다
        if not find(sid, key):
            out = {'error': 'NO_KEY'}
        elif g('q') == '배고픈':          # 국립국어원 사전에서 기본형으로 찾은 경우
            out = {'q': g('q'), 'a': 'hungry', 'sure': True, 'base': '배고프다', 'back': '',
                   'src': '사전', 'pos': '형용사', 'def': '배 속이 비어서 음식이 먹고 싶다.', 'dir': 'ko→en'}
        elif g('q') == '수상한':          # 어떻게 해도 확인이 안 되는 경우
            out = {'q': g('q'), 'a': 'award-winning', 'sure': False, 'base': '', 'back': '상을 받은', 'dir': 'ko→en'}
        else:
            out = {'q': g('q'), 'a': 'ramp', 'sure': True, 'base': '', 'back': g('q'), 'dir': 'ko→en'}
    else:
        out = {'ok': True}
    # 실제 서버처럼, callback 이 없으면 그냥 JSON 으로 돌려준다 (쿠키 없는 fetch 가 쓰는 방식)
    uses['jsonp' if 'callback' in q else 'fetch'] += 1
    if 'callback' not in q:
        route.fulfill(status=200, content_type='application/json',
                      headers={'Access-Control-Allow-Origin': '*'}, body=json.dumps(out))
        return
    route.fulfill(status=200, content_type='application/javascript', body=cb + '(' + json.dumps(out) + ')')

def check_out(r):
    return {'draftAt': r['draftAt'], 'finalAt': r['finalAt'] if r['phase'] == 'done' else None, 'savedAt': r['at'],
            'phase': r['phase'], 'draftPdf': r.get('pdf', ''), 'finalPdf': r.get('finalPdf', '')}

def monitor(k):
    """gas/Code.gs 의 readMonitorRows 와 같은 규칙 (중복 줄에 같은 이름의 원래 줄이 있으면 kp/op)."""
    if k != TKEY:
        return {'error': 'BAD_KEY'}
    st = []
    for i, r in enumerate(rows):
        if r['dup'] == '이어받음' or ahead_of(r):
            continue
        od = sum(1 for y in rows if ahead_of(y) is r)
        x = {'c': r['sid'][0] + '학년 ' + str(int(r['sid'][1:3])) + '반', 'sid': r['sid'], 'nm': r['name'], 'ph': r['phase'],
             'lv': 0, 'hg': 0, 'bs': 0, 'dc': 0, 'sn': 0, 'at': 0, 'dr': 0, 'fn': 0, 'dup': r['dup'] is True and not od, 'od': od, 'rm': r.get('rm', '')}
        if r['dup'] is True and not od:
            c = [y for j, y in enumerate(rows) if j != i and y['sid'] == r['sid'] and y['dup'] != '이어받음'
                 and norm(y['name']) == norm(r['name'])]
            o = max(c, key=lambda y: ORDER.get(y['phase'], 0), default=None)
            if o and ORDER.get(r['phase'], 0) <= ORDER.get(o['phase'], 0):
                x['kp'] = r['key'][:6]; x['op'] = o['phase']
        st.append(x)
    now = time.time() * 1000
    return {'ok': True, 'at': int(now), 'classes': sorted({x['c'] for x in st}), 'students': st, 'fo': True, 'fmode': '',
            'openCls': {k[2:]: v for k, v in OPEN.items() if k.startswith('c:') and v > now},
            'openSid': {k[2:]: v for k, v in OPEN.items() if k.startswith('s:') and v > now}}

def takeover(k, sid, kp):
    """gas/Code.gs 의 takeover 와 같은 규칙."""
    if k != TKEY:
        return {'error': 'BAD_KEY'}
    d = next((r for r in rows if r['sid'] == sid and r['dup'] is True and r['key'].startswith(kp)), None)
    if not d:
        return {'error': 'NO_DUP'}
    cand = [r for r in rows if r is not d and r['sid'] == sid and r['dup'] != '이어받음' and norm(r['name']) == norm(d['name'])]
    if not cand:
        return {'error': 'NO_ORIGINAL'}
    o = max(cand, key=lambda r: ORDER.get(r['phase'], 0))
    if ORDER.get(d['phase'], 0) > ORDER.get(o['phase'], 0):
        return {'error': 'DUP_AHEAD'}
    nk = d['key']
    o['key'] = nk
    d['key'] = '이어받음'; d['dup'] = '이어받음'
    TAKEN.add(nk)
    return {'ok': True, 'phase': o['phase']}

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
    teacher_html = open(os.path.join(DOCS, 'teacher.html'), encoding='utf-8').read()

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
    mon = gs[gs.index('function monitorData'):gs.index('function overviewTick')]
    tick = gs[gs.index('function overviewTick'):gs.index('function monitorAll')]
    check('총괄 갱신이 자동으로 돈다 (자동 저장 + 선생님 현황 화면의 따로 부르는 요청)',
          dopost.count('maybeRebuildOverview(OV_SAVE_SEC)') == 1 and 'maybeRebuildOverview(OV_MONITOR_SEC)' in tick and 'teacherKey()' in tick,
          '제출 요청에서 갱신하면 그 학생이 십수 초를 기다린다(2026-10-21 부하 시험)')
    check('현황 화면 3초 읽기는 총괄 갱신·PDF 채우기를 하지 않는다', 'maybeRebuildOverview' not in mon and 'fillMissingPdfs' not in mon,
          '1분마다 그 요청이 10~30초 걸려 화면이 멈췄다')
    check('현황 화면이 1분마다 따로 부른다', 'action: "ovtick"' in teacher_html and 'setInterval(ovTick, 60000)' in teacher_html)
    check('최종 제출 요청은 제출명단을 쓰지 않는다(PDF 만들 때)', 'logRow(' not in dopost and 'logRow(d, [file])' in gs)
    check('다시 제출하면 PDF 칸을 비워 새로 만든다', 'phase === "done" ? (pdfLink || "")' in gs and 'phase === "draftDone" ? (pdfLink || "")' in gs)
    check('제출 요청은 총괄 갱신을 기다리지 않는다', dopost.count('maybeRebuildOverview(') == 1)
    check('갱신 간격이 넉넉하다',
          re.search(r'OV_SAVE_SEC = (\d+)', gs) and int(re.search(r'OV_SAVE_SEC = (\d+)', gs).group(1)) >= 120,
          '실시간은 teacher.html 이 맡고, 시트는 기록이라 자주 쓸 필요가 없다')
    check('현황 화면 기능이 있다', 'function monitorData' in gs and 'function newTeacherKey' in gs)
    check('현황 화면 열쇠를 코드에 적지 않는다',
          not re.search(r'teacherKey["\']?\s*[:=]\s*["\'][0-9a-f]{16,}', gs),
          '이 파일은 공개 저장소에 올라간다')
    check('진단 함수가 있다', 'function diagnose' in gs)
    # 사전: 단어 하나를 그대로 번역하면 자주 틀린다. 기본형 시도 + 되돌림 확인이 있어야 한다.
    check('사전이 기본형으로도 찾아 본다', 'function koBaseForm' in gs and 'koBaseForm(q)' in gs)
    check('사전이 되돌려 확인한다', 'function sameWord' in gs and 'trCached(a, to, from)' in gs,
          '번역 결과를 다시 한국어로 되돌려 원래 단어와 맞는지 본다')
    check('사전 번역 결과를 보관해 호출을 줄인다', 'function trCached' in gs)
    check('확인 여부를 학생에게 돌려준다', 'sure: !!r.sure' in gs)
    check('사전 신뢰도를 직접 확인할 함수가 있다', 'function testDict' in gs)
    # 진짜 사전(국립국어원 krdict) 을 먼저 보고, 안 되면 번역으로 넘어가야 한다
    check('국립국어원 사전을 먼저 본다', 'function krdictLookup' in gs and 'krdictLookup(tries[i])' in gs)
    check('사전 인증키를 코드에 적지 않는다',
          'settingsSheet().getRange("B2")' in gs and 'getProperty("krdictKey")' in gs,
          '이 파일은 공개 저장소에 올라간다. 키는 시트나 스크립트 속성에서만 읽어야 한다')
    check('선생님이 실행할 함수가 하나뿐이다', 'function 사전켜기' in gs,
          '편집기에서 코드를 고치게 하지 않는다')
    check('인증키를 스프레드시트에서 읽는다',
          'function settingsSheet' in gs and 'settingsSheet().getRange("B2")' in gs,
          '선생님만 보는 파일에 두어야 공개 저장소에 노출되지 않는다')
    # 실측으로 확인된 두 가지 (2026-09-10): num 은 10 이상, User-Agent 없으면 차단됨
    numv = re.search(r'trans_lang=1&num=(\d+)', gs)
    check('사전 요청의 num 이 10 이상이다', numv is not None and int(numv.group(1)) >= 10,
          '3 을 넣으면 Invalid num value(103) 로 거절당한다: ' + (numv.group(1) if numv else '없음'))
    check('사전 요청에 User-Agent 를 보낸다', '"User-Agent"' in gs,
          '안 보내면 Request Blocked(400) 이 온다')
    check('사전이 거절하면 오류 탭에 남긴다', '사전(krdict) 거절' in gs,
          '키 오류·값 오류·하루 한도 초과가 조용히 넘어가면 안 된다')
    # 실패를 오래 기억하면 코드를 고쳐도 옛 결과가 계속 나온다 (2026-09-10 실제로 겪음)
    keep = re.search(r'out \? 21600 : (\d+)', gs)
    check('"못 찾음"은 오래 기억하지 않는다', keep is not None and int(keep.group(1)) <= 1800,
          '찾은 뜻은 6시간, 못 찾음은 30분 이내여야 한다: ' + (keep.group(1) if keep else '없음'))
    check('보관해 둔 사전 결과를 한 번에 비울 수 있다',
          'function kdVer' in gs and '"kd" + kdVer()' in gs and 'setProperty("kdVer"' in gs,
          '사전켜기 가 판 번호를 올려 옛 기억을 버린다')
    check('사전이 실패해도 번역으로 넘어간다',
          'return dictByTranslate(q);' in gs and 'logError("사전(krdict) 호출"' in gs,
          '권한 미승인·키 없음·응답 실패 모두 지금 방식으로 되돌아가야 한다')
    check('현황 화면 자료를 잠깐 보관해 재사용한다',
          'CacheService.getScriptCache()' in gs and 'mon_all' in gs and 'MON_CACHE_SEC' in gs,
          '3초마다 물어보므로 매번 시트를 열면 느리고 사용량이 많이 든다')
    check('보관 시간이 화면 갱신 주기와 맞는다',
          int(re.search(r'MON_CACHE_SEC = (\d+)', gs).group(1)) <= int(re.search(r'REFRESH_SEC = (\d+)', teacher_html).group(1)),
          '보관 시간이 갱신 주기보다 길면 화면이 그만큼 늦어진다')
    check('이탈을 바로 보내는 간격이 갱신 주기보다 짧다',
          int(re.search(r'lastFlush < (\d+)', html).group(1)) / 1000 <= int(re.search(r'REFRESH_SEC = (\d+)', teacher_html).group(1)) + 2,
          '학생 쪽에서 늦게 보내면 화면을 빨리 새로 읽어도 소용없다')
    # 주석을 걷어낸 뒤 검사한다 (설명 문장에 적힌 ScriptApp 까지 잡히면 안 되므로)
    code = re.sub(r'/\*.*?\*/', '', gs, flags=re.S)
    code = '\n'.join(ln.split('//')[0] for ln in code.split('\n'))
    check('트리거(ScriptApp)를 쓰지 않는다', 'ScriptApp' not in code,
          '웹 앱에 script.scriptapp 권한이 없어 매번 실패한다(오류 탭). 주석 밖에서 쓰면 안 된다')
    check('요청이 몰려도 갱신은 한 번만 돈다', 'getProperty("ovAt")' in gs and 'OV_INTERVAL_SEC' in gs)
    check('갱신이 저장 잠금을 붙잡지 않는다',
          'function rebuildOverview' in gs and 'lock.waitLock(30000); } catch (e) { return; }' not in gs,
          '갱신하는 몇 초 동안 학생 저장이 줄을 서면 안 된다')
    check('선생님이 손으로 켜고 끌 필요가 없다',
          'installOverviewTrigger' not in gs and 'removeOverviewTrigger' not in gs,
          '수업마다 실행해야 하는 함수가 남아 있으면 안 된다')
    check('반별 탭은 글자를 키운다', 'const BIG = !withClass;' in gs and 'setRowHeights(4, body.length, 34)' in gs)
    check('이탈한 학생 이름이 맨 위에 나온다', 'leaveNames' in gs)
    check('꼬였을 때 초기화할 방법이 있다', 'function resetOverviewSchedule' in gs)
    check('총괄 갱신이 학생 글 전체를 읽지 않는다',
          'function overviewRows' in gs and 'const rows = overviewRows(draftSheet());' in gs,
          '갱신이 1~2분마다 도므로 큰 칸을 읽으면 느려진다')
    # overviewRows 가 만드는 16칸의 위치가 COL 과 맞는지 (틀리면 총괄에 엉뚱한 값이 찍힌다)
    ovcols = a_ = None
    m = re.search(r'out\.push\(a\[i\]\.concat\(\["", "", b\[i\]\[0\], ""\], c\[i\]\)\);', gs)
    check('총괄이 읽는 열 위치가 맞다', m is not None,
          '1-8 + 빈칸2 + 초안PDF + 빈칸 + 13-16 = 16칸이어야 한다')
    check('없는 함수를 부르지 않는다 (exportDocx)', 'exportDocx' not in gs)
    check('모르는 단계를 최종 제출로 처리하지 않는다',
          'if (p.phase !== "final") return textOut("BAD_PHASE");' in gs)
    check('제출 요청은 PDF 를 만들지 않는다 (PDF 는 따로, 실패해도 제출은 성공)',
          'savePdf(' not in dopost and 'function makePdfNow' in gs and 'if (p.phase === "pdf")' in dopost,
          '2026-10-21 부하 시험: 90명 동시 제출에서 PDF 때문에 37명이 첫 시도에 실패')
    check('빠진 PDF 를 채우는 길이 있다', 'function fillMissingPdfs' in gs and 'function PDF빠진것만들기' in gs)
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
    # 2026-10-21 점검에서 고친 것들 (되돌아가지 않게)
    check('최종 제출은 글을 저장한 뒤에 성공이라고 답한다',
          'saveDraft(data, p.data || "", "done"' in dopost and
          dopost.index('saveDraft(data, p.data || "", "done"') < dopost.rindex('return okWith("OK");'),
          '저장 실패를 삼키고 PDF 까지 실패하면 글이 어디에도 없는데 학생은 OK 를 받았다')
    check('최종 상태 저장 실패를 삼키지 않는다', 'logError("최종 상태 저장"' not in dopost)
    check('초안 제출도 글을 저장한 뒤에 성공이라고 답한다',
          dopost.index('saveDraft(data, p.data || "", "draftDone"') < dopost.rindex('return okWith("OK_DRAFT");'))
    check('같은 제출이 다시 오면 PDF 를 또 만들지 않는다', dopost.count('recentAt(st.') >= 2)
    check('늦은 자동 저장이 제출된 글을 덮지 않는다', 'return "STALE";' in gs)
    check('이미 2회차면 늦게 온 초안 제출을 무시한다',
          '(PHASE_ORDER[st.phase] || 0) >= PHASE_ORDER.final) return textOut("OK_DRAFT")' in dopost)
    lor = gs[gs.index('function loadOrRegister'):gs.index('const PHASE_ORDER')]
    check('로그인 때 시트 열기는 잠금 밖에서 한다',
          lor.index('const sh = draftSheet();') < lor.index('withLock('),
          '30명이 한꺼번에 로그인하면 잠금 대기가 30초를 넘겨 BUSY')
    check('열쇠가 맞아도 이름이 다르면 바로 열지 않는다', 'error: "NAME_MISMATCH"' in lor)
    check('최종 제출 확인은 그 줄의 [최종제출시각]으로 한다',
          'out.finalAt = out.phase === "done" ? (v[COL.finalAt - 1] || null) : null;' in gs)
    check('기존 기록 잇기가 교사 열쇠를 확인한다',
          'function takeover' in gs and gs[gs.index('function takeover'):].split('\n}')[0].count('teacherKey()') == 1)
    check('잇기 뒤 옛 화면의 저장을 받지 않는다', 'if (wasTaken(data.key)) return textOut("TAKEN");' in dopost)
    check('총괄 갱신 차례를 잠금 안에서 정한다', 'if (!lock.tryLock(2000)) return;' in gs)
    check('초안 탭 제목만 바뀐 경우 탭을 갈아치우지 않는다', '초안 탭 제목 줄이 바뀌어 되돌림' in gs)
    check('만들다 만 구글 문서를 휴지통으로 보낸다', 'function buildPdf' in gs)
    check('명단과 다르면 막지 않고 확인받은 뒤 표시한다',
          'error: "ROSTER_CHECK"' in lor and 'rosterOk' in lor and 'noteRoster(' in lor and 'NOT_IN_ROSTER' not in gs)
    check('명단은 교사 열쇠로만 올릴 수 있다', 'function putRoster' in gs and 'teacherKey()' in gs[gs.index('function putRoster'):gs.index('function rosterMap')])
    check('로그인은 대부분 잠금 없이 처리한다 (90명 동시 로그인 대비)',
          lor.index('const r = findRow(sh, sid, key);') < lor.index('withLock(') and 'if (!canTransfer)' in lor)
    sd = gs[gs.index('function saveDraft'):gs.index('function rowState')]
    check('저장은 줄 찾기를 잠금 밖에서 하고, 잠금 안에서 열쇠를 다시 확인한다',
          sd.index('findRow(sh, d.sid, d.key)') < sd.index('withLock(') and 'String(old[COL.key - 1]) !== String(d.key)' in sd)
    check('제출 답에 확인 정보를 함께 보낸다', 'JSON.stringify(checkStatus(data.sid, data.key))' in dopost and dopost.count('okWith(') >= 4)
    check('제출명단 파일을 매번 드라이브에 묻지 않는다', 'props.getProperty("logSheetOk") === saved' in gs)
    check('교사 PIN 이 소스에 그대로 있지 않다', not re.search(r'teacherPin:\s*"\d', html) and 'teacherPinHash' in html)
    dep = open(os.path.join(BASE, '..', 'gas', '.deployment-id'), encoding='utf-8').read().strip()
    check('배포 ID 가 페이지 주소에 든 것과 같다', dep in SCRIPT, dep)

check_server_file()

# ── T0b. 선생님 현황 화면 검사 ─────────────────────────────────
# 색을 칠하는 열 위치가 한 칸 어긋나면 총괄에 엉뚱한 색이 찍힌다. 위치를 직접 맞춰 본다.
def check_status_sheet():
    print('T0b 선생님 현황 화면(총괄·반별 탭) 검사')
    gs = open(os.path.join(BASE, '..', 'gas', 'Code.gs'), encoding='utf-8').read()
    check('현황 화면을 그리는 함수가 있다', 'function writeStatusSheet' in gs)
    check('반별 탭을 만든다', 'writeStatusSheet(ss, cls, cls,' in gs,
          '수업 들어가서 그 반 탭만 보면 되도록')
    check('전체 탭도 만든다', 'writeStatusSheet(ss, ov.name || "총괄", "전체"' in gs)
    check('이탈이 늘면 색이 진해진다', 'function leaveColor' in gs and 'C_W1' in gs and 'C_W3' in gs)
    check('기기가 조용하면 표시된다', 'quietMin >= 3' in gs,
          '쓰고 있어야 하는데 3분 넘게 저장이 없으면 연결이 끊어진 것')
    check('색을 한 번에 칠한다 (갱신 속도)', gs.count('rng.setBackgrounds(bg);') == 1,
          '칸마다 칠하면 1~2분마다 도는 갱신이 느려진다')

    seg = gs[gs.index('function writeStatusSheet'):gs.index('function rebuildOverview')]
    def arr(after):
        i = seg.index(after); j = seg.index('[', i); d = 0
        for k in range(j, len(seg)):
            if seg[k] == '[': d += 1
            elif seg[k] == ']':
                d -= 1
                if d == 0: return seg[j + 1:k]
        return ''
    head = ['반'] + [x.strip().strip('"') for x in arr('["학번", "이름"').split(',')]
    body = ['r.cls'] + [x.strip() for x in arr('[r.sid, r.name').split(',')]
    check('열 이름 수와 본문 값 수가 같다', len(head) == len(body), str(len(head)) + ' vs ' + str(len(body)))
    want = {2: '상태', 3: '이탈', 4: '한글', 5: '대량', 6: '사전', 10: '마지막 저장', 11: '조용함', 16: '확인'}
    bad = [str(n) + ':' + head[1 + n] + '(기대 ' + w + ')' for n, w in want.items() if head[1 + n] != w]
    check('색을 칠하는 열 위치가 맞다', not bad, bad)
    check('가운데 정렬 범위가 숫자 칸이다', head[4] == '이탈' and head[10] == '최종 문장',
          head[4] + ' ~ ' + head[10])

    # 페이지가 이탈 횟수를 자동 저장에 실어 보내는지 (안 보내면 수업 중 이탈 칸이 계속 빈다)
    check('자동 저장이 이탈 횟수를 보낸다',
          'function buildLiveMeta' in html and 'body.append("meta", buildLiveMeta());' in html,
          '이것이 없으면 제출 전까지 총괄의 이탈 칸이 비어 있다')
    seg2 = html[html.index('function buildLiveMeta'):html.index('function buildMeta')]
    for label in ['화면이탈 ', '한글입력 ', '대량입력 ', '사전 ', '소요 ']:
        check('자동 저장에 "' + label.strip() + '" 이 들어간다', label in seg2)
    check('이탈이 생기면 바로 보낸다', 'function flushSoon' in html and 'flushSoon();' in html)

check_status_sheet()

def new_page(b):
    ctx = b.new_context(viewport={'width': 1180, 'height': 900})
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.errs = errs
    pg.route(SCRIPT + '*', mock)
    pg.route('http://127.0.0.1:8880/index.html*', lambda route: route.fulfill(status=200, content_type='text/html; charset=utf-8', body=TEST_HTML))
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
    # 활용형은 기본형으로 찾아 주고, 확실하지 않으면 학생에게 알려야 한다
    A.fill('#dictQ', '배고픈'); A.keyboard.press('Enter'); A.wait_for_timeout(600)
    d = A.inner_text('#dictOut')
    flat = lambda t: ' '.join(t.split())
    check('활용형도 제 뜻을 찾는다', 'hungry' in d, flat(d)[:70])
    check('어떤 기본형으로 찾았는지 보여 준다', '배고프다' in d, flat(d)[:70])
    check('품사를 보여 준다', '형용사' in d, flat(d)[:90])
    check('뜻풀이를 보여 준다', '음식이 먹고 싶다' in d, flat(d)[:110])
    A.fill('#dictQ', '수상한'); A.keyboard.press('Enter'); A.wait_for_timeout(600)
    d = A.inner_text('#dictOut')
    check('확실하지 않은 뜻은 경고한다', '확실하지 않' in d, flat(d)[:80])
    check('확실한 뜻에는 경고가 없다', d.count('확실하지 않') == 1, d.count('확실하지 않'))
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
    A.wait_for_timeout(800)
    check('제출 뒤 PDF 를 따로 요청한다', ('10315', 'final') in pdfs and rows[0].get('finalPdf'), pdfs[-3:])
    check('학생 화면에 PDF 소식이 붙는다', 'PDF도 만들었습니다' in A.inner_text('#doneStatus'), A.inner_text('#doneStatus')[:80])

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
    ctxD, D = new_page(b); login(D, '10315', '가상하나', offline_ok=True)
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

    def to_final(pg, sid, name, line):
        """로그인 → 초안 시작 → 한 줄 → 초안 제출 → 다시 로그인해 최종 단계까지."""
        login(pg, sid, name); start_draft(pg)
        type_line(pg, 0, 0, line); pg.wait_for_timeout(300)
        pg.click('#submitBtn'); pg.wait_for_selector('#modal:not([hidden])')
        pg.click('#modalOk'); pg.wait_for_selector('#done:not([hidden])'); pg.wait_for_timeout(1200)
        login(pg, sid, name)

    # ── T13. 와이파이가 끊긴 채 최종 제출하면 "전송했습니다"라고 하지 않고, 연결되면 저절로 다시 보낸다 ──
    print('T13 끊긴 채 최종 제출 → 연결되면 저절로 다시 보냄')
    ctxG, G = new_page(b)
    to_final(G, '10201', '정민지', 'We need a quiet room for everyone.')
    check('최종 단계로 들어간다', G.inner_text('#phaseLabel') == '최종 글쓰기', G.inner_text('#phaseLabel'))
    G.click('#final'); G.keyboard.type('A quiet room helps us. We rely on it. It is good for all of us.')
    G.wait_for_timeout(300)
    DROP['net'] = True
    G.click('#submitBtn'); G.wait_for_selector('#modal:not([hidden])')
    G.click('#modalOk'); G.wait_for_selector('#done:not([hidden])'); G.wait_for_timeout(3500)
    st = G.inner_text('#doneStatus')
    rowG = next(r for r in rows if r['sid'] == '10201')
    check('끊겼을 때 "전송했습니다"라고 하지 않는다', '전송했습니다' not in st, st[:70])
    check('확인되지 않았다고 알린다', '확인되지 않' in st, st[:70])
    check('다시 보내기 단추가 보인다', not G.eval_on_selector('#retryBtn', 'e=>e.hidden'))
    check('서버에는 아직 최종 제출이 없다', rowG['phase'] != 'done', rowG['phase'])
    DROP['net'] = False
    G.evaluate("window.dispatchEvent(new Event('online'))"); G.wait_for_timeout(2500)
    st = G.inner_text('#doneStatus')
    check('연결되면 저절로 다시 보내 성공한다', '전송했습니다' in st, st[:70])
    check('서버 단계가 최종 제출이 된다', rowG['phase'] == 'done', rowG['phase'])
    check('최종 글이 서버에 있다', 'A quiet room helps us' in (rowG['data'] or ''))

    # ── T14. 열쇠를 잃은 학생: 선생님 현황 화면의 "기존 기록 잇기" → 다시 로그인하면 원래 글 ──
    print('T14 기존 기록 잇기')
    ctxH, H = new_page(b)
    to_final(H, '10202', '한지우', 'Original draft line for takeover.')
    ctxH.close()                                         # 원래 아이패드는 더 이상 없음 (열쇠 분실)
    ctxI, I = new_page(b); login(I, '10202', '한지우')
    check('새 기기는 중복 줄이 생긴다', sum(1 for r in rows if r['sid'] == '10202') == 2)
    check('이미 초안을 낸 학생은 새 기기에서 처음부터 시작하지 못함', '이미 제출한 기록' in I.inner_text('#dlgTitle') and I.eval_on_selector('#app', 'e=>e.hidden'),
          I.inner_text('#dlgTitle'))
    I.click('#dlgActions button:has-text("확인")'); I.wait_for_timeout(300)
    ctxT = b.new_context(viewport={'width': 1280, 'height': 900}); T = ctxT.new_page()
    T.route(SCRIPT + '*', mock)
    T.on('dialog', lambda d: d.accept())
    T.goto('http://127.0.0.1:8880/teacher.html?k=' + TKEY); T.wait_for_timeout(1500)
    T.click('.card:has-text("10202") >> text=1학년') if False else None
    btn = T.query_selector('.take[data-sid="10202"]')
    check('현황 화면에 "기존 기록 잇기" 단추가 보인다', btn is not None)
    if btn:
        btn.click(); T.wait_for_timeout(1500)
    orig = next(r for r in rows if r['sid'] == '10202' and r['dup'] is not True and r['dup'] != '이어받음')
    keyI = I.evaluate("localStorage.getItem('czkey:10202')")
    check('원래 줄이 새 기기 열쇠로 이어진다', orig['key'] == keyI)
    check('현황 화면에서 빈 중복 카드가 사라진다', T.query_selector('.take[data-sid="10202"]') is None)
    ctxT.close()
    check('원래 글은 그대로', 'Original draft line for takeover' in (orig['data'] or ''))
    I.click('#startBtn'); I.wait_for_timeout(1500)
    check('원래 단계(최종 글쓰기)로 열린다', I.inner_text('#phaseLabel') == '최종 글쓰기', I.inner_text('#phaseLabel'))
    check('원래 초안이 보인다', 'Original draft line' in I.eval_on_selector('[data-part="0"][data-line="0"]', 'e=>e.value'))
    check('다시 로그인한 뒤에는 저장을 받는다', keyI not in TAKEN)

    # ── T15. 같은 아이패드를 다른 학생이 쓸 때 앞 학생 학번을 쳐도 글이 열리지 않는다 ──
    print('T15 공용 아이패드에서 남의 글이 열리지 않는다')
    G.goto('http://127.0.0.1:8880/index.html?as=1')
    G.fill('#sid', '10201'); G.fill('#name', '김철수'); G.click('#startBtn'); G.wait_for_timeout(800)
    check('이름이 다르면 확인 창이 뜬다 (이 기기 기록)', '이름이 다릅니다' in G.inner_text('#dlgTitle'), G.inner_text('#dlgTitle'))
    check('창에 원래 이름을 다 보여 주지 않는다', '정민지' not in G.inner_text('#dlgText'))
    G.click('#dlgActions button:has-text("다시 입력")'); G.wait_for_timeout(400)
    check('글 화면이 열리지 않는다', G.eval_on_selector('#app', 'e=>e.hidden') and G.eval_on_selector('#done', 'e=>e.hidden'))
    keyG = G.evaluate("localStorage.getItem('czkey:10201')")
    ctxJ, J = new_page(b)
    J.goto('http://127.0.0.1:8880/index.html?as=1')
    J.evaluate("k => localStorage.setItem('czkey:10201', k)", keyG)
    J.fill('#sid', '10201'); J.fill('#name', '김철수'); J.click('#startBtn'); J.wait_for_timeout(1200)
    check('서버도 이름이 다르면 열어 주지 않는다', '이름이 다릅니다' in J.inner_text('#dlgTitle'), J.inner_text('#dlgTitle'))
    J.click('#dlgActions button:has-text("다시 입력")'); J.wait_for_timeout(300)
    check('서버 확인 뒤에도 글 화면이 열리지 않는다', J.eval_on_selector('#app', 'e=>e.hidden') and J.eval_on_selector('#done', 'e=>e.hidden'))
    ctxJ.close()

    # ── T16. 주소에 ?d=60 을 붙여도 시간이 늘지 않는다 / 교사 조작이 기록된다 ──
    print('T16 주소로 시간 늘리기 막힘 / 교사 조작 기록')
    ctxK, K = new_page(b)
    K.goto('http://127.0.0.1:8880/index.html?as=1&d=60')
    K.fill('#sid', '10203'); K.fill('#name', '오세훈'); K.click('#startBtn'); K.wait_for_timeout(1200)
    start_draft(K)
    check('?d=60 이어도 초안은 20분이다', near20(K.inner_text('#timer')), K.inner_text('#timer'))
    teacher(K, '#teacherBtn', '5분 추가')
    K.click('[data-part="0"][data-line="0"]'); K.keyboard.type('Hi'); K.wait_for_timeout(1800)
    lastK = [x for x in posts if x['sid'] == '10203' and x['phase'] == 'save']
    check('교사 조작이 자동집계에 남는다', bool(lastK) and '교사조작 1회' in lastK[-1]['meta'], lastK[-1]['meta'][-80:] if lastK else '')
    ctxK.close()

    # ── T17. 지난 시간에 초안을 내지 못하고 닫은 학생: 다음 로그인 때 초안을 내고 곧바로 최종 단계 ──
    print('T17 지난 시간 미제출 초안 → 다음 시간 바로 최종')
    ctxL, L = new_page(b)
    login(L, '10204', '윤아름'); start_draft(L)
    type_line(L, 0, 0, 'Left without submitting.'); L.wait_for_timeout(1500)
    L.goto('http://127.0.0.1:8880/index.html?as=1'); L.wait_for_timeout(500)     # 화면을 닫음 (로그인 화면에서는 저장이 돌지 않음)
    L.evaluate("""() => { const k = Object.keys(localStorage).find(x => x.startsWith('cz1:') && x.endsWith('10204'));
        const st = JSON.parse(localStorage.getItem(k)); st.phaseStartedAt = Date.now() - 4 * 3600 * 1000;
        localStorage.setItem(k, JSON.stringify(st)); }""")
    rowL = next(r for r in rows if r['sid'] == '10204')
    _d = json.loads(rowL['data']); _d['phaseStartedAt'] = int(time.time() * 1000) - 4 * 3600 * 1000; rowL['data'] = json.dumps(_d)
    L.fill('#sid', '10204'); L.fill('#name', '윤아름'); L.click('#startBtn'); L.wait_for_timeout(2500)
    check('초안이 서버에 제출된다', rowL['draftAt'] is not None)
    check('한 번 더 로그인하지 않아도 최종 글쓰기로 간다', L.inner_text('#phaseLabel') == '최종 글쓰기' and L.eval_on_selector('#done', 'e=>e.hidden'),
          L.inner_text('#phaseLabel'))
    check('최종 타이머가 새로 20분이다', near20(L.inner_text('#timer')), L.inner_text('#timer'))
    ctxL.close()

    # ── T18. 명단과 다르면 막지 않고 확인받은 뒤 들어가고, 선생님 쪽에 표시된다 ──
    print('T18 명단 확인 (막지 않음, 확인 + 표시)')
    ROSTER.update({'10301': '최유진'})
    ctxM, M = new_page(b)
    login(M, '10399', '전학생')
    check('명단에 없는 학번이면 확인 창이 뜬다', '확인하세요' in M.inner_text('#dlgTitle') and '명단에 없습니다' in M.inner_text('#dlgText'), M.inner_text('#dlgTitle'))
    M.click('#dlgActions button:has-text("다시 입력")'); M.wait_for_timeout(300)
    check('"다시 입력"이면 들어가지 않고 줄도 안 생긴다', M.eval_on_selector('#app', 'e=>e.hidden') and not any(r['sid'] == '10399' for r in rows))
    M.click('#startBtn'); M.wait_for_timeout(1200)
    M.click('#dlgActions button:has-text("이대로 시작")'); M.wait_for_timeout(1500)
    check('"이대로 시작"이면 들어간다 (전학생 등)', not M.eval_on_selector('#app', 'e=>e.hidden'))
    r18 = next((r for r in rows if r['sid'] == '10399'), None)
    check('그 줄에 명단 확인 표시가 남는다', bool(r18 and r18.get('rm')))
    ctxM.close()
    ctxM2, M2 = new_page(b)
    login(M2, '10301', '최유친')
    check('이름이 명단과 다르면 확인 창이 뜬다', '이름과 입력한 이름이 다릅니다' in M2.inner_text('#dlgText'), M2.inner_text('#dlgText')[:40])
    M2.click('#dlgActions button:has-text("다시 입력")'); M2.wait_for_timeout(300)
    login(M2, '10301', '최 유진')
    check('명단과 같으면(띄어쓰기 무시) 확인 없이 들어간다', not M2.eval_on_selector('#app', 'e=>e.hidden'))
    ctxM2.close()
    ROSTER.clear()

    # ── T19. 구글이 "동시 실행이 너무 많음"으로 돌려보내도 로그인·제출이 저절로 다시 되어 성공한다 ──
    print('T19 동시 실행 한도에 걸려도 저절로 다시 시도')
    ctxN, N = new_page(b)
    BUSY['n'] = 2
    N.goto('http://127.0.0.1:8880/index.html?as=1')
    N.fill('#sid', '10205'); N.fill('#name', '서하린'); N.click('#startBtn')
    try: N.wait_for_selector('#app:not([hidden])', timeout=30000)
    except Exception: pass
    check('로그인이 결국 된다', not N.eval_on_selector('#app', 'e=>e.hidden'), N.inner_text('#gateNote'))
    check('줄이 하나만 생긴다', sum(1 for r in rows if r['sid'] == '10205') == 1)
    start_draft(N); type_line(N, 0, 0, 'Busy server test line.'); N.wait_for_timeout(500)
    BUSY['n'] = 1
    N.click('#submitBtn'); N.wait_for_selector('#modal:not([hidden])')
    N.click('#modalOk'); N.wait_for_selector('#done:not([hidden])'); N.wait_for_timeout(16000)
    rowN = next(r for r in rows if r['sid'] == '10205')
    check('초안 제출이 결국 된다', rowN['draftAt'] is not None and '저장되었습니다' in N.inner_text('#doneStatus'), N.inner_text('#doneStatus')[:60])
    ctxN.close()

    # ── T20. 비상용 PDF 저장: 오른쪽 아래 작은 단추 → 인쇄·공유 창. 이탈로 세지 않고, 횟수는 자동집계에 남김 ──
    print('T20 비상용 PDF 저장')
    ctxP, P = new_page(b)
    P.goto('http://127.0.0.1:8880/index.html?as=1'); P.wait_for_timeout(400)
    check('로그인 전에는 PDF 단추가 안 보임', P.eval_on_selector('#pdfBtn', 'e=>e.hidden'))
    P.fill('#sid', '10206'); P.fill('#name', '나비상'); P.click('#startBtn'); P.wait_for_timeout(1200)
    check('글 화면에서는 PDF 단추가 보임', not P.eval_on_selector('#pdfBtn', 'e=>e.hidden'))
    box = P.eval_on_selector('#pdfBtn', 'e=>{const r=e.getBoundingClientRect(); return [r.right, r.bottom, innerWidth, innerHeight, getComputedStyle(e).opacity]}')
    check('단추는 오른쪽 아래 구석에 흐리게', box[2] - box[0] < 12 and box[3] - box[1] < 12 and float(box[4]) < 0.5, box)
    start_draft(P)
    type_line(P, 0, 0, 'Emergency backup sentence here.'); P.wait_for_timeout(300)
    leaves0 = P.evaluate('state.leaves.length')
    P.evaluate("window.__printed = 0; window.print = () => { window.__printed++; window.dispatchEvent(new Event('blur')); }; 0")   # 끝을 0 으로: 함수로 끝나면 시험 도구가 그 함수를 한 번 불러 버림
    P.click('#pdfBtn'); P.wait_for_timeout(1800)
    check('인쇄·공유 창을 부름', P.evaluate('window.__printed') == 1, P.evaluate('window.__printed'))
    pv = P.inner_text('#printView')
    check('PDF 내용에 학번·이름·쓴 글이 들어감', '10206' in pv and '나비상' in pv and 'Emergency backup sentence' in pv and 'Step 3 초안' in pv, pv[:80])
    check('PDF 저장하는 동안 이탈로 세지 않음', P.evaluate('state.leaves.length') == leaves0)
    P.wait_for_timeout(1500)
    lastP = [x for x in posts if x['sid'] == '10206' and x['phase'] == 'save']
    check('PDF 저장 횟수가 자동집계에 남음', bool(lastP) and 'PDF저장 1회' in lastP[-1]['meta'], lastP[-1]['meta'][-60:] if lastP else '')
    P.click('#submitBtn'); P.wait_for_selector('#modal:not([hidden])'); P.click('#modalOk'); P.wait_for_selector('#done:not([hidden])'); P.wait_for_timeout(800)
    check('제출 화면에서도 PDF 단추가 보임', not P.eval_on_selector('#pdfBtn', 'e=>e.hidden'))
    ctxP.close()

    # ── T21. 현황판에서 학생 조작: 카드 오른쪽 클릭 → 학생 화면에 반영 ──
    print('T21 현황판 조작')
    ctxS, Sx = new_page(b)
    Sx.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); Sx.wait_for_timeout(300)
    Sx.fill('#sid', '10207'); Sx.fill('#name', '조작학생'); Sx.click('#startBtn'); Sx.wait_for_timeout(1500)
    ctxS2, S2 = new_page(b)
    S2.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); S2.wait_for_timeout(300)
    S2.fill('#sid', '10208'); S2.fill('#name', '조작둘'); S2.click('#startBtn'); S2.wait_for_timeout(1500)
    ctxT2 = b.new_context(viewport={'width': 1280, 'height': 900}); T2 = ctxT2.new_page()
    T2.route(SCRIPT + '*', mock)
    answers = {'prompt': '책상 위를 정리하세요'}
    T2.on('dialog', lambda d: d.accept(answers['prompt'] if d.type == 'prompt' else None))
    T2.goto('http://127.0.0.1:8880/teacher.html#k=' + TKEY); T2.wait_for_selector('.card', timeout=15000)
    tab = T2.query_selector('.tabs button[data-c="1학년 2반"]')
    if tab: tab.click(); T2.wait_for_timeout(1500)
    def menu(sid, label, right=True):
        card = T2.wait_for_selector('.card[data-sid="%s"]' % sid, timeout=10000)
        if right: card.click(button='right')
        else: T2.click('.card[data-sid="%s"] .more' % sid)
        T2.wait_for_selector('#cmenu:not([hidden])', timeout=5000)
        T2.click('#cmenu button:has-text("%s")' % label); T2.wait_for_timeout(1200)
    menu('10207', '5분 더 주기')
    check('현황판: 보냈다는 안내', '보냈습니다' in T2.inner_text('#tnote'), T2.inner_text('#tnote')[:50])
    Sx.wait_for_timeout(2500)
    check('학생 화면: 5분이 늘어남', Sx.evaluate('state.extraSec') == 300, Sx.evaluate('state.extraSec'))
    check('다른 학생에게는 안 감', S2.evaluate('state.extraSec || 0') == 0)
    menu('10207', '초안 쓰기 단계로', right=False)
    Sx.wait_for_timeout(2500)
    check('학생 화면: 초안 단계로 넘어감 (⋯ 단추)', Sx.inner_text('#phaseLabel') == '초안 쓰기', Sx.inner_text('#phaseLabel'))
    T2.wait_for_timeout(3500)    # 현황 화면이 새 단계를 읽어 오게
    menu('10207', '메시지 보내기')
    Sx.wait_for_timeout(2500)
    check('학생 화면: 선생님 메시지 창', '선생님 메시지' in Sx.inner_text('#dlgTitle') and '책상 위를 정리하세요' in Sx.inner_text('#dlgText'), Sx.inner_text('#dlgText')[:30])
    Sx.click('#dlgActions button:has-text("확인")'); Sx.wait_for_timeout(300)
    type_line(Sx, 0, 0, 'Teacher made me submit.'); Sx.wait_for_timeout(500)
    menu('10207', '지금 제출시키기')
    Sx.wait_for_timeout(3500)
    check('학생 화면: 지금 제출됨', not Sx.eval_on_selector('#done', 'e=>e.hidden') and Sx.evaluate('state.phase') == 'draftDone', Sx.evaluate('state.phase'))
    T2.wait_for_timeout(3500)
    menu('10207', '제출 취소')
    Sx.wait_for_timeout(3500)
    check('학생 화면: 제출 취소로 다시 열림', Sx.evaluate('state.phase') == 'draft' and not Sx.eval_on_selector('#app', 'e=>e.hidden'), Sx.evaluate('state.phase'))
    T2.click('#classMenu'); T2.wait_for_selector('#cmenu:not([hidden])')
    T2.click('#cmenu button:has-text("5분 더 주기")'); T2.wait_for_timeout(1500)
    check('반 전체: 보낸 학생 수 안내', '명에게' in T2.inner_text('#tnote'), T2.inner_text('#tnote')[:40])
    Sx.wait_for_timeout(2500)
    check('반 전체: 두 학생 모두 반영', S2.evaluate('state.extraSec') == 300 and Sx.evaluate('state.extraSec') >= 300, [S2.evaluate('state.extraSec'), Sx.evaluate('state.extraSec')])
    Sx.wait_for_timeout(1500)
    lastS = [x for x in posts if x['sid'] == '10207' and x['phase'] == 'save']
    check('학생 기록에 현황판 조작이 남음', bool(lastS) and '현황판: 5분 추가' in lastS[-1]['meta'] and '현황판: 제출 취소' in lastS[-1]['meta'], lastS[-1]['meta'][-120:] if lastS else '')
    check('같은 조작을 두 번 적용하지 않음', Sx.evaluate("state.tlog.filter(x => x.a === '현황판: 5분 추가').length") == 2)
    for c_ in (ctxS, ctxS2, ctxT2): c_.close()

    # ── T22. 2회차 마감: 초안을 낸 학생은 선생님이 열 때까지 2회차를 못 함, 연 뒤 3시간만 ──
    print('T22 2회차 마감과 열기')
    FINAL['default'] = False
    def to_draftdone(pg, sid, name):
        pg.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); pg.fill('#sid', sid); pg.fill('#name', name); pg.click('#startBtn'); pg.wait_for_timeout(1300)
        start_draft(pg); type_line(pg, 0, 0, 'Draft by ' + name + '.'); pg.wait_for_timeout(300)
        pg.click('#submitBtn'); pg.wait_for_selector('#modal:not([hidden])'); pg.click('#modalOk'); pg.wait_for_selector('#done:not([hidden])'); pg.wait_for_timeout(1000)
    ctxZ, Z = new_page(b); to_draftdone(Z, '10301', '마감하나')
    check('초안 제출 화면: 선생님이 열면 시작된다는 안내', '선생님이 열면' in Z.inner_text('#doneHint'), Z.inner_text('#doneHint')[:40])
    Z.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); Z.fill('#sid', '10301'); Z.fill('#name', '마감하나'); Z.click('#startBtn'); Z.wait_for_timeout(1500)
    check('집에서 다시 들어와도 2회차가 열리지 않음', not Z.eval_on_selector('#done', 'e=>e.hidden') and Z.eval_on_selector('#app', 'e=>e.hidden'), Z.evaluate('state.phase'))
    rz = next(r for r in rows if r['sid'] == '10301' and r['name'] == '마감하나')
    Z.evaluate("() => { state.phase = 'final'; }")
    code = Z.evaluate("async () => (await sendToServer(submitBody('final', 'x', 'final'))).split('\\n')[0]")
    check('서버도 닫힌 2회차 제출을 받지 않음', code == 'CLOSED' and rz['phase'] == 'draftDone', code)
    Z.evaluate("() => { state.phase = 'draftDone'; }")
    ctxY, Y = new_page(b); to_draftdone(Y, '10302', '마감둘')
    ctxT3 = b.new_context(viewport={'width': 1280, 'height': 900}); T3 = ctxT3.new_page()
    T3.route(SCRIPT + '*', mock); T3.on('dialog', lambda d: d.accept())
    T3.goto('http://127.0.0.1:8880/teacher.html#k=' + TKEY); T3.wait_for_selector('.card', timeout=15000)
    tab = T3.query_selector('.tabs button[data-c="1학년 3반"]')
    if tab: tab.click(); T3.wait_for_timeout(1500)
    check('현황 막대: 2회차 닫힘', '닫힘' in T3.inner_text('#bar'), T3.inner_text('#bar')[:80])
    T3.click('.card[data-sid="10302"]', button='right'); T3.wait_for_selector('#cmenu:not([hidden])')
    T3.click('#cmenu button:has-text("이 학생 2회차 열기")'); T3.wait_for_timeout(1500)
    Y.wait_for_timeout(2500)
    check('학생 한 명만 열기: 그 학생은 저절로 최종 글쓰기로', Y.inner_text('#phaseLabel') == '최종 글쓰기' and not Y.eval_on_selector('#app', 'e=>e.hidden'), Y.evaluate('state.phase'))
    check('다른 학생은 여전히 닫힘', Z.eval_on_selector('#app', 'e=>e.hidden'))
    T3.click('#classMenu'); T3.wait_for_selector('#cmenu:not([hidden])')
    T3.click('#cmenu button:has-text("2회차 열기")'); T3.wait_for_timeout(2000)
    Z.wait_for_timeout(2500)
    check('반 전체 열기: 기다리던 학생 화면이 저절로 최종 글쓰기로', Z.inner_text('#phaseLabel') == '최종 글쓰기' and not Z.eval_on_selector('#app', 'e=>e.hidden'), Z.evaluate('state.phase'))
    check('현황 막대: 2회차 열림 ~시각', '열림 ~' in T3.inner_text('#bar'), T3.inner_text('#bar')[:80])
    T3.click('#classMenu'); T3.wait_for_selector('#cmenu:not([hidden])')
    T3.click('#cmenu button:has-text("2회차 닫기")'); T3.wait_for_timeout(1500)
    check('반 닫기: 서버 기록에서 빠짐', 'c:1학년 3반' not in OPEN)
    # 조사 중에 나간 학생이 몇 시간 뒤 들어옴 → 그대로 초안으로 내고 마감
    ctxW, W = new_page(b)
    W.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); W.fill('#sid', '10303'); W.fill('#name', '마감셋'); W.click('#startBtn'); W.wait_for_timeout(1300)
    W.click('[data-step2="0"]'); W.keyboard.type('only research'); W.wait_for_timeout(1500)
    W.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); W.wait_for_timeout(300)
    W.evaluate("""() => { const k = Object.keys(localStorage).find(x => x.startsWith('cz1:') && x.endsWith('10303'));
        const st = JSON.parse(localStorage.getItem(k)); st.phaseStartedAt = Date.now() - 4 * 3600 * 1000; localStorage.setItem(k, JSON.stringify(st)); }""")
    rw = next(r for r in rows if r['sid'] == '10303')
    _d = json.loads(rw['data']); _d['phaseStartedAt'] = int(time.time() * 1000) - 4 * 3600 * 1000; rw['data'] = json.dumps(_d)
    W.fill('#sid', '10303'); W.fill('#name', '마감셋'); W.click('#startBtn'); W.wait_for_timeout(2500)
    check('조사 중 나간 학생: 다시 들어오면 초안으로 내고 마감', rw['phase'] == 'draftDone' and W.eval_on_selector('#app', 'e=>e.hidden'), rw['phase'])
    for c_ in (ctxZ, ctxY, ctxT3, ctxW): c_.close()
    FINAL['default'] = True

    print('T23 1회차에 기기 두 대: 로그인만 한 기기 + 초안 낸 기기')
    ctxP, P = new_page(b)
    P.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); P.fill('#sid', '10320'); P.fill('#name', '두기기'); P.click('#startBtn'); P.wait_for_timeout(1300)
    ctxQ, Q2 = new_page(b); to_draftdone(Q2, '10320', '두기기')
    mine = [r for r in rows if r['sid'] == '10320']
    check('시트에는 줄이 두 개 (조사 중 + 초안 제출)', sorted(r['phase'] for r in mine) == ['draftDone', 'research'], [r['phase'] for r in mine])
    ms_ = [s for s in monitor(TKEY)['students'] if s['sid'] == '10320']
    check('현황에는 카드 하나 (초안 제출, 다른 기기 1)', len(ms_) == 1 and ms_[0]['ph'] == 'draftDone' and ms_[0]['od'] == 1 and 'kp' not in ms_[0], ms_)
    qkey = next(r['key'] for r in mine if r['phase'] == 'draftDone')
    P.goto('http://127.0.0.1:8880/index.html?as=1&cp=1'); P.fill('#sid', '10320'); P.fill('#name', '두기기'); P.click('#startBtn'); P.wait_for_timeout(1800)
    check('로그인만 한 기기로 다시 들어오면 낸 초안이 열림 (2회차가 열려 있으니 최종 작성으로, 조사 중으로 되돌아가지 않음)',
          P.evaluate('state.phase') in ('draftDone', 'final') and P.evaluate("localStorage.getItem('czkey:10320')") == qkey, P.evaluate('state.phase'))
    check('멈춘 줄은 이어받음으로 숨김, 낸 줄은 그대로', [r['dup'] for r in mine if r['phase'] == 'research'] == ['이어받음'] and P.evaluate("document.body.innerText").find('Draft by 두기기') >= 0
          and next(r for r in mine if r['dup'] != '이어받음')['key'] == qkey)
    for c_ in (ctxP, ctxQ): c_.close()

    # ── 마무리 ──
    print('마무리')
    allerrs = {'A': A.errs, 'C': C.errs, 'G': G.errs, 'I': I.errs}
    check('페이지 오류가 없다', not any(allerrs.values()), allerrs)
    check('토큰이 맞지 않는 요청이 없다', not any(x for x in posts if x.get('token') == 'bad'))
    # 구글 다중 로그인(/u/1/) 문제를 피하려면 반드시 쿠키 없는 fetch 를 써야 한다.
    check('읽기가 쿠키 없는 방식(fetch)으로 나간다', uses['fetch'] > 0, uses)
    check('예전 방식(JSONP)으로 새지 않는다', uses['jsonp'] == 0,
          str(uses) + ' — JSONP 는 <script> 태그라 구글 쿠키가 함께 가고, 계정이 여러 개면 실패한다')
    b.close()

srv.shutdown()
print()
if fails:
    print('FAIL (' + str(len(fails)) + '건)')
    for f in fails:
        print(' - ' + f)
    sys.exit(1)
print('PASS')

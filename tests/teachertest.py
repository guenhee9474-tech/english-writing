"""
선생님 현황 페이지(docs/teacher.html) 자동 테스트.
  실행: python tests/teachertest.py      통과 기준: 마지막 줄에 PASS
가짜 monitor 서버를 붙여 열쇠 확인·카드 색·정렬·반 바꾸기·자동 새로고침을 실제 브라우저로 확인한다.
"""
import threading, http.server, socketserver, functools, urllib.parse, json, os, re, sys, time

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs')
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DOCS)
class Q(socketserver.TCPServer): allow_reuse_address = True
srv = Q(('127.0.0.1', 8882), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

# 윈도우 기본 콘솔(cp949)에서 이모지·특수문자 때문에 출력이 죽지 않게 한다
try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception: pass

from playwright.sync_api import sync_playwright
html = open(os.path.join(DOCS, 'teacher.html'), encoding='utf-8').read()
SCRIPT = re.search(r'SCRIPT_URL = "([^"]+)"', html).group(1)
KEY = "testkey123"
NOW = int(time.time() * 1000)

STUDENTS = [
    dict(sid="10101", nm="김하늘", ph="draft",     lv=0, hg=0, bs=0, dc=1, sn=3, at=NOW - 20 * 1000,      dr=0, fn=0, dup=False),
    dict(sid="10102", nm="이서준", ph="draft",     lv=4, hg=1, bs=0, dc=0, sn=2, at=NOW - 10 * 1000,      dr=0, fn=0, dup=False),
    dict(sid="10103", nm="박서연", ph="draftDone", lv=1, hg=0, bs=0, dc=2, sn=9, at=NOW - 60 * 1000,      dr=NOW - 55 * 1000, fn=0, dup=False),
    dict(sid="10104", nm="최민준", ph="done",      lv=0, hg=0, bs=0, dc=3, sn=9, at=NOW - 120 * 1000,     dr=NOW - 900 * 1000, fn=NOW - 100 * 1000, dup=False),
    dict(sid="10105", nm="정하윤", ph="final",     lv=8, hg=3, bs=2, dc=0, sn=9, at=NOW - 300 * 1000,     dr=NOW - 999 * 1000, fn=0, dup=True),
    dict(sid="10106", nm="강도윤", ph="",          lv=0, hg=0, bs=0, dc=0, sn=0, at=0,                    dr=0, fn=0, dup=False),
]

calls = {"n": 0}
def mock(route):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(route.request.url).query)
    g = lambda k: q.get(k, [''])[0]
    cb = g('callback') or 'cb'
    calls["n"] += 1
    if g('action') != 'monitor':
        out = {'error': 'BAD'}
    elif g('k') != KEY:
        out = {'error': 'BAD_KEY'}
    else:
        cls = g('cls')
        out = {'ok': True, 'at': NOW, 'cls': cls, 'classes': ['1학년 1반', '1학년 2반'],
               'students': STUDENTS if (not cls or cls == '1학년 1반') else []}
    route.fulfill(status=200, content_type='application/javascript', body=cb + '(' + json.dumps(out) + ')')

fails = []
def check(label, cond, detail=''):
    print(('  OK   ' if cond else '  FAIL ') + label + (' :: ' + str(detail) if detail else ''))
    if not cond: fails.append(label + (' :: ' + str(detail) if detail else ''))

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1280, 'height': 900})
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    pg.route(SCRIPT + '*', mock)

    print('현황 페이지')
    # 1) 열쇠 없이 열면 안내가 뜬다
    pg.goto('http://127.0.0.1:8882/teacher.html')
    pg.wait_for_timeout(500)
    check('열쇠 없이 열면 안내가 뜬다', '열쇠가 필요합니다' in pg.inner_text('body'))
    check('열쇠 없이는 서버를 부르지 않는다', calls["n"] == 0, calls["n"])

    # 2) 틀린 열쇠
    pg.goto('http://127.0.0.1:8882/teacher.html?k=wrong')
    pg.wait_for_timeout(900)
    check('틀린 열쇠는 거부된다', '열쇠가 맞지 않습니다' in pg.inner_text('body'))

    # 3) 정상
    pg.goto('http://127.0.0.1:8882/teacher.html?k=' + KEY)
    pg.wait_for_selector('.card', timeout=8000)
    pg.wait_for_timeout(400)
    cards = pg.query_selector_all('.card')
    check('학생 카드가 모두 그려진다', len(cards) == 6, len(cards))
    check('반 탭이 두 개다', len(pg.query_selector_all('#tabs button')) == 2)
    bar = pg.inner_text('#bar')
    check('접속 인원이 맞다', '5 / 6' in bar.replace('\n', ' '), bar.replace('\n', ' ')[:80])
    check('이탈 인원이 맞다', re.search(r'이탈\s*3명', bar) is not None, bar.replace('\n', ' ')[:120])

    # 4) 이탈 표시
    def card_of(nm):
        for c in pg.query_selector_all('.card'):
            if nm in c.inner_text(): return c
        return None
    c2 = card_of('이서준')
    check('이탈한 학생 카드가 빨갛게 표시된다', 'leave' in c2.get_attribute('class'), c2.get_attribute('class'))
    check('이탈 횟수가 크게 보인다', c2.query_selector('.lv').inner_text() == '4')
    c1 = card_of('김하늘')
    check('이탈 없는 학생은 표시가 없다', 'leave' not in c1.get_attribute('class') and c1.query_selector('.lv') is None)
    c6 = card_of('강도윤')
    check('미접속 학생이 회색으로 보인다', 'off' in c6.get_attribute('class'))
    check('미접속 안내가 뜬다', '아직 안 들어옴' in c6.inner_text())
    c5 = card_of('정하윤')
    check('조용한 학생이 표시된다', 'quiet' in c5.get_attribute('class'), c5.get_attribute('class'))
    check('한글·대량·중복이 함께 보인다', '한글 3' in c5.inner_text() and '대량 2' in c5.inner_text() and '중복' in c5.inner_text(),
          c5.inner_text().replace('\n', ' '))
    c4 = card_of('최민준')
    check('최종 제출 학생이 초록으로 보인다', 'done' in c4.get_attribute('class'))

    # 5) 정렬 바꾸기
    pg.click('button[data-s="leave"]')
    pg.wait_for_timeout(300)
    first = pg.query_selector_all('.card')[0].inner_text()
    check('이탈 많은 순으로 정렬된다', '정하윤' in first, first.replace('\n', ' ')[:40])
    pg.click('button[data-s="sid"]')
    pg.wait_for_timeout(300)
    check('학번 순으로 되돌아간다', '김하늘' in pg.query_selector_all('.card')[0].inner_text())

    # 6) 반 바꾸기
    pg.click('#tabs button:has-text("1학년 2반")')
    pg.wait_for_timeout(900)
    check('빈 반은 안내가 나온다', '아직 접속한 학생이 없습니다' in pg.inner_text('#body'))

    # 7) 자동 새로고침
    n0 = calls["n"]
    pg.wait_for_timeout(8500)
    check('몇 초마다 저절로 다시 읽는다', calls["n"] > n0, str(n0) + ' -> ' + str(calls["n"]))
    check('갱신 시각이 표시된다', '갱신' in pg.inner_text('#fresh'), pg.inner_text('#fresh'))

    check('페이지 오류가 없다', not errs, errs)
    b.close()

srv.shutdown()
print()
if fails:
    print('FAIL (' + str(len(fails)) + '건)')
    for f in fails: print(' - ' + f)
    sys.exit(1)
print('PASS')

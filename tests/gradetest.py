"""
채점 페이지(docs/grade.html) 자동 테스트.
  실행: python tests/gradetest.py      통과 기준: 마지막 줄에 PASS
가짜 서버(grade 읽기·gradeSave 저장)를 붙여 열쇠 확인·반 탭·자동 점수·오류 수 입력·가감·엑셀·인쇄,
그리고 학생 글·AI 표시·메모에 넣은 HTML/스크립트가 실행되지 않는지를 실제 브라우저로 확인한다.
"""
import functools, http.server, io, json, os, re, socketserver, sys, threading, time, urllib.parse, zipfile

DOCS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs')
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=DOCS)
class Q(socketserver.TCPServer): allow_reuse_address = True
srv = Q(('127.0.0.1', 8883), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception: pass

from playwright.sync_api import sync_playwright
html = open(os.path.join(DOCS, 'grade.html'), encoding='utf-8').read()
SCRIPT = re.search(r'SCRIPT_URL = "([^"]+)"', html).group(1)
KEY = "gradekey-0123456789abcdef"
GOOD = ("Our school should be an inclusive place. The library is not accessible to students in wheelchairs. "
        "Regardless of age, everyone can benefit from a ramp. We must ensure that every student can use it. "
        "Many students rely on the elevator. We can make use of the empty room. A ramp makes it easier for them to move. "
        "That is the reason why we need change. Thank you for reading.")
EVIL = 'Hello <img src=x onerror="window.__pwned=1"> world. <script>window.__pwned=2</script> Bye.'
DB = {
    "10101": dict(c="101", sid="10101", nm="김하늘", ph="done", dup=False, dr=1761400000000, fn=1761500000000, final=GOOD, pdf="https://drive.google.com/file/d/x",
                  g=dict(e=None, ov={}, memo="", adj=[], marks=[{"s": GOOD.index("is not accessible"), "e": GOOD.index("is not accessible") + 17, "k": "문법", "q": "is not accessible", "f": "isn't", "w": "<b>예시</b>"}])),
    "10102": dict(c="101", sid="10102", nm="이서준", ph="draftDone", dup=False, dr=1761400000000, fn=0, final="", pdf="", g=None),
    "10103": dict(c="101", sid="10103", nm="<i>박</i>", ph="done", dup=False, dr=0, fn=1761500000000, final=EVIL, pdf="javascript:alert(1)", g=None),
    "10104": dict(c="101", sid="10104", nm="강도윤", ph="", dup=False, dr=0, fn=0, final="", pdf="", g=None),
    "10201": dict(c="102", sid="10201", nm="최민준", ph="done", dup=False, dr=1, fn=2, final="One two. Three four. Five six.", pdf="", g=None),
}
saves = []


def mock(route):
    req = route.request
    if req.method == "POST":
        p = {k: v[0] for k, v in urllib.parse.parse_qs(req.post_data or "").items()}
        saves.append(p)
        if p.get("k") != KEY:
            out = {"error": "BAD_KEY"}
        else:
            s = DB[p["sid"]]
            g = s["g"] or dict(e=None, ov={}, memo="", adj=[], marks=None)
            if "e" in p: g["e"] = None if p["e"] == "" else int(p["e"])
            if "ov" in p: g["ov"] = json.loads(p["ov"])
            if "memo" in p: g["memo"] = p["memo"]
            if "adj" in p: g["adj"] = json.loads(p["adj"])
            if "ok" in p: g["ok"] = json.loads(p["ok"])
            s["g"] = g
            out = {"ok": True, "g": g}
    else:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(req.url).query)
        out = {"ok": True, "students": list(DB.values())} if q.get("k", [""])[0] == KEY else {"error": "BAD_KEY"}
    route.fulfill(status=200, content_type='application/json', headers={"Access-Control-Allow-Origin": "*"}, body=json.dumps(out))


results = []
def check(label, cond, detail=''):
    results.append(bool(cond))
    print(('  ok  ' if cond else 'FAIL  ') + label + ('' if cond else '  ' + str(detail)))


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(accept_downloads=True)
    pg = ctx.new_page()
    pg.route(SCRIPT + '*', mock)
    pg.goto('http://127.0.0.1:8883/grade.html')
    pg.wait_for_timeout(500)
    check('열쇠 없이 열면 안내', '열쇠' in pg.inner_text('#msg'))

    pg.goto('http://127.0.0.1:8883/grade.html#k=wrong-key-but-long-enough')
    pg.reload(); pg.wait_for_timeout(600)
    check('틀린 열쇠면 막힘', '맞지 않습니다' in pg.inner_text('#msg'))

    pg.goto('http://127.0.0.1:8883/grade.html?k=' + KEY)
    pg.wait_for_timeout(800)
    check('?k= 로 열면 주소를 #k= 로 바꿈 (서버 기록에 덜 남게)', '?k=' not in pg.url and '#k=' in pg.url)
    check('반 탭 두 개', pg.locator('#tabs button').count() == 2)
    check('반 정보: 4명, 입력 남음 2명 (최종 낸 학생만)', '4명' in pg.inner_text('#clsInfo') and '입력 남음 2명' in pg.inner_text('#clsInfo'), pg.inner_text('#clsInfo'))
    lst = pg.inner_text('#list')
    check('최종 안 낸 학생은 바로 총점 (16), 미응시는 0', '16' in lst and lst.strip().endswith('0'), lst)

    pg.click('button[data-sid="10101"]'); pg.wait_for_timeout(300)
    check('Word Bank 밑줄 8곳 이상 (AI 표시와 겹친 곳은 표시가 앞)', pg.locator('.text .wb').count() >= 8)
    check('AI 표시 1개 (빨간 칠)', pg.locator('.text .mk').count() == 1)
    check('AI 표시의 HTML 은 글자로만', '<b>예시</b>' in pg.inner_text('.marks') and pg.locator('.marks b').count() == 0)
    check('자동: 참여 24 · 분량 12 · 표현 12, 총점은 오류 수 전이라 ?', pg.inner_text('#score .total').startswith('?'))
    pg.click('.marks li[data-mid] .tg'); pg.wait_for_timeout(1200)
    mid = pg.get_attribute('.marks li[data-mid]', 'data-mid')
    check("AI 표시를 '오류로 셈' → 오류 수 1, 어느 표시인지 저장", pg.input_value('#errIn') == '1' and DB['10101']['g'].get('ok') == [mid] and DB['10101']['g']['e'] == 1)
    check('센 표시는 글 속에서도 진하게', pg.locator('.text .mk.yes').count() == 1)
    pg.click('.text .mk[data-mid]'); pg.wait_for_timeout(1200)
    check('글 속 칠을 다시 누르면 뺌 → 오류 수 0', pg.input_value('#errIn') == '0' and DB['10101']['g'].get('ok') == [])
    pg.click('[data-bulk="all"]'); pg.wait_for_timeout(1200)
    check("'AI 표시 모두 오류로' → 다 세고 오류 수도 그만큼", pg.input_value('#errIn') == '1' and len(DB['10101']['g']['ok']) == 1)
    pg.click('[data-bulk="none"]'); pg.wait_for_timeout(1200)
    check("'모두 빼기' → 0", pg.input_value('#errIn') == '0' and DB['10101']['g']['ok'] == [])
    # AI 가 놓친 곳을 선생님이 글에서 끌어 골라 표시
    pg.evaluate("""() => { const box = document.querySelector('#paper .text'); const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT);
      let t; while ((t = w.nextNode())) { const i = t.nodeValue.indexOf('wheelchairs'); if (i >= 0) { const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + 11);
        const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r); break; } } document.dispatchEvent(new MouseEvent('mouseup')); }""")
    pg.wait_for_timeout(300)
    check('글에서 고르면 오류로 표시 단추가 뜸', pg.is_visible('#selMark'))
    pg.click('#selMark'); pg.wait_for_timeout(1200)
    i0 = GOOD.index('wheelchairs')
    check('선생님 표시가 저장되고 (원래 글 위치), 오류 수 +1, 보라색으로', DB['10101']['g']['ok'] == [f'{i0}-{i0 + 11}'] and pg.input_value('#errIn') == '1' and pg.locator('.text .mk.tch').count() == 1)
    pg.click('.marks li.tch .tg'); pg.wait_for_timeout(1200)
    check("선생님 표시 '빼기' → 0", DB['10101']['g']['ok'] == [] and pg.input_value('#errIn') == '0')
    pg.fill('#errIn', '4'); pg.wait_for_timeout(2500)
    check('오류 4개 → 57점, 서버에 저장', pg.inner_text('#score .total').startswith('57') and any(s.get('e') == '4' and s.get('sid') == '10101' for s in saves), pg.inner_text('#score .total'))

    pg.click('#adjAdd'); pg.fill('#adjRows .row:last-child .r', '발표 우수')
    pg.fill('#adjRows .row:last-child .p', '2'); pg.wait_for_timeout(1200)
    check('가감 +2 → 59점 (사유와 함께 저장)', pg.inner_text('#score .total').startswith('59') and DB['10101']['g']['adj'] == [{"r": "발표 우수", "p": 2}], pg.inner_text('#score .total'))
    pg.click('#adjAdd'); pg.fill('#adjRows .row:last-child .p', '-5'); pg.wait_for_timeout(1200)
    check('사유 없는 가감 줄은 저장 안 함', DB['10101']['g']['adj'] == [{"r": "발표 우수", "p": 2}])
    pg.fill('[data-ov="length"]', '9'); pg.wait_for_timeout(1200)
    check('자동 점수 고치기 (분량 9) → 56', pg.inner_text('#score .total').startswith('56'), pg.inner_text('#score .total'))
    pg.fill('#memoIn', '<script>window.__pwned=3</script>메모'); pg.wait_for_timeout(1200)

    pg.click('button[data-sid="10103"]'); pg.wait_for_timeout(300)
    check('학생 글의 HTML·스크립트가 실행되지 않음', pg.evaluate('window.__pwned') is None and pg.locator('.text img').count() == 0 and '<img' in pg.inner_text('.text'))
    check('이름의 HTML 도 글자로', '<i>박</i>' in pg.inner_text('#paper h2'))
    check('javascript: 같은 이상한 PDF 주소는 링크로 만들지 않음', pg.locator('#paper .meta a').count() == 0)
    pg.fill('#errIn', '0'); pg.keyboard.press('Enter'); pg.wait_for_timeout(1200)
    check('Enter 로 다음 학생', '강도윤' in pg.inner_text('#paper h2'))

    with pg.expect_download() as d:
        pg.click('#btnXlsx')
    data = open(d.value.path(), 'rb').read()
    z = zipfile.ZipFile(io.BytesIO(data))
    wb = z.read('xl/workbook.xml').decode()
    s1 = z.read('xl/worksheets/sheet1.xml').decode()
    check('엑셀: 총괄·101반·102반 시트', all(x in wb for x in ('총괄', '101반', '102반')) and len([n for n in z.namelist() if n.startswith('xl/worksheets/')]) == 3)
    check('엑셀: 총점 56, 가감 사유, 메모(글자 그대로)', '<v>56</v>' in s1 and '발표 우수 +2' in s1 and '&lt;script&gt;' in s1, s1[:300])
    check('엑셀: 아직 오류 수 없는 학생은 입력 필요', '오류 수 입력 필요' in s1)

    with pg.expect_download() as d2:
        pg.click('#btnXlsxCls')
    z2 = zipfile.ZipFile(io.BytesIO(open(d2.value.path(), 'rb').read()))
    check('이 반 엑셀: 지금 반 시트 하나, 그 반 학생만, 파일 이름에 반', d2.value.suggested_filename.startswith('수행평가_채점_101반') and len([n for n in z2.namelist() if n.startswith('xl/worksheets/')]) == 1
          and '101반' in z2.read('xl/workbook.xml').decode() and '최민준' not in z2.read('xl/worksheets/sheet1.xml').decode())
    with ctx.expect_page() as w:
        pg.evaluate('window.print = () => {}')
        pg.click('#btnPrint')
    pw = w.value
    pw.evaluate('window.print = () => {}')
    pw.wait_for_timeout(300)
    body = pw.inner_text('body')
    check('인쇄: 학생마다 한 쪽, 점수표와 가감', pw.locator('section').count() == 4 and '가감: 발표 우수' in body and '56 / 60' in body)
    check('인쇄 창에서도 스크립트가 실행되지 않음', pw.evaluate('window.__pwned') is None and pg.evaluate('window.__pwned') is None)
    br.close()

srv.shutdown()
print('PASS' if all(results) else 'FAIL', f'({sum(results)}/{len(results)})')

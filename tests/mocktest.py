"""
브라우저 자동 테스트. Apps Script를 흉내 내는 가짜 서버를 띄우고 학생 흐름을 끝까지 돌린다.
  실행: python tests/mocktest.py          (처음: pip install -r tests/requirements.txt && python -m playwright install chromium)
  통과 기준: 마지막 줄에 PASS 가 찍히고 errors 가 [] 이어야 한다.
"""
import threading, http.server, socketserver, functools, urllib.parse, json, time, uuid, os, re, sys
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs'))
class Q(socketserver.TCPServer): allow_reuse_address=True
srv = Q(('127.0.0.1', 8880), Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
from playwright.sync_api import sync_playwright
html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'docs', 'index.html'), encoding='utf-8').read()
SCRIPT = re.search(r'scriptUrl:\s*"([^"]+)"', html).group(1)
assert SCRIPT, 'docs/index.html의 CONFIG.submit.scriptUrl이 비어 있습니다'
ORDER={'research':0,'draft':1,'draftDone':2,'final':3,'done':4}
rows=[]   # {sid,name,key,data,phase,at,dup}
posts=[]; finals={}
def find(sid,key): return next((r for r in rows if r['sid']==sid and r['key']==key and key), None)
def mock(route):
    req=route.request; u=urllib.parse.urlparse(req.url); q=urllib.parse.parse_qs(u.query)
    if req.method=='POST':
        b=urllib.parse.parse_qs(req.post_data or ''); g=lambda k: b.get(k,[''])[0]
        r=find(g('sid'),g('key')); posts.append((g('phase'),g('sid'),bool(r),'bank' in b))
        if not r: route.fulfill(status=200, body='UNKNOWN_KEY'); return
        ph=g('phase'); phase='draftDone' if ph=='draft' else ('done' if ph=='final' else json.loads(g('data') or '{}').get('phase',''))
        if ORDER.get(r['phase'],0)<=ORDER.get(phase,0): r.update(data=g('data'),phase=phase,at=time.strftime('%Y-%m-%dT%H:%M:%S'))
        if ph=='final': finals[(g('sid'),g('key')[:6])]=r['at']
        route.fulfill(status=200, body='OK'); return
    cb=q.get('callback',['cb'])[0]; action=q.get('action',[''])[0]; g=lambda k: q.get(k,[''])[0]
    sid,name,key=g('sid'),g('name'),g('key')
    if action=='load':
        r=find(sid,key)
        if r: out={'found':bool(r['data']),'data':r['data'],'key':key,'name':r['name'],'dup':r['dup']}
        else:
            dup=any(x['sid']==sid for x in rows); k=uuid.uuid4().hex[:20]; rows.append({'sid':sid,'name':name,'key':k,'data':None,'phase':'research','at':None,'dup':dup}); out={'found':False,'key':k,'name':name,'dup':dup}
        out['finalOpen']=True; out['finalAt']=finals.get((sid,(out['key'] or '')[:6]))
    elif action=='check': r=find(sid,key); out={'draftAt':r['at'] if r else None,'finalAt':finals.get((sid,key[:6]))}
    elif action=='dict': out={'q':g('q'),'a':'ramp'} if find(sid,key) else {'error':'NO_KEY'}
    else: out={'ok':True}
    route.fulfill(status=200, content_type='application/javascript', body=cb+'('+json.dumps(out)+')')
def new_page(b):
    ctx=b.new_context(viewport={'width':1180,'height':900}); pg=ctx.new_page(); errs=[]; pg.on('pageerror', lambda e: errs.append(str(e))); pg.errs=errs; pg.route(SCRIPT+'*', mock); return ctx,pg
def login(pg,sid,name): pg.goto('http://127.0.0.1:8880/index.html?as=1'); pg.fill('#sid',sid); pg.fill('#name',name); pg.click('#startBtn'); pg.wait_for_timeout(900)
with sync_playwright() as p:
    b=p.chromium.launch()
    ctxA,A=new_page(b); login(A,'10315','김하늘')
    keyA=A.evaluate("localStorage.getItem('czkey:10315')"); print('device A key stored:', bool(keyA), '| phase:', A.inner_text('#phaseLabel'), '| rules mention 15분:', '조사 15분' in A.inner_text('#rules') if not A.eval_on_selector('#gate','e=>e.hidden') else 'n/a')
    A.click('[data-step2="0"]'); A.keyboard.type('학교 도서관'); A.wait_for_timeout(1800)
    print('autosave used key:', [x for x in posts if x[0]=='save'][:1], '| server row data set:', bool(rows[0]['data']))
    # device B (no key) -> separate row + banner
    ctxB,B=new_page(b); login(B,'10315','김하늘')
    print('device B: dup banner:', B.inner_text('#banner')[:22] if not B.eval_on_selector('#banner','e=>e.hidden') else 'none', '| rows:', len(rows), '| B sees A step2?', B.eval_on_selector('[data-step2="0"]','e=>e.value')=='학교 도서관')
    B.click('[data-step2="0"]'); B.keyboard.type('B의 글'); B.wait_for_timeout(1800)
    print('A row intact:', '학교 도서관' in (rows[0]['data'] or ''), '| B row separate:', 'B의 글' in (rows[1]['data'] or ''))
    # A continues: draft → submit (bank sent) → relogin final → dictionary works with key
    A.click('#startDraftBtn'); A.wait_for_selector('#dlg:not([hidden])'); A.click('#dlgActions button:has-text("시작")'); A.wait_for_timeout(500)
    print('draft timer starts at:', A.inner_text('#timer'))
    ta=A.query_selector('[data-part="0"][data-line="0"]'); ta.click(); A.keyboard.type('Many students rely on the library.')
    A.click('#dictTop'); A.fill('#dictQ','경사로'); A.keyboard.press('Enter'); A.wait_for_timeout(400); print('dict with key:', A.inner_text('#dictOut').replace('\n',' '))
    A.click('#submitBtn'); A.click('#modalOk'); A.wait_for_selector('#done:not([hidden])'); A.wait_for_timeout(700)
    print('draft submit posted with bank:', [x for x in posts if x[0]=='draft'][0][3], '| status:', A.inner_text('#doneStatus')[:20])
    login(A,'10315','김하늘'); print('A relogin -> phase:', A.inner_text('#phaseLabel'), '| final timer:', A.inner_text('#timer'))
    print('errors A:', A.errs, '| errors B:', B.errs)
    ok = (not A.errs and not B.errs and A.inner_text('#phaseLabel') == '최종 글쓰기' and len(rows) == 2)
    print('PASS' if ok else 'FAIL')
    b.close()
    if not ok: sys.exit(1)
srv.shutdown()

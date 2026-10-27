"""
AI 표시 도구(tools/ai_marks.py) 테스트 — 가짜 서버·가짜 Claude 만 씀.
  실행: python tests/ai_marks_test.py      통과 기준: 마지막 줄에 PASS
가리기(이름·학번·한글·전화·메일·my name is), 표시 자리 찾기, 새 글만 처리, 올리는 형식을 확인한다.
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools'))
try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception: pass
import ai_marks as am

GOOD = "My name is Minsu Kim. The library is not accessible. 홍길동 helped me. Call 010-1234-5678 or a@b.com. ID 10301."
STUDENTS = [
    {"sid": "10301", "nm": "홍길동", "fn": 100, "final": GOOD, "g": None},
    {"sid": "10302", "nm": "김영희", "fn": 100, "final": "Fine text.", "g": {"marks": [], "mAt": 100}},
    {"sid": "10303", "nm": "박철수", "fn": 300, "final": "Resubmitted text.", "g": {"marks": [], "mAt": 100}},
    {"sid": "10304", "nm": "이민수", "fn": 0, "final": "", "g": None},
]
SENT, POSTS = [], []
def claude(prompt, system):
    SENT.append(prompt)
    return '[{"quote": "is not accessible", "kind": "문법", "fix": "isn\'t", "why": "예"}, {"quote": "○○ helped", "kind": "문법", "fix": "", "why": ""}]'
def ask(method, params):
    if method == "GET": return {"ok": True, "students": STUDENTS}
    POSTS.append(params); return {"ok": True, "n": len(json.loads(params["items"]))}

results = []
def check(label, cond):
    results.append(bool(cond)); print(('  ok  ' if cond else 'FAIL  ') + label)

masked = am.mask_for_claude(GOOD, ["홍길동", "김영희", "10301"])
check('가리기: 한글·영어 이름·전화·메일·학번', all(x not in masked for x in ("홍길동", "Minsu", "Kim", "010-1234-5678", "a@b.com", "10301")) and "is not accessible" in masked)
m = am.parse_marks(claude("", ""), GOOD); SENT.clear()
check('표시는 원래 글에서 찾은 것만, 형식 {s,e,k,q,f,w}', len(m) == 1 and GOOD[m[0]["s"]:m[0]["e"]] == "is not accessible" and set(m[0]) == {"s", "e", "k", "q", "f", "w"})
check('새로 낸 글과 표시 뒤에 다시 낸 글만', [am.needs_marks(s) for s in STUDENTS] == [True, False, True, False])
done = am.run("k" * 30, ask=ask, claude=claude, say=lambda _: None)
items = json.loads(POSTS[0]["items"])
check('2개 표시해 한 번에 올림', done["sent"] == 2 and len(POSTS) == 1 and {i["sid"] for i in items} == {"10301", "10303"})
check('Claude 에 보낸 글에 이름·학번 없음', len(SENT) == 2 and all(x not in p for p in SENT for x in ("홍길동", "박철수", "10301", "10303", "Minsu")))
check('열쇠는 저장소에 없음', "settings.json" in open(am.__file__, encoding="utf-8").read() and not any(len(t) == 40 and t.isalnum() for t in open(am.__file__, encoding="utf-8").read().split('"')))
print('PASS' if all(results) else 'FAIL', f'({sum(results)}/{len(results)})')

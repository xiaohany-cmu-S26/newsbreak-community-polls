"""End-to-end API smoke test against a running backend (any provider; uses a seeded poll, no generation).

  .venv/bin/python -m scripts.smoke_test [http://localhost:8000]"""
import json
import sys
import urllib.error
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")


def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body else None,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def check(name, cond):
    cond = bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}")
    return cond


ok = True
s, h = call("GET", "/api/health")
ok &= check(f"health ({h.get('provider')})", s == 200 and h.get("ok"))

polls = call("GET", "/api/polls")[1]
mv = next((p for p in polls if p["city"] == "mountain view, ca"), None)
ok &= check("seeded Mountain View poll exists (run scripts.seed_demo first)", mv is not None)
if mv:
    pid = mv["poll_id"]
    s, r = call("POST", f"/api/polls/{pid}/vote", {"voter_id": "smoke-outsider", "option_idx": 0, "zip": "15213"})
    ok &= check("vote from outside geo_scope rejected (403)", s == 403)
    s, r = call("POST", f"/api/polls/{pid}/vote", {"voter_id": "smoke-voter", "option_idx": 1, "zip": "94040"})
    ok &= check("vote from inside geo_scope accepted", s == 200 and r["results"]["your_vote"] == 1)
    s, r = call("POST", f"/api/polls/{pid}/vote", {"voter_id": "smoke-voter", "option_idx": 2, "zip": "94040"})
    ok &= check("re-vote replaces rather than double counts", s == 200 and r["results"]["your_vote"] == 2)
    total = r["results"]["total"]
    v = call("GET", f"/api/polls/{pid}?voter_id=smoke-voter&zip=94040")[1]["results"]
    ok &= check("voter sees split iff 30+ votes", v["show_split"] == (total >= 30))
    nv = call("GET", f"/api/polls/{pid}?voter_id=smoke-nobody&zip=94040")[1]["results"]
    ok &= check("non-voter never sees split", nv["show_split"] is False and nv["counts"] is None)
    arts = [a for a in call("POST", "/api/polls/batch", {"article_ids": ["3702094647051", "3606213450231", "nope"]})[1].items()]
    ok &= check("batch lookup returns counts only for seeded articles", len(arts) == 2 and all("counts" not in v for _, v in arts))
    s, r = call("POST", "/api/polls/get-or-create", {"url": "https://www.newsbreak.com/news/3702094647051-copy", "headline": "x",
                                                     "text": "y" * 50, "article_id": "3702094647051", "voter_id": "smoke-voter", "zip": "94040"})
    ok &= check("get-or-create on a seeded article id is a cache hit, no generation", s == 200 and r["cached"] and r["poll"]["poll_id"])
    s, r = call("POST", "/api/polls/get-or-create", {"url": "x", "headline": "h", "text": "short"})
    ok &= check("too-short text rejected (400)", s == 400)
print("\nALL PASS" if ok else "\nSOME CHECKS FAILED")
sys.exit(0 if ok else 1)

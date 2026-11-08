"""get_or_create_poll: cache -> triage -> match -> draft/critic loop -> publish.
Exactly one agent run per article, enforced by a global lock plus DB cache."""
import hashlib
import json
import os
import re
import threading
import uuid

from backend import db
from backend.agent import llm, geo
from backend.agent.critic import critique
from backend.agent.draft import draft_poll
from backend.agent.match import find_match
from backend.agent.triage import triage

MAX_CRITIC_RETRIES = 2   # draft -> critic -> (revise -> critic) x2 at most
_gen_lock = threading.Lock()


def content_hash(headline, text):
    norm = re.sub(r"[^a-z0-9]", "", (headline + text[:2000]).lower())
    return hashlib.sha1(norm.encode()).hexdigest()


def article_id_from_url(url):
    """NewsBreak article URLs look like /news/4894584928434-slug or /<publisher>-1589914/4894584928434-slug.
    The article id is the long digit run that starts the last path segment."""
    path = (url or "").split("?")[0]
    m = re.search(r"/(\d{10,})(?:-|$)", path)
    if m:
        return m.group(1)
    m = re.search(r"(\d{6,})", path)
    if m:
        return m.group(1)
    return hashlib.sha1((url or "").encode()).hexdigest()[:16]


def _noop(_msg):
    pass


def get_or_create_poll(article, log=_noop, force=False):
    """article: {article_id, url, headline, text, city_hint?}. Returns dict with pollable + poll."""
    aid = article["article_id"]
    h = content_hash(article["headline"], article["text"])

    if force:
        db.delete_article(aid, drop_orphan_poll=True)

    cached = db.get_article(aid)
    if cached and cached["pollable"] is not None:
        log(f"cache hit for article {aid} (pollable={bool(cached['pollable'])})")
        return _response(cached, cached_hit=True)

    with _gen_lock:  # serialize generation: one agent run per article, no duplicate polls for one story
        cached = db.get_article(aid)
        if cached and cached["pollable"] is not None:
            return _response(cached, cached_hit=True)

        dup = db.get_article_by_hash(h)
        if dup and dup["article_id"] != aid:
            log(f"content hash matches article {dup['article_id']}; reusing its verdict")
            db.upsert_article(aid, article.get("url"), article["headline"], h, city=dup["city"],
                              pollable=dup["pollable"], triage=json.loads(dup["triage"] or "null"), poll_id=dup["poll_id"])
            if dup["poll_id"]:
                db.add_source_to_poll(dup["poll_id"], article.get("url"))
            return _response(db.get_article(aid), cached_hit=True)

        usage = llm.Usage()
        trace = []

        # 1. triage
        log("triage: asking Haiku whether this is a pending local decision...")
        t = triage(article["headline"], article["text"], usage, city_hint=article.get("city_hint", ""))
        city_k = geo.city_key(t.get("city"), t.get("state")) or geo.city_key(*_split_hint(article.get("city_hint", "")))
        log(f"triage -> pollable={t['pollable']} category={t['category']} city='{city_k}' | {t['reason']}")
        trace.append({"step": "triage", **t})
        if not t["pollable"]:
            db.upsert_article(aid, article.get("url"), article["headline"], h, city=city_k, pollable=0, triage=t)
            return {"article_id": aid, "pollable": False, "triage": t, "poll": None, "cached": False,
                    "trace": trace, "usage": usage.summary()}

        # 2. match against existing polls in the city
        candidates = db.recent_polls_for_city(city_k) if city_k else []
        if candidates:
            log(f"match: comparing against {len(candidates)} existing poll(s) in {city_k}...")
            pid, why = find_match(article["headline"], article["text"], candidates, usage)
            db.log_match(aid, pid, [c["poll_id"] for c in candidates], why)
            trace.append({"step": "match", "matched": pid, "reason": why, "candidates": len(candidates)})
            log(f"match -> {'poll ' + pid if pid else 'none'} | {why}")
            if pid:
                db.upsert_article(aid, article.get("url"), article["headline"], h, city=city_k, pollable=1, triage=t, poll_id=pid)
                db.add_source_to_poll(pid, article.get("url"))
                r = _response(db.get_article(aid), cached_hit=False)
                r["trace"] = trace
                r["usage"] = usage.summary()
                return r

        # 3. draft <-> critic loop
        zips = geo.zips_for(city_k)
        city_label = t.get("city") and f"{t['city']}, {t['state']}".strip(", ") or article.get("city_hint", "")
        draft, research, feedback = None, [], None
        critic_log = []
        passed = False
        for attempt in range(1, MAX_CRITIC_RETRIES + 2):
            log(f"draft (attempt {attempt}): Sonnet researching and drafting...")
            draft, research = draft_poll(article, city_label, zips, usage, log=log,
                                         prev_draft=draft, feedback=feedback, research=research)
            log(f"draft -> Q: {draft['question']}")
            for i, o in enumerate(draft["options"]):
                log(f"          [{i}] {o}")
            log("critic: reviewing draft...")
            verdict = critique(article, draft, research, usage, attempt=attempt)
            critic_log.append({"attempt": attempt, "passed": verdict["passed"], "summary": verdict["summary"],
                               "issues": verdict["issues"], "draft": draft})
            if verdict["passed"]:
                log(f"critic -> PASS ({verdict['summary']})")
                passed = True
                break
            log(f"critic -> FAIL: {len(verdict['issues'])} issue(s)")
            for iss in verdict["issues"]:
                log(f"          - [{iss.get('severity', 'major')}] {iss['type']}: {iss['detail']}")
            feedback = verdict["issues"]
        if not passed:
            # publish the attempt with the fewest major issues rather than blindly the last one
            def n_major(entry):
                return sum(1 for i in entry["issues"] if i.get("severity", "major") == "major")
            best = min(critic_log, key=lambda e: (n_major(e), -e["attempt"]))
            draft = best["draft"]
            log(f"critic never passed; publishing attempt {best['attempt']} ({n_major(best)} major issue(s)) flagged critic_passed=false")

        # 4. publish
        poll_id = uuid.uuid4().hex[:12]
        options = [o.strip() for o in draft["options"] if o.strip()][:4]
        scope = geo.normalize_zips(draft.get("geo_scope"))
        if zips:
            scope = [z for z in scope if z in zips] or zips
        poll = {
            "poll_id": poll_id, "city": city_k, "question": draft["question"].strip(), "options": options,
            "context": draft["context"], "geo_scope": scope, "decision_date": draft.get("decision_date", ""),
            "sources": list(dict.fromkeys([s for s in ([article.get("url")] + draft.get("sources", [])) if s])),
            "critic_passes": len(critic_log), "critic_passed": passed, "critic_log": critic_log,
            "usage": usage.summary(),
        }
        db.create_poll(poll)
        db.upsert_article(aid, article.get("url"), article["headline"], h, city=city_k, pollable=1, triage=t, poll_id=poll_id)
        log(f"published poll {poll_id}  (cost ${usage.summary()['cost_usd']}, {usage.summary()['n_calls']} calls)")
        if os.getenv("DEMO_SIM_VOTES", "0") == "1":
            from scripts.seed_demo import sim_votes_for_all
            sim_votes_for_all()
            log("DEMO_SIM_VOTES=1: populated simulated votes for the new poll")
        r = _response(db.get_article(aid), cached_hit=False)
        r["trace"] = trace
        r["usage"] = usage.summary()
        return r


def _split_hint(hint):
    if "," in (hint or ""):
        c, s = hint.split(",", 1)
        return c.strip(), s.strip()
    return hint or "", ""


def _response(article_row, cached_hit):
    triage_d = json.loads(article_row["triage"]) if article_row.get("triage") else None
    poll = db.get_poll(article_row["poll_id"]) if article_row.get("poll_id") else None
    return {"article_id": article_row["article_id"], "pollable": bool(article_row["pollable"]),
            "triage": triage_d, "poll": poll, "cached": cached_hit}

"""FastAPI backend for NewsBreak community polls.
Run: .venv/bin/uvicorn backend.main:app --reload --port 8000"""
import logging
from typing import Optional

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import db
from backend.agent import llm
from backend.agent.pipeline import get_or_create_poll, article_id_from_url

MIN_VOTES_TO_SHOW = 30

log = logging.getLogger("polls")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

app = FastAPI(title="NewsBreak Community Polls")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ArticleIn(BaseModel):
    url: str
    headline: str
    text: str
    article_id: Optional[str] = None
    city_hint: Optional[str] = ""
    voter_id: Optional[str] = ""
    zip: Optional[str] = ""


class BatchIn(BaseModel):
    article_ids: list[str]


class VoteIn(BaseModel):
    voter_id: str
    option_idx: int
    zip: str


def results_view(poll, voter_id, eligible=True):
    """Split is hidden until 30 votes exist AND the viewer has voted or cannot vote here (non-residents can't be anchored)."""
    counts = db.vote_counts(poll["poll_id"], len(poll["options"]))
    total = sum(counts)
    your_vote = db.get_vote(poll["poll_id"], voter_id) if voter_id else None
    enough = total >= MIN_VOTES_TO_SHOW
    show = enough and (your_vote is not None or not eligible)
    if show:
        status = "shown"
    elif not enough:
        status = "early"
    else:
        status = "vote_to_see"
    return {"total": total, "your_vote": your_vote, "show_split": show,
            "counts": counts if show else None, "min_votes": MIN_VOTES_TO_SHOW, "status": status}


def public_poll(poll, voter_id="", zip_code=""):
    scope = poll["geo_scope"]
    eligible = (not scope) or (zip_code in scope)
    return {
        "poll_id": poll["poll_id"], "city": poll.get("city") or "", "question": poll["question"], "options": poll["options"],
        "context": poll["context"], "geo_scope": scope, "decision_date": poll["decision_date"],
        "sources": poll["sources"], "critic_passes": poll["critic_passes"], "critic_passed": poll["critic_passed"],
        "critic_log": [{"attempt": c["attempt"], "passed": c["passed"], "summary": c["summary"],
                        "issues": c["issues"]} for c in poll["critic_log"]],
        "eligible": eligible, "results": results_view(poll, voter_id, eligible),
    }


@app.get("/api/health")
def health():
    return {"ok": True, "provider": llm.PROVIDER, "mock": llm.MOCK, "models": {"triage": llm.TRIAGE_MODEL, "draft": llm.DRAFT_MODEL}}


@app.post("/api/polls/get-or-create")
def get_or_create(a: ArticleIn):
    aid = a.article_id or article_id_from_url(a.url)
    if len(a.text.strip()) < 40:
        raise HTTPException(400, "article text too short to evaluate")
    r = get_or_create_poll({"article_id": aid, "url": a.url, "headline": a.headline.strip(),
                            "text": a.text, "city_hint": a.city_hint or ""}, log=log.info)
    out = {"article_id": r["article_id"], "pollable": r["pollable"], "cached": r["cached"],
           "triage": r.get("triage"), "poll": None}
    if r["poll"]:
        out["poll"] = public_poll(r["poll"], a.voter_id or "", a.zip or "")
    return out


@app.post("/api/polls/batch")
def batch(b: BatchIn):
    out = {}
    poll_ids = {}
    for aid in b.article_ids[:100]:
        row = db.get_article(aid)
        if row and row["pollable"] and row["poll_id"]:
            poll_ids[aid] = row["poll_id"]
    totals = db.vote_totals(list(set(poll_ids.values())))
    for aid, pid in poll_ids.items():
        out[aid] = {"poll_id": pid, "total": totals.get(pid, 0)}
    return out


@app.get("/api/polls/{poll_id}")
def get_poll(poll_id: str, voter_id: str = "", zip: str = ""):
    poll = db.get_poll(poll_id)
    if not poll:
        raise HTTPException(404, "no such poll")
    return public_poll(poll, voter_id, zip)


@app.post("/api/polls/{poll_id}/vote")
def vote(poll_id: str, v: VoteIn):
    poll = db.get_poll(poll_id)
    if not poll:
        raise HTTPException(404, "no such poll")
    if not (0 <= v.option_idx < len(poll["options"])):
        raise HTTPException(400, "bad option")
    if poll["geo_scope"] and v.zip not in poll["geo_scope"]:
        raise HTTPException(403, f"ZIP {v.zip} is outside this poll's area")
    if not v.voter_id:
        raise HTTPException(400, "voter_id required")
    db.record_vote(poll_id, v.voter_id, v.option_idx, v.zip)
    return {"ok": True, "results": results_view(poll, v.voter_id)}


@app.get("/api/polls")
def list_polls(city: str = ""):
    polls = db.list_polls(city or None)
    totals = db.vote_totals([p["poll_id"] for p in polls])
    return [{"poll_id": p["poll_id"], "city": p["city"], "question": p["question"], "options": p["options"],
             "total": totals.get(p["poll_id"], 0), "critic_passes": p["critic_passes"],
             "critic_passed": p["critic_passed"]} for p in polls]


# ---------- admin dashboard (operator view: shows splits regardless of gating; no auth, demo only) ----------

@app.get("/api/admin/polls")
def admin_polls():
    polls = db.list_polls(limit=500)
    out = []
    total_votes = 0
    for p in polls:
        counts = db.vote_counts(p["poll_id"], len(p["options"]))
        total = sum(counts)
        total_votes += total
        usage = p.get("usage") or {}
        origin = "seeded" if "hand-seeded" in str(usage.get("note", "")) else "agent"
        out.append({
            "poll_id": p["poll_id"], "city": p["city"], "question": p["question"], "options": p["options"],
            "counts": counts, "total": total, "geo_scope": p["geo_scope"], "decision_date": p["decision_date"],
            "critic_passes": p["critic_passes"], "critic_passed": p["critic_passed"],
            "critic_issues": [i for c in p["critic_log"] for i in c.get("issues", [])],
            "sources": p["sources"], "created_at": p["created_at"], "origin": origin,
            "cost_usd": usage.get("cost_usd", 0), "n_calls": usage.get("n_calls", 0),
            "articles": db.articles_for_poll(p["poll_id"]),
            "by_zip": db.vote_counts_by_zip(p["poll_id"], len(p["options"])),
        })
    declined = []
    for a in db.declined_articles():
        t = json.loads(a["triage"]) if a.get("triage") else {}
        declined.append({"article_id": a["article_id"], "url": a["url"], "headline": a["headline"], "city": a["city"],
                         "category": t.get("category", ""), "reason": t.get("reason", ""), "created_at": a["created_at"]})
    recent = []
    for v in db.recent_votes(20):
        opts = json.loads(v["options"]) if isinstance(v["options"], str) else v["options"]
        recent.append({"poll_id": v["poll_id"], "question": v["question"], "option": opts[v["option_idx"]] if 0 <= v["option_idx"] < len(opts) else "?",
                       "zip": v["zip"], "created_at": v["created_at"], "simulated": str(v["voter_id"]).startswith("seed-")})
    return {"provider": llm.PROVIDER, "models": {"triage": llm.TRIAGE_MODEL, "draft": llm.DRAFT_MODEL},
            "stats": {"polls": len(polls), "votes": total_votes, "declined": len(declined),
                      "agent_polls": sum(1 for p in out if p["origin"] == "agent")},
            "polls": out, "declined": declined, "recent_votes": recent}


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    path = os.path.join(os.path.dirname(__file__), "admin.html")
    return HTMLResponse(open(path, encoding="utf-8").read())

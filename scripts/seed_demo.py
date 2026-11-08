"""Seed the database for the demo.

  .venv/bin/python -m scripts.seed_demo            # load hand-written polls from scripts/seed_polls.json + realistic votes
  .venv/bin/python -m scripts.seed_demo --reset    # wipe the DB first
  .venv/bin/python -m scripts.seed_demo --sim-votes # give every poll that has no votes a simulated, realistic vote set
  .venv/bin/python -m scripts.seed_demo --forget-real-votes # delete real (non-simulated) votes so you can vote again on camera
With an API key set, opening any un-seeded article once in the extension generates and caches its poll live.

Seeded polls are keyed by real NewsBreak article ids, so opening those articles with the extension shows them instantly."""
import argparse
import json
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from backend import db  # noqa: E402
from backend.agent.pipeline import content_hash  # noqa: E402

SEED_FILE = os.path.join(ROOT, "scripts", "seed_polls.json")


def seed_votes(poll_id, geo_scope, total, weights, rng):
    """Deterministic, realistic vote distribution. weights = relative share per option."""
    n = len(weights)
    s = sum(weights)
    for i in range(total):
        r = rng.random() * s
        acc = 0
        idx = n - 1
        for j, w in enumerate(weights):
            acc += w
            if r < acc:
                idx = j
                break
        db.record_vote(poll_id, f"seed-{poll_id}-{i:04d}", idx, rng.choice(geo_scope))


def forget_real_votes():
    """Delete votes cast by real voters (extension / smoke test); simulated seed votes stay."""
    with db._lock, db.connect() as c:
        n = c.execute("DELETE FROM votes WHERE voter_id NOT LIKE 'seed-%'").rowcount
    print(f"deleted {n} real vote(s); simulated votes kept")


def sim_votes_for_all(rng=None):
    """Simulated votes for every poll with no votes yet (e.g. polls the agent generated on this machine)."""
    rng = rng or random.Random()
    n = 0
    for p in db.list_polls(limit=1000):
        if sum(db.vote_counts(p["poll_id"], len(p["options"]))) > 0:
            continue
        total = rng.choice([34, 41, 58, 77, 96, 128, 163, 214, 289])
        k = len(p["options"])
        # skewed but not lopsided: a leader, a runner-up, the rest small; "not sure" style last option stays small
        weights = [rng.uniform(1.0, 3.0) for _ in range(k)]
        weights[rng.randrange(k)] *= 2.2
        if k >= 3:
            weights[-1] *= 0.4
        seed_votes(p["poll_id"], p["geo_scope"] or ["00000"], total, weights, rng)
        n += 1
        print(f"simulated {total} votes for {p['poll_id']}: {p['question'][:60]}...")
    print(f"done: {n} poll(s) populated")


def load_seeds(reset):
    if reset and os.path.exists(db.DB_PATH):
        os.remove(db.DB_PATH)
        db.init_db()
    seeds = json.load(open(SEED_FILE))
    rng = random.Random(42)
    for s in seeds:
        p = s["poll"]
        poll_id = s["poll_id"]
        if db.get_poll(poll_id):
            print(f"skip {poll_id} (exists)")
            continue
        db.create_poll({
            "poll_id": poll_id, "city": s["city"], "question": p["question"], "options": p["options"],
            "context": p["context"], "geo_scope": p["geo_scope"], "decision_date": p.get("decision_date", ""),
            "sources": p.get("sources", []), "critic_passes": p.get("critic_passes", 1),
            "critic_passed": p.get("critic_passed", True), "critic_log": p.get("critic_log", []),
            "usage": p.get("usage", {"note": "hand-seeded for demo"}),
        })
        for art in s["articles"]:
            db.upsert_article(art["article_id"], art["url"], art["headline"], content_hash(art["headline"], art.get("text", "")),
                              city=s["city"], pollable=1, triage=art.get("triage", {"pollable": True, "category": s.get("category", "other_local_decision"),
                                                                                       "reason": "seeded", "city": "", "state": "", "decision_body": ""}),
                              poll_id=poll_id)
        v = s.get("votes", {})
        seed_votes(poll_id, p["geo_scope"], v.get("total", 0), v.get("weights", [1] * len(p["options"])), rng)
        print(f"seeded {poll_id}: {p['question'][:70]}...  ({v.get('total', 0)} votes, {len(s['articles'])} article(s))")
    declined = os.path.join(ROOT, "scripts", "seed_declined.json")
    if os.path.exists(declined):
        for a in json.load(open(declined)):
            db.upsert_article(a["article_id"], a["url"], a["headline"], content_hash(a["headline"], ""), city=a.get("city", ""),
                              pollable=0, triage=a["triage"])
            print(f"seeded declined: {a['headline'][:70]}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--sim-votes", action="store_true", help="populate simulated votes for every poll that has none")
    ap.add_argument("--forget-real-votes", action="store_true", help="delete non-simulated votes so you can vote again")
    a = ap.parse_args()
    if a.forget_real_votes:
        forget_real_votes()
    elif a.sim_votes:
        sim_votes_for_all()
    else:
        load_seeds(a.reset)

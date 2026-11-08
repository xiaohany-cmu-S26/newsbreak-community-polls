"""SQLite storage: articles, polls, votes, match log. Hackathon-grade, stdlib only."""
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

DB_PATH = os.environ.get("POLLS_DB", os.path.join(os.path.dirname(__file__), "data", "polls.db"))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
  article_id    TEXT PRIMARY KEY,
  url           TEXT,
  headline      TEXT,
  content_hash  TEXT,
  city          TEXT,
  pollable      INTEGER,          -- NULL = not triaged yet
  triage        TEXT,             -- JSON from triage step
  poll_id       TEXT,
  created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_articles_hash ON articles(content_hash);

CREATE TABLE IF NOT EXISTS polls (
  poll_id        TEXT PRIMARY KEY,
  city           TEXT,
  question       TEXT,
  options        TEXT,   -- JSON list
  context        TEXT,   -- JSON {for, against}
  geo_scope      TEXT,   -- JSON list of ZIPs
  decision_date  TEXT,
  sources        TEXT,   -- JSON list
  critic_passes  INTEGER,
  critic_passed  INTEGER,
  critic_log     TEXT,   -- JSON list
  usage          TEXT,   -- JSON token usage + cost
  created_at     TEXT
);

CREATE TABLE IF NOT EXISTS votes (
  poll_id     TEXT,
  voter_id    TEXT,
  option_idx  INTEGER,
  zip         TEXT,
  created_at  TEXT,
  PRIMARY KEY (poll_id, voter_id)
);

CREATE TABLE IF NOT EXISTS match_log (
  article_id       TEXT,
  matched_poll_id  TEXT,
  candidates       TEXT,  -- JSON list of poll_ids considered
  reason           TEXT,
  created_at       TEXT
);
"""


def now():
    return datetime.now(timezone.utc).isoformat()


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with connect() as c:
        c.executescript(SCHEMA)


def _row(r):
    return dict(r) if r is not None else None


# ---------- articles ----------

def get_article(article_id):
    with connect() as c:
        return _row(c.execute("SELECT * FROM articles WHERE article_id=?", (article_id,)).fetchone())


def get_article_by_hash(content_hash):
    with connect() as c:
        return _row(c.execute(
            "SELECT * FROM articles WHERE content_hash=? AND pollable IS NOT NULL ORDER BY created_at LIMIT 1",
            (content_hash,)).fetchone())


def upsert_article(article_id, url, headline, content_hash, city=None, pollable=None, triage=None, poll_id=None):
    with _lock, connect() as c:
        c.execute("""
            INSERT INTO articles(article_id,url,headline,content_hash,city,pollable,triage,poll_id,created_at)
            VALUES(?,?,?,?,?,?,?,?,?)
            ON CONFLICT(article_id) DO UPDATE SET
              url=excluded.url, headline=excluded.headline, content_hash=excluded.content_hash,
              city=COALESCE(excluded.city, articles.city),
              pollable=COALESCE(excluded.pollable, articles.pollable),
              triage=COALESCE(excluded.triage, articles.triage),
              poll_id=COALESCE(excluded.poll_id, articles.poll_id)
        """, (article_id, url, headline, content_hash, city,
              pollable, json.dumps(triage) if triage is not None else None, poll_id, now()))


def delete_article(article_id, drop_orphan_poll=False):
    """Delete an article row; optionally also its poll (and votes) when no other article links to that poll."""
    with _lock, connect() as c:
        r = c.execute("SELECT poll_id FROM articles WHERE article_id=?", (article_id,)).fetchone()
        c.execute("DELETE FROM articles WHERE article_id=?", (article_id,))
        if drop_orphan_poll and r and r["poll_id"]:
            n = c.execute("SELECT COUNT(*) FROM articles WHERE poll_id=?", (r["poll_id"],)).fetchone()[0]
            if n == 0:
                c.execute("DELETE FROM votes WHERE poll_id=?", (r["poll_id"],))
                c.execute("DELETE FROM polls WHERE poll_id=?", (r["poll_id"],))


def search_articles(query, city=None, limit=5):
    """Crude keyword search over stored headlines (stub for a real search tool)."""
    words = [w for w in query.lower().split() if len(w) > 3][:6]
    if not words:
        return []
    clauses = " OR ".join(["lower(headline) LIKE ?"] * len(words))
    params = [f"%{w}%" for w in words]
    sql = f"SELECT article_id,url,headline,city FROM articles WHERE ({clauses})"
    if city:
        sql += " AND lower(city)=?"
        params.append(city.lower())
    sql += " LIMIT ?"
    params.append(limit)
    with connect() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


# ---------- polls ----------

def create_poll(poll):
    with _lock, connect() as c:
        c.execute("""
            INSERT INTO polls(poll_id,city,question,options,context,geo_scope,decision_date,sources,
                              critic_passes,critic_passed,critic_log,usage,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (poll["poll_id"], poll.get("city"), poll["question"], json.dumps(poll["options"]),
              json.dumps(poll["context"]), json.dumps(poll["geo_scope"]), poll.get("decision_date") or "",
              json.dumps(poll.get("sources", [])), poll.get("critic_passes", 0),
              1 if poll.get("critic_passed") else 0, json.dumps(poll.get("critic_log", [])),
              json.dumps(poll.get("usage", {})), now()))


def _poll_from_row(r):
    if r is None:
        return None
    d = dict(r)
    for k in ("options", "context", "geo_scope", "sources", "critic_log", "usage"):
        d[k] = json.loads(d[k]) if d.get(k) else ([] if k != "context" and k != "usage" else {})
    d["critic_passed"] = bool(d.get("critic_passed"))
    return d


def get_poll(poll_id):
    with connect() as c:
        return _poll_from_row(c.execute("SELECT * FROM polls WHERE poll_id=?", (poll_id,)).fetchone())


def list_polls(city=None, limit=50):
    with connect() as c:
        if city:
            rows = c.execute("SELECT * FROM polls WHERE lower(city)=? ORDER BY created_at DESC LIMIT ?",
                             (city.lower(), limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM polls ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [_poll_from_row(r) for r in rows]


def recent_polls_for_city(city, days=30, limit=20):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    with connect() as c:
        rows = c.execute(
            "SELECT * FROM polls WHERE lower(city)=? AND created_at>=? ORDER BY created_at DESC LIMIT ?",
            ((city or "").lower(), cutoff, limit)).fetchall()
        return [_poll_from_row(r) for r in rows]


def add_source_to_poll(poll_id, url):
    if not url:
        return
    with _lock, connect() as c:
        r = c.execute("SELECT sources FROM polls WHERE poll_id=?", (poll_id,)).fetchone()
        if r is None:
            return
        sources = json.loads(r["sources"] or "[]")
        if url not in sources:
            sources.append(url)
            c.execute("UPDATE polls SET sources=? WHERE poll_id=?", (json.dumps(sources), poll_id))


def log_match(article_id, matched_poll_id, candidates, reason):
    with _lock, connect() as c:
        c.execute("INSERT INTO match_log VALUES(?,?,?,?,?)",
                  (article_id, matched_poll_id or "", json.dumps(candidates), reason, now()))


# ---------- votes ----------

def record_vote(poll_id, voter_id, option_idx, zip_code):
    with _lock, connect() as c:
        c.execute("INSERT OR REPLACE INTO votes(poll_id,voter_id,option_idx,zip,created_at) VALUES(?,?,?,?,?)",
                  (poll_id, voter_id, option_idx, zip_code, now()))


def get_vote(poll_id, voter_id):
    with connect() as c:
        r = c.execute("SELECT option_idx FROM votes WHERE poll_id=? AND voter_id=?", (poll_id, voter_id)).fetchone()
        return r["option_idx"] if r else None


def vote_counts(poll_id, n_options):
    counts = [0] * n_options
    with connect() as c:
        for r in c.execute("SELECT option_idx, COUNT(*) AS n FROM votes WHERE poll_id=? GROUP BY option_idx",
                           (poll_id,)):
            if 0 <= r["option_idx"] < n_options:
                counts[r["option_idx"]] = r["n"]
    return counts


def vote_counts_by_zip(poll_id, n_options):
    """{zip: [counts per option]} for weighted results."""
    out = {}
    with connect() as c:
        for r in c.execute("SELECT zip, option_idx, COUNT(*) AS n FROM votes WHERE poll_id=? GROUP BY zip, option_idx",
                           (poll_id,)):
            arr = out.setdefault(r["zip"], [0] * n_options)
            if 0 <= r["option_idx"] < n_options:
                arr[r["option_idx"]] = r["n"]
    return out


def vote_totals(poll_ids):
    if not poll_ids:
        return {}
    q = ",".join("?" * len(poll_ids))
    with connect() as c:
        return {r["poll_id"]: r["n"] for r in
                c.execute(f"SELECT poll_id, COUNT(*) AS n FROM votes WHERE poll_id IN ({q}) GROUP BY poll_id", poll_ids)}


init_db()


# ---------- admin views ----------

def articles_for_poll(poll_id):
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT article_id, url, headline, created_at FROM articles WHERE poll_id=? ORDER BY created_at", (poll_id,))]


def declined_articles(limit=200):
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT article_id, url, headline, city, triage, created_at FROM articles WHERE pollable=0 ORDER BY created_at DESC LIMIT ?",
            (limit,))]


def recent_votes(limit=15):
    with connect() as c:
        return [dict(r) for r in c.execute(
            "SELECT v.poll_id, v.option_idx, v.zip, v.created_at, v.voter_id, p.question, p.options "
            "FROM votes v JOIN polls p ON p.poll_id=v.poll_id ORDER BY v.created_at DESC LIMIT ?", (limit,))]

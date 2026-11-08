"""Step 2b: does this article describe the same decision as an existing poll? (Haiku)"""
from backend.agent import llm

import re

SYSTEM = """You decide whether a new local news article is about the same underlying pending decision as one of the existing polls. "Same decision" means a resident voting on the existing poll would be answering the question the new article raises: same proposal, same decision body, same locality. Different phases of one proposal (study session vs. final vote) still count as the same decision. Different proposals on the same topic (two different housing projects) do not. Set is_same_decision to true and match_poll_id to that poll's id ONLY when there is a genuine match; otherwise set is_same_decision to false and match_poll_id to "". Most articles do not match any existing poll. Respond with JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "is_same_decision": {"type": "boolean"},
        "match_poll_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["is_same_decision", "match_poll_id", "reason"],
    "additionalProperties": False,
}

_GENERIC = {"mountain", "council", "should", "approve", "proposal", "proposed", "residents", "district", "school",
            "board", "which", "would", "could", "about", "their", "after", "plans", "local", "commission", "county",
            "city", "decision", "vote", "votes", "meeting", "public", "state", "california"}


def _keywords(text):
    return set(re.findall(r"[a-z]{5,}", (text or "").lower())) - _GENERIC


def find_match(headline, text, candidates, usage):
    if not candidates:
        return "", "no candidate polls in this city"
    if llm.MOCK:
        from backend.agent import mock
        return mock.find_match(headline, candidates)
    cand = "\n".join(f"- poll_id={p['poll_id']}: {p['question']} | options: {' / '.join(p['options'])}" for p in candidates)
    user = f"NEW ARTICLE HEADLINE: {headline}\n\nNEW ARTICLE (excerpt):\n{text[:2500]}\n\nEXISTING POLLS:\n{cand}"
    out = llm.structured(llm.TRIAGE_MODEL, "match", SYSTEM, user, SCHEMA, usage, max_tokens=300)
    by_id = {p["poll_id"]: p for p in candidates}
    pid = out.get("match_poll_id", "")
    reason = out.get("reason", "")
    if not out.get("is_same_decision") or pid not in by_id:
        return "", reason
    # Sanity guard for small models: a genuine match shares at least one specific keyword with the poll question.
    shared = _keywords(headline + " " + text[:400]) & _keywords(by_id[pid]["question"])
    if not shared:
        return "", f"model proposed {pid} but no specific keyword overlap; rejected. ({reason})"
    return pid, reason

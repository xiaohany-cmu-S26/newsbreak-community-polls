"""Step 4: independent fairness review of the draft (Sonnet, single structured call)."""
import json

from backend.agent import llm

SYSTEM = """You are a fairness reviewer for community polls attached to local news articles. You receive the SUPPORTING MATERIAL (part 1: the news article itself; part 2: research results from tools) and the draft poll. Anything stated in the article OR in the research results counts as supported. Find the problems a careful, skeptical editor would flag. A poll that fails goes back for revision; a poll that passes is shown to thousands of residents, so be careful in both directions: do not invent problems.

Check for:
1. loaded_wording: words in the question or options that signal which answer is right ("controversial", "much-needed", "reckless", "finally", "only"), presuppositions, or framing that presumes the outcome.
2. missing_option: a position the article or research shows real people holding that has no option; a binary question on an issue the material shows is not binary; or no way to express uncertainty on a complex issue.
3. unsupported_claim: a statement in context.for, context.against, or the question that appears in NEITHER the article NOR the research results. Numbers, dates, names and motives are the usual offenders. A figure that appears in the article is supported, full stop.
4. leading_order: option order, length or tone asymmetry that nudges toward an answer (the favored option first and longest, the opposing option phrased as a strawman).
5. scope_error: geo_scope inconsistent with who the decision affects, or decision_date not supported by the material.
6. other: anything else a reasonable reader would see as unfair, including for/against summaries of clearly unequal strength or length.

Rate each issue's severity: "major" if a reasonable resident would see the poll as unfair or misleading because of it (a loaded question, a missing side of the debate, a false number); "minor" if it is a polish item. Do NOT flag as issues: city-wide ZIP scope for a decision made by a city body (ZIP codes are coarse and the whole city votes for the council); attributed summaries like "supporters say" or "business owners argue" when the article reports those positions; the conventional order yes / conditional yes / no / not sure; plain option phrasings such as "Yes, approve as proposed", "Support the project as proposed", "No, do not approve", "Delay or reconsider" (these are neutral labels for positions, not endorsements). Pass unless there is at least one major issue. For every issue give a concrete suggested_fix. Respond with JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "passed": {"type": "boolean"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": ["loaded_wording", "missing_option", "unsupported_claim",
                                                        "leading_order", "scope_error", "other"]},
                    "severity": {"type": "string", "enum": ["major", "minor"]},
                    "detail": {"type": "string"},
                    "suggested_fix": {"type": "string"},
                },
                "required": ["type", "severity", "detail", "suggested_fix"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["passed", "issues", "summary"],
    "additionalProperties": False,
}


def critique(article, draft, research, usage, attempt=1):
    if llm.MOCK:
        from backend.agent import mock
        return mock.critique(draft, attempt)
    research_txt = json.dumps(research, indent=1)[:6000] if research else "(none)"
    user = (f"SUPPORTING MATERIAL, PART 1 - THE ARTICLE\nHEADLINE: {article['headline']}\n\n{article['text'][:9000]}\n\n"
            f"SUPPORTING MATERIAL, PART 2 - RESEARCH RESULTS FROM TOOLS:\n{research_txt}\n\n"
            f"DRAFT POLL TO REVIEW:\n{json.dumps(draft, indent=1)}")
    out = llm.structured(llm.DRAFT_MODEL, "critic", SYSTEM, user, SCHEMA, usage, max_tokens=6000, effort="medium")
    # Deterministic guard: an "unsupported" figure that literally appears in the article is supported.
    import re
    haystack = (article["headline"] + " " + article["text"]).lower()
    for iss in out.get("issues", []):
        if iss.get("type") == "unsupported_claim" and iss.get("severity", "major") == "major":
            nums = re.findall(r"\$?\d[\d,]*(?:\.\d+)?%?", iss.get("detail", ""))
            nums = [n.strip("$%") for n in nums]
            if nums and all(n in haystack for n in nums):
                iss["severity"] = "minor"
                iss["detail"] += " [auto-check: every figure cited here appears in the article; downgraded to minor]"
    # Enforce the pass rule in code so a strict small model cannot fail a draft on minor items alone.
    majors = [i for i in out.get("issues", []) if i.get("severity", "major") == "major"]
    out["passed"] = bool(out.get("passed")) or not majors
    if majors:
        out["passed"] = False
    return out

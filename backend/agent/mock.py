"""Canned responses so the whole pipeline (and the extension) can be exercised with MOCK_LLM=1."""
import re

_CRIME = re.compile(
    r"\b(shooting|shot|stabb|crash|killed|dies|died|dead|death|arrest|robber|robbed|burglar|handgun|"
    r"suspect|police say|murder|homicide|obituar|funeral|fire crews|wildfire|earthquake|touchdown|playoff|"
    r"concert|grand opening)", re.I)
_DECISION = re.compile(
    r"\b(council|board|commission|vote|voted|voting|decide|decision|proposal|proposed|plan|budget|ordinance|"
    r"zoning|hearing|measure|ballot|approve|approval|district|permit|policy)", re.I)


def triage(headline, text, city_hint=""):
    crime = 3 * len(_CRIME.findall(headline)) + len(_CRIME.findall(text[:2000]))
    decision = 3 * len(_DECISION.findall(headline)) + len(_DECISION.findall(text[:2000]))
    if crime > 0 and crime >= decision:
        return {"pollable": False, "category": "crime_accident_tragedy",
                "reason": "MOCK: matched a crime/tragedy/entertainment keyword.",
                "city": "Mountain View", "state": "CA", "decision_body": ""}
    city, state = "Mountain View", "CA"
    if "," in (city_hint or ""):
        city, state = [s.strip() for s in city_hint.split(",", 1)]
    return {"pollable": True, "category": "other_local_decision",
            "reason": "MOCK: no exclusion keyword found; treating as a pending local decision.",
            "city": city, "state": state, "decision_body": "City Council"}


_GENERIC = {"mountain", "council", "should", "approve", "proposal", "proposed", "residents", "district", "school",
            "board", "which", "would", "could", "about", "their", "after", "plans", "local", "commission", "county"}


def find_match(headline, candidates):
    h = set(re.findall(r"[a-z]{5,}", headline.lower())) - _GENERIC  # returns (poll_id, reason)
    for p in candidates:
        q = set(re.findall(r"[a-z]{5,}", p["question"].lower())) - _GENERIC
        if len(h & q) >= 3:
            return p["poll_id"], f"MOCK: shared specific keywords {sorted(h & q)[:4]} with existing poll"
    return "", "MOCK: no specific keyword overlap"


def draft(article, city_label, zips, prev_draft, feedback, research, log):
    from backend.agent.tools import run_tool
    topic = article["headline"].rstrip(".")
    if not research:
        for name, args in (("fetch_agenda_item", {"query": topic, "city": city_label}),
                           ("search_related_articles", {"query": topic, "city": city_label})):
            out = run_tool(name, args)
            research.append({"tool": name, "args": args, "result": out})
            log(f"   tool {name}(...) -> found={out.get('found', len(out.get('results', [])))}")
    agenda = next((r["result"] for r in research if r["tool"] == "fetch_agenda_item" and r["result"].get("found")), None)
    revised = bool(feedback)
    verb = "approve" if not revised else "approve"
    loaded = "" if revised else "finally "
    q = (f"Should the {agenda['body']} {loaded}approve the proposal described as \"{agenda['title']}\"?" if agenda
         else f"Should the city {loaded}move forward with the proposal described in \"{topic}\"?")
    return {
        "question": q,
        "options": ["Yes, approve as proposed", "Yes, but with changes", "No, do not approve", "Not sure / need more information"],
        "context": {
            "for": "MOCK: Supporters say the proposal addresses a documented need described in the article.",
            "against": "MOCK: Opponents say the costs and side effects described in the article outweigh the benefits.",
        },
        "geo_scope": zips or ["94040", "94041", "94043"],
        "decision_date": agenda["decision_date"] if agenda else "",
        "sources": [article.get("url") or "pasted-article"] + ([agenda["source_url"]] if agenda else []),
        "notes": "MOCK draft" + (" (revised after critic feedback)" if revised else ""),
    }, research


def critique(draft, attempt):
    if attempt == 1 and "finally" in draft["question"]:
        return {"passed": False, "summary": "MOCK: loaded wording in question.",
                "issues": [{"type": "loaded_wording", "severity": "major",
                            "detail": "The word 'finally' implies the decision is overdue and favors approval.",
                            "suggested_fix": "Remove 'finally'."}]}
    return {"passed": True, "summary": "MOCK: no issues found.", "issues": []}

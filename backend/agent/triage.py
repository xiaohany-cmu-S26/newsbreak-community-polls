"""Step 1: cheap triage with Haiku. Is this article about a pending local decision?"""
from backend.agent import llm

SYSTEM = """You screen local news articles to decide whether a community poll about a pending local decision makes sense.

pollable = true only when the article is about a specific decision that has NOT been finally made, or a live community question, that residents of a specific US locality could reasonably weigh in on: zoning and development approvals, housing policy, city/county/school budgets and taxes, school district policy, transit and road projects, parks and environmental rules, local ordinances, ballot measures, and similar. There must be an identifiable decision body (council, board, commission, district, voters) or an open question the community is actively debating.

pollable = false for: crime, arrests, court cases, accidents, fires, deaths, obituaries, disasters and weather, sports results, entertainment, business openings/closings and promotions, human-interest stories, national or international news with no local decision attached, and decisions that are already final with no open follow-up. When in doubt, say false: a poll on a tragedy is worse than a missed poll.

Also extract the locality (city and 2-letter state) and the decision body, using "" when unknown. Give a one-sentence reason. Respond with JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "pollable": {"type": "boolean"},
        "category": {"type": "string", "enum": [
            "zoning_development", "housing", "budget_taxes", "schools", "transit_transportation",
            "parks_environment", "public_safety_policy", "governance_elections", "other_local_decision",
            "crime_accident_tragedy", "obituary", "weather_disaster", "sports_entertainment",
            "business_promo", "human_interest", "national_or_nonlocal", "already_decided", "other_not_pollable"]},
        "reason": {"type": "string"},
        "city": {"type": "string"},
        "state": {"type": "string"},
        "decision_body": {"type": "string"},
    },
    "required": ["pollable", "category", "reason", "city", "state", "decision_body"],
    "additionalProperties": False,
}


def triage(headline, text, usage, city_hint=""):
    if llm.MOCK:
        from backend.agent import mock
        return mock.triage(headline, text, city_hint)
    body = text[:6000]
    hint = f"\nLocation hint from the page: {city_hint}" if city_hint else ""
    user = f"HEADLINE: {headline}{hint}\n\nARTICLE:\n{body}"
    return llm.structured(llm.TRIAGE_MODEL, "triage", SYSTEM, user, SCHEMA, usage, max_tokens=600)

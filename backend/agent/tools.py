"""Research tools for the draft agent. Stubbed with local JSON + the SQLite DB.
Swap the bodies for real sources later; the tool schemas stay the same."""
import json
import os

from backend import db

_DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
_AGENDA = json.load(open(os.path.join(_DATA, "agenda_items.json")))
_RELATED = json.load(open(os.path.join(_DATA, "related_articles.json")))

TOOLS = [
    {
        "name": "search_related_articles",
        "description": "Search other local news coverage related to a pending decision. Returns headlines, snippets and URLs. Use it to find positions and facts the current article may have left out.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords describing the decision, e.g. 'El Camino bike lane parking'"},
                "city": {"type": "string", "description": "City and state, e.g. 'Mountain View, CA'"},
            },
            "required": ["query", "city"],
            "additionalProperties": False,
        },
    },
    {
        "name": "fetch_agenda_item",
        "description": "Look up the official council, board or commission agenda item for a pending local decision. Returns the item summary, meeting date and scheduled decision date when found.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keywords describing the decision"},
                "city": {"type": "string", "description": "City and state"},
            },
            "required": ["query", "city"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_existing_polls",
        "description": "List polls already published for this city, so you do not duplicate a live poll and can keep framing consistent.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City and state"}},
            "required": ["city"],
            "additionalProperties": False,
        },
    },
]


def _norm_city(city):
    return (city or "").strip().lower()


def _score(keywords, query):
    q = query.lower()
    return sum(1 for k in keywords if k.lower() in q)


def search_related_articles(query, city=""):
    city_k = _norm_city(city)
    hits = []
    for item in _RELATED:
        if city_k and item["city"] != city_k and city_k not in item["city"]:
            continue
        s = _score(item["keywords"], query)
        if s:
            hits.append((s, {"headline": item["headline"], "url": item["url"], "snippet": item["snippet"]}))
    hits.sort(key=lambda x: -x[0])
    out = [h for _, h in hits[:3]]
    for a in db.search_articles(query, city=city_k or None, limit=3):
        out.append({"headline": a["headline"], "url": a["url"], "snippet": "(previously seen article)"})
    return {"results": out, "note": "Stub search over local demo data and previously seen articles."}


def fetch_agenda_item(query, city=""):
    city_k = _norm_city(city)
    best, best_s = None, 0
    for item in _AGENDA:
        if city_k and item["city"] != city_k and city_k not in item["city"]:
            continue
        s = _score(item["keywords"], query) + _score(item["title"].split(), query) * 0.1
        if s > best_s:
            best, best_s = item, s
    if not best or best_s < 1:
        return {"found": False, "note": "No matching agenda item in the local demo index."}
    return {"found": True, **{k: best[k] for k in ("id", "body", "meeting_date", "decision_date", "title", "summary", "source_url")}}


def get_existing_polls(city=""):
    polls = db.recent_polls_for_city(_norm_city(city), days=60, limit=10)
    return {"polls": [{"poll_id": p["poll_id"], "question": p["question"], "options": p["options"]} for p in polls]}


def run_tool(name, args):
    fn = {"search_related_articles": search_related_articles,
          "fetch_agenda_item": fetch_agenda_item,
          "get_existing_polls": get_existing_polls}.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": str(e)}

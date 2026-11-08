"""Step 3: draft the poll with Sonnet, using research tools in a manual tool-use loop."""
import json

from backend.agent import llm
from backend.agent.tools import TOOLS, run_tool

MAX_TOOL_STEPS = 6

SYSTEM = """You draft neutral community polls for local news articles about pending local decisions. Readers of the article vote; results are shown to the community and may be seen by local officials, so the poll must be scrupulously fair.

Process:
1. Identify the single concrete pending decision or open question in the article. If it covers several, pick the one most directly affecting residents.
2. Research it with the tools: fetch_agenda_item for the official item and decision date, search_related_articles for other coverage and positions the article may omit, get_existing_polls to avoid duplicating a live poll. Use each tool at most twice. Tool data may be missing; that is fine, work from the article.
3. Write the poll as JSON.

Rules:
- question: one sentence, plain language. Name the decision body and the specific proposal. No adjectives that signal a side ("controversial", "much-needed"), no presuppositions, no framing that presumes the outcome.
- options: 2 to 4. Cover the real positions in the debate, including a conditional option ("Yes, but only if ...") when the article or research shows one exists. On complex issues, make the LAST option "Not sure / need more information". Options must be parallel in tone and length; none may sound more reasonable than the others. Order options neutrally, never to favor one.
- context.for and context.against: 1-2 sentences each, the strongest fair summary of each side, drawn only from the article and tool results, with attribution ("Supporters say...", "The staff report estimates..."). Equal length and equal charity. No claim that is not in the article or research.
- geo_scope: ZIP codes of residents the decision affects. Use only ZIPs from the provided list when one is given; the whole list for city-wide decisions, a subset for neighborhood-level ones. If no list is provided, use your best knowledge of the city's ZIP codes.
- decision_date: ISO date YYYY-MM-DD if the article or agenda gives one, otherwise "".
- sources: URLs or identifiers from the article and tool results that support the context claims.
- notes: one line on which decision you chose and why.
Respond with JSON only."""

SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "options": {"type": "array", "items": {"type": "string"}},
        "context": {
            "type": "object",
            "properties": {"for": {"type": "string"}, "against": {"type": "string"}},
            "required": ["for", "against"],
            "additionalProperties": False,
        },
        "geo_scope": {"type": "array", "items": {"type": "string"}},
        "decision_date": {"type": "string"},
        "sources": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": ["question", "options", "context", "geo_scope", "decision_date", "sources", "notes"],
    "additionalProperties": False,
}


def _user_prompt(article, city_label, zips, prev_draft, feedback):
    parts = [f"CITY: {city_label or 'unknown'}"]
    if zips:
        parts.append(f"KNOWN ZIP CODES FOR THIS CITY: {', '.join(zips)}")
    parts.append(f"ARTICLE URL: {article.get('url') or 'n/a'}")
    parts.append(f"HEADLINE: {article['headline']}")
    parts.append(f"ARTICLE:\n{article['text'][:9000]}")
    if prev_draft and feedback:
        parts.append("YOUR PREVIOUS DRAFT WAS REJECTED BY THE FAIRNESS REVIEWER.\nPrevious draft:\n"
                     + json.dumps(prev_draft, indent=1)
                     + "\nReviewer issues:\n" + json.dumps(feedback, indent=1)
                     + "\nRevise the draft to fix every issue. You may re-run tools if you need more material, "
                       "but do not need to.")
    return "\n\n".join(parts)


def draft_poll(article, city_label, zips, usage, log=print, prev_draft=None, feedback=None, research=None):
    """Returns (draft_dict, research_list). research_list collects tool results for the critic."""
    research = research if research is not None else []
    if llm.MOCK:
        from backend.agent import mock
        return mock.draft(article, city_label, zips, prev_draft, feedback, research, log)
    if llm.PROVIDER == "ollama":
        return _draft_ollama(article, city_label, zips, usage, log, prev_draft, feedback, research)

    messages = [{"role": "user", "content": _user_prompt(article, city_label, zips, prev_draft, feedback)}]
    output_config = {"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}}
    client = llm.client()

    for step in range(MAX_TOOL_STEPS + 1):
        kwargs = dict(model=llm.DRAFT_MODEL, max_tokens=12000, system=SYSTEM, messages=messages,
                      tools=TOOLS, output_config=output_config)
        if step == MAX_TOOL_STEPS:
            kwargs["tool_choice"] = {"type": "none"}  # force a final answer
        resp = client.messages.create(**kwargs)
        usage.add(llm.DRAFT_MODEL, "draft", resp.usage)

        if resp.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for b in resp.content:
                if b.type == "tool_use":
                    out = run_tool(b.name, b.input)
                    log(f"   tool {b.name}({json.dumps(b.input)}) -> {json.dumps(out)[:160]}")
                    research.append({"tool": b.name, "args": b.input, "result": out})
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})
            continue
        if resp.stop_reason == "refusal":
            raise RuntimeError("Model refused to draft")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("Draft hit max_tokens")
        return json.loads(llm.text_of(resp)), research
    raise RuntimeError("Draft loop did not terminate")


def _draft_ollama(article, city_label, zips, usage, log, prev_draft, feedback, research):
    """Local-model path. Small models are unreliable at mixing tool calls with schema output,
    so: (1) a short research phase with tools, (2) one schema-constrained call to write the poll."""
    model = llm.DRAFT_MODEL
    user = _user_prompt(article, city_label, zips, prev_draft, feedback)
    if not research:  # research once; revisions reuse it
        tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                   "parameters": t["input_schema"]}} for t in TOOLS]
        messages = [{"role": "system", "content": SYSTEM + "\n\nSTEP 1: call the research tools you need (fetch_agenda_item and search_related_articles at least once each). Reply with the single word DONE when you have enough."},
                    {"role": "user", "content": user}]
        for _ in range(4):
            resp = llm.ollama_chat(model, messages, tools=tools, max_tokens=800)
            usage.add(model, "draft-research", llm._OllamaUsage(resp))
            msg = resp["message"]
            calls = msg.get("tool_calls") or []
            if not calls:
                break
            messages.append(msg)
            for c in calls:
                name = c["function"]["name"]
                args = c["function"].get("arguments") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except ValueError:
                        args = {}
                out = run_tool(name, args)
                log(f"   tool {name}({json.dumps(args)}) -> {json.dumps(out)[:160]}")
                research.append({"tool": name, "args": args, "result": out})
                messages.append({"role": "tool", "content": json.dumps(out), "tool_name": name})
        if not research:  # model skipped tools; run the two obvious lookups ourselves
            for name in ("fetch_agenda_item", "search_related_articles"):
                args = {"query": article["headline"], "city": city_label}
                out = run_tool(name, args)
                log(f"   tool {name}(auto) -> {json.dumps(out)[:120]}")
                research.append({"tool": name, "args": args, "result": out})
    final = [{"role": "system", "content": SYSTEM},
             {"role": "user", "content": user + "\n\nRESEARCH RESULTS (from your tools):\n"
              + json.dumps(research, indent=1)[:7000] + "\n\nNow write the poll as JSON."}]
    resp = llm.ollama_chat(model, final, schema=SCHEMA, max_tokens=1800)
    usage.add(model, "draft", llm._OllamaUsage(resp))
    draft = json.loads(resp["message"]["content"])
    if not draft.get("options") or len(draft["options"]) < 2:
        raise RuntimeError("local model returned fewer than 2 options")
    return draft, research

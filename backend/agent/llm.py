"""Claude client, model config, token/cost accounting, and MOCK mode switch."""
import json
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

PROVIDER = os.getenv("LLM_PROVIDER", "claude").strip().lower()   # claude | ollama | mock
if os.getenv("MOCK_LLM", "0") == "1":
    PROVIDER = "mock"
MOCK = PROVIDER == "mock"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
if PROVIDER == "ollama":
    TRIAGE_MODEL = os.getenv("OLLAMA_TRIAGE_MODEL", OLLAMA_MODEL)
    DRAFT_MODEL = os.getenv("OLLAMA_DRAFT_MODEL", OLLAMA_MODEL)
else:
    TRIAGE_MODEL = os.getenv("TRIAGE_MODEL", "claude-haiku-4-5-20251001")
    DRAFT_MODEL = os.getenv("DRAFT_MODEL", "claude-sonnet-5")

# $ per 1M tokens (input, output) - Anthropic list prices
PRICES = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-opus-5": (5.0, 25.0),
}


def _price_for(model):
    for k, v in PRICES.items():
        if model.startswith(k):
            return v
    return (0.0, 0.0)


class Usage:
    """Accumulates tokens across all calls in one pipeline run."""

    def __init__(self):
        self.calls = []

    def add(self, model, step, usage):
        self.calls.append({
            "model": model, "step": step,
            "input": (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0)
                     + (getattr(usage, "cache_creation_input_tokens", 0) or 0),
            "output": usage.output_tokens or 0,
        })

    def summary(self):
        cost = 0.0
        per_model = {}
        for c in self.calls:
            pi, po = _price_for(c["model"])
            cost += c["input"] / 1e6 * pi + c["output"] / 1e6 * po
            m = per_model.setdefault(c["model"], {"input": 0, "output": 0, "calls": 0})
            m["input"] += c["input"]
            m["output"] += c["output"]
            m["calls"] += 1
        return {"cost_usd": round(cost, 4), "per_model": per_model, "n_calls": len(self.calls)}


_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError("ANTHROPIC_API_KEY is not set. Put it in backend/.env, or set MOCK_LLM=1 to run offline.")
        _client = anthropic.Anthropic()
    return _client


class _OllamaUsage:
    def __init__(self, resp):
        self.input_tokens = resp.get("prompt_eval_count", 0) or 0
        self.output_tokens = resp.get("eval_count", 0) or 0


def ollama_chat(model, messages, schema=None, tools=None, max_tokens=2048, temperature=0.2):
    """One /api/chat call to a local Ollama server. Returns the parsed JSON response."""
    import urllib.request
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens, "num_ctx": 16384}}
    if schema:
        body["format"] = schema
    if tools:
        body["tools"] = tools
    req = urllib.request.Request(OLLAMA_URL + "/api/chat", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Ollama call failed ({OLLAMA_URL}, model {model}): {e}. "
                           f"Is `ollama serve` running and the model pulled?") from e


def text_of(response):
    return "".join(b.text for b in response.content if b.type == "text")


def structured(model, step, system, user_content, schema, usage, max_tokens=2048, effort=None):
    """One-shot call that returns validated JSON (Claude: output_config.format; Ollama: format=schema)."""
    if PROVIDER == "ollama":
        resp = ollama_chat(model, [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
                           schema=schema, max_tokens=max_tokens)
        usage.add(model, step, _OllamaUsage(resp))
        return json.loads(resp["message"]["content"])
    output_config = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    resp = client().messages.create(
        model=model, max_tokens=max_tokens, system=system,
        messages=[{"role": "user", "content": user_content}],
        output_config=output_config,
    )
    usage.add(model, step, resp.usage)
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"Model refused at step {step}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError(f"Hit max_tokens at step {step}")
    return json.loads(text_of(resp))

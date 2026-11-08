# NewsBreak Community Polls

**What does my town actually think?**

A Chrome extension and a small agent backend that attach a neutral, location-gated poll to local news stories about
decisions that haven't been made yet: a zoning vote, a school-budget cut, a bike lane that removes parking. Readers vote
with one click; only residents of the affected ZIP codes can vote; everyone can read. Council members get a signal
from the whole town instead of the comments section.

Built in one day at the NewsBreak x CMU local-AI hackathon (September 2026) by two CMU software engineering students.
The extension is the prototype vehicle; the design is meant to become a native NewsBreak feature.

## What it does

- **Polls only on decisions.** A triage model decides whether a story is about a pending local decision or a live
  community question. Crime, accidents, court cases, obituaries, business openings, and already-decided items are
  declined, and the decline is shown with its reason. We poll decisions, never incidents.
- **One poll per story, generated once.** The first reader of a story triggers the agent; every later reader gets the
  cached poll. Syndicated copies and differently-worded articles about the same decision map to the same poll, first
  by content hash and then by a model that compares the article against open polls in the same city.
- **Neutral by construction.** The draft step researches the decision with tools (agenda item, related coverage,
  existing polls), then writes a question, 2-4 parallel options, and an attributed case-for / case-against. A separate
  critic model checks for loaded wording, missing options, unsupported claims, leading option order, and scope errors,
  and sends the draft back for revision when it finds a major problem. What the critic caught is logged and shown in the
  widget under "How this poll was made".
- **No anchoring.** Feed cards show only the vote count. The split appears once 30 votes exist, and only to people who
  have voted or who cannot vote here.
- **Runs entirely on a laptop.** The default provider is a local 7B model through Ollama. Claude (Haiku 4.5 for triage,
  Sonnet 5 for draft and critic) is a drop-in alternative when an API key is available.

## How it works

```
Chrome extension (MV3)                      Backend (FastAPI + SQLite)
┌────────────────────────┐   article text   ┌──────────────────────────────────────────┐
│ article page           │ ───────────────▶ │ cache lookup ─▶ content-hash dedupe       │
│  extract (JSON-LD)     │                  │   ─▶ triage (pollable? city?)             │
│  widget (Shadow DOM)   │ ◀─────────────── │   ─▶ match against open polls in city     │
│ feed page              │  poll / verdict  │   ─▶ draft (tools) ⇄ critic (≤2 retries)  │
│  badges: counts only   │                  │   ─▶ publish, then serve from cache       │
│ popup: ZIP, position   │  votes, results  │ votes: one per voter per poll, ZIP-gated  │
└────────────────────────┘                  └──────────────────────────────────────────┘
```

Research tools are stubbed with local data (`backend/data/`) so the agent loop is real but needs no external services.
Swapping in live sources (Legistar agendas, a related-story index) is a one-file change.

## Results

Triage evaluated on 49 real local articles collected by hand from the Mountain View feed and nearby cities, labeled
pollable or not, using the local `qwen2.5:7b` model on headline plus a one-line summary:

| n | precision | recall | F1 | accuracy |
|---|---|---|---|---|
| 49 | 0.84 | 0.94 | 0.89 | 0.92 |

All four misses were rows we had marked borderline while labeling: an informational school-board report, a council
candidate forum, a "more cuts may follow" budget story, and a data-center noise story with no scheduled vote.

Critic behavior on the same article across four fresh runs: before tuning, the small model failed every draft, partly on
invented grounds. Three fixes made it usable: issues carry a major/minor severity and only major ones fail a draft; the
article itself is labeled as supporting material and any "unsupported" figure that appears verbatim in the article is
auto-downgraded; when nothing passes, the attempt with the fewest major issues is published and flagged. Real catches
along the way: "as planned" presuming the outcome, and a compromise option the article described but the draft omitted.

## Run it

Requirements: Python 3.10+, Chrome, and either [Ollama](https://ollama.com) or an Anthropic API key.

```bash
python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env            # LLM_PROVIDER=ollama by default; or set claude + ANTHROPIC_API_KEY
ollama pull qwen2.5:7b && ollama serve &        # local model
.venv/bin/python -m scripts.seed_demo --reset    # 5 example polls with simulated votes, 6 pre-triaged declines
.venv/bin/uvicorn backend.main:app --port 8000
```

Load the extension: `chrome://extensions`, Developer mode, Load unpacked, pick `extension/`. Enter your ZIP in the poll
widget or the popup (Mountain View is 94040). Then open an article, for example
https://www.newsbreak.com/san-jos-spotlight-510761/3702094647051-mountain-view-planning-commission-backs-affordable-housing-development-with-little-parking

Other useful commands:

```bash
.venv/bin/python -m backend.cli eval/articles/demo_bike_lane.txt --city "Mountain View, CA" --fresh   # watch the agent trace
.venv/bin/python -m eval.run_triage_eval      # precision / recall on eval/labeled_articles.jsonl
.venv/bin/python -m eval.critic_report        # drafts flagged, issue types, before/after questions
.venv/bin/python -m scripts.smoke_test        # end-to-end API checks against a running backend
.venv/bin/python -m scripts.export_polls      # every poll and its votes as Markdown
```

The operator dashboard at `http://localhost:8000/admin` shows every poll with its split, votes by ZIP, mapped
articles, critic status, recent votes, and declined articles. It has no authentication and shows splits regardless of
the 30-vote gate, so it is for the person running the backend, not for readers.

Mock mode (`MOCK_LLM=1`) runs the whole pipeline with canned responses for extension work without any model.

## Repo layout

```
backend/            FastAPI app, SQLite layer, admin page
backend/agent/      triage.py, match.py, draft.py, critic.py, pipeline.py, tools.py, llm.py (provider switch)
backend/data/       zips.json, stub agenda items and related articles
extension/          Manifest V3, vanilla JS: extract.js, content_article.js, content_feed.js, popup, background
eval/               49 labeled articles, triage eval, critic report
scripts/            seed_demo.py, seed_polls.json, smoke_test.py, export_polls.py
```

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/polls/get-or-create` | `{url, headline, text, article_id?, city_hint?, voter_id?, zip?}` → cached or new poll, or `pollable: false` with the triage reason |
| POST | `/api/polls/batch` | `{article_ids}` → `{id: {poll_id, total}}` for cards with polls (counts only) |
| POST | `/api/polls/{id}/vote` | `{voter_id, option_idx, zip}`; 403 outside `geo_scope`; re-voting replaces |
| GET | `/api/polls/{id}?voter_id=&zip=` | poll plus gated results |
| GET | `/admin` | operator dashboard |

## Limits and what's next

- The extension runs on newsbreak.com only. Extending it to publishers' own sites is mostly a manifest change; the
  content-hash and same-decision matching already handle a story appearing on several sites.
- Research tools are stubs. Real agenda feeds would let the agent cite decision dates and staff reports directly.
- A second poll tier for lighter community questions (favorites, predictions) would widen coverage; it should stay
  visually distinct from decision polls so the neutral ones keep their credibility.
- Raw versus population-weighted results with a margin of error: votes already store ZIP; a ZIP population table is all
  that's missing.

## Terms of service

The backend never fetches NewsBreak pages. Article text leaves the browser only for a story the user already opened,
once per story. The eval set holds URLs, headlines, and our own one-line summaries; no article bodies are stored in the
repo. A native integration would read from NewsBreak's own content store.

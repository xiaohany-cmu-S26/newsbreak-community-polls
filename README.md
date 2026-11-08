# NewsBreak Community Polls

**"What does my town actually think?"** A Chrome extension plus a small backend agent that attaches a neutral,
AI-generated, location-gated poll to NewsBreak stories about *pending* local decisions (zoning, budgets, school
policy, transit). Built for the NewsBreak x CMU local-AI hackathon. The extension is the prototype vehicle; the pitch
is that this becomes a native NewsBreak feature.

## How it works

1. **Lazy generation.** A poll is generated only when the first reader opens an article. It is cached; every later
   reader sees the same poll. Each article gets at most one agent run (global lock + DB cache).
2. **Cheap triage first** (Claude Haiku 4.5): is this a pending local decision or open community question? Crime,
   accidents, obituaries, business promos, already-decided items are declined. Verdicts are cached, including declines.
3. **Same story, many URLs.** Before drafting, the backend checks a content hash (syndicated copies) and then asks
   Haiku whether the article is about the same decision as any open poll in the same city. Matches link to the
   existing poll instead of creating a duplicate.
4. **Draft with research tools** (Claude Sonnet 5, tool use): `search_related_articles`, `fetch_agenda_item`,
   `get_existing_polls` (stubbed with local data in `backend/data/`). Output: neutral question, 2-4 options,
   for/against context, ZIP-code `geo_scope`, `decision_date`, sources.
5. **Critic loop** (Sonnet 5): a second call checks for loaded wording, missing options, unsupported claims, leading
   option order, scope errors. Failures go back to the drafter, max 2 retries. Everything the critic caught is logged
   and shown in the widget under "How this poll was made".
6. **Voting.** One click. Only ZIPs in `geo_scope` can vote (set your ZIP in the widget or popup); everyone can view.
   The split is shown only once 30+ votes exist, and only to people who have voted or who cannot vote here
   (non-residents cannot be anchored, so they see results right away). Feed cards show the vote **count** only.

**Where the models run.** Three providers, chosen with `LLM_PROVIDER` in `backend/.env`:

| Provider | Runs where | Cost | Quality |
|---|---|---|---|
| `ollama` (default in `.env.example`) | Fully on this laptop via [Ollama](https://ollama.com) (`qwen2.5:7b`) | free | good enough for the demo; slower (1-3 min per fresh poll) |
| `claude` | Anthropic API: Haiku 4.5 triage, Sonnet 5 draft + critic | ~$0.10 per poll | best; what a native NewsBreak integration would use |
| `mock` | canned responses | free | placeholders, for extension work only |

The database, URL matching, content-hash dedupe, vote storage and result gating always run locally regardless of
provider. An Anthropic key, if used, lives only in `backend/.env`; the extension never sees it.

## Repo layout

```
backend/            FastAPI + SQLite + agent (triage.py, match.py, draft.py, critic.py, pipeline.py, tools.py)
backend/data/       zips.json, agenda_items.json, related_articles.json (demo stub data), polls.db (created)
backend/cli.py      run the pipeline on a pasted article and print the trace
extension/          Manifest V3, vanilla JS: extract.js, content_article.js, content_feed.js, popup, background
eval/               labeled_articles.jsonl (49 hand-labeled), run_triage_eval.py, critic_report.py
scripts/            seed_demo.py, seed_polls.json (5 demo polls), seed_declined.json
```

## Setup

```bash
/opt/homebrew/bin/python3.12 -m venv .venv          # needs Python 3.10+
.venv/bin/pip install -r backend/requirements.txt
cp backend/.env.example backend/.env                # paste your sk-ant-... key; or set MOCK_LLM=1 to run offline
.venv/bin/python -m scripts.seed_demo --reset       # 5 demo polls with votes + 6 pre-triaged declines
.venv/bin/uvicorn backend.main:app --port 8000
```

Load the extension: `chrome://extensions` → Developer mode → Load unpacked → pick `extension/`. Enter your ZIP either
in the box inside the poll widget or in the popup (ZIP `94040` for Mountain View). The popup also sets the backend URL
and where the poll appears on article pages: right sidebar (default, falls back to end of article), end of article, or
under the headline. After editing extension files, click the reload arrow on the extension's card.

Local model (no API account needed):

```bash
brew install ollama
ollama serve &                      # leave running
ollama pull qwen2.5:7b              # ~4.7 GB, once
# backend/.env: LLM_PROVIDER=ollama
```

Mock mode: `MOCK_LLM=1 .venv/bin/uvicorn backend.main:app --port 8000` runs the pipeline with canned responses
(keyword triage, generic draft, a critic that catches one loaded word). For extension work only.

Demo vote data: `.venv/bin/python -m scripts.seed_demo --sim-votes` gives every poll without votes a simulated,
realistic distribution. With `DEMO_SIM_VOTES=1` in `.env`, polls generated during the demo get one automatically.

Expose for a teammate's laptop: `ngrok http 8000` (free account + authtoken; claim the free static domain), then put
the `https://...ngrok-free.app` URL in the popup. The extension sends the header that skips ngrok's warning page.

## Run the agent on pasted text

```bash
.venv/bin/python -m backend.cli eval/articles/demo_bike_lane.txt --city "Mountain View, CA" --fresh
.venv/bin/python -m backend.cli eval/articles/demo_crime.txt --city "Mountain View, CA" --fresh   # declined
```

Prints the trace: triage → tool calls → draft → critic verdict → (revision) → publish, with token cost.

## Evaluation

```bash
.venv/bin/python -m eval.run_triage_eval     # precision / recall on eval/labeled_articles.jsonl
.venv/bin/python -m eval.critic_report       # drafts flagged, issue types, before/after questions
```

`labeled_articles.jsonl` has 49 real articles (17 pollable, 32 not) collected by hand from the Mountain View feed and
nearby cities, with URL, headline, a one-line summary in our own words, label and notes on borderline cases. To
evaluate on full article text, paste a body into `eval/articles/<id>.txt` (first line = headline); the script
prefers it over the summary. Results land in `eval/results/`.

Results so far (local `qwen2.5:7b`, headline + one-line summary per article, 2026-09-19):

| n | precision | recall | F1 | accuracy |
|---|---|---|---|---|
| 49 | 0.84 | 0.94 | 0.89 | 0.92 |

All four misses were rows we had marked *borderline* when labeling (an informational school-board report, a
council candidate forum, a "more cuts may follow" budget story, and a data-center noise story with no scheduled vote).
Re-run with `LLM_PROVIDER=claude` for the Haiku numbers once a key is available.

Critic notes (local model, same bike-lane article, four fresh runs): before tuning, the 7B critic failed every draft,
partly on invented grounds (figures "unsupported" that were in the article; city-wide ZIP scope; "as proposed" called
loaded). Three fixes: issues carry a `major`/`minor` severity and only major ones fail a draft; the article is
explicitly labeled as supporting material and any "unsupported" figure that appears verbatim in the article is
auto-downgraded; when no draft passes, the attempt with the fewest major issues is published and flagged. After tuning
the first draft passed in 51 s. Real catches seen along the way: "as planned" (presumes the outcome) and a missing
compromise option that the article described. Expect Sonnet's critic to be both stricter and more accurate.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/polls/get-or-create` | `{url, headline, text, article_id?, city_hint?, voter_id?, zip?}` → cached or new poll, or `pollable:false` with triage reason |
| POST | `/api/polls/batch` | `{article_ids: [...]}` → `{id: {poll_id, total}}` for cards that have polls (count only) |
| POST | `/api/polls/{id}/vote` | `{voter_id, option_idx, zip}`; 403 if ZIP outside `geo_scope` |
| GET | `/api/polls/{id}?voter_id=&zip=` | poll + gated results |
| GET | `/api/polls` | list (sanity checks) |
| GET | `/admin` | operator dashboard: every poll with its split, votes by ZIP, mapped articles, critic status, recent votes, declined articles; auto-refreshes every 5 s. Shows splits regardless of the 30-vote gate and has no auth: demo only |

## Demo script (2 minutes)

Backend running, DB seeded, extension loaded with ZIP 94040. Keep `http://localhost:8000/admin` open in a second
window: votes cast during the demo appear there within 5 seconds.

Right before recording, clear your rehearsal votes so the "vote, then see the split" moment happens on camera
(keeps every poll and all simulated votes): `.venv/bin/python -m scripts.seed_demo --forget-real-votes`.
Start the backend from your own terminal so it outlives any other session:
`LLM_PROVIDER=ollama DEMO_SIM_VOTES=1 .venv/bin/uvicorn backend.main:app --port 8000`.

1. **Feed.** Open `newsbreak.com/mountain-view-ca`. Cards for the San Jose self-checkout and data-center stories carry
   badges: "📊 302 neighbors voted" and "📊 Poll open — be one of the first to vote". Counts only, never the split.
2. **Vote.** Open the 334 San Antonio Road affordable-housing article
   (`newsbreak.com/san-jos-spotlight-510761/3702094647051-...`). The poll appears under the headline with the
   case for and against. Click an option; the split appears (214 votes).
3. **Geo gate.** Open the San Jose self-checkout article. Same widget, but a notice: voting is limited to San Jose
   ZIPs; you can view only.
4. **Declined.** Open "Charges dropped against former Mountain View El Camino Hospital manager". No poll; with
   "show agent trace" on, the widget shows the triage reason. Any fresh crime story is declined the same way, live.
5. **Fresh article (optional).** Open an article no one has opened. The widget shows "first reader waits for the
   agent", then the poll appears with "Neutrality check: N critic passes, revised for: ...". With the local model this
   takes 1-3 min, so either start it before the demo clock or show the CLI trace instead. Everyone opening it
   afterward gets the cached poll instantly.

## Terms-of-service note

The backend never fetches NewsBreak pages. Article text leaves the browser only for an article the user already
opened, once per article. Eval and seed data were collected by hand (URLs, headlines, our own one-line summaries);
no article bodies are stored in the repo. A native integration would read from NewsBreak's own content store.

## Stretch ideas not built

- Raw vs. population-weighted results with a margin of error (votes already store ZIP; add a ZIP population table).
- Swap the stubbed research tools for real sources (Legistar agendas, NewsBreak's own related-story index).

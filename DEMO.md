# Demo kit

## 1. Thirty minutes before

Open two terminals in the project folder (`/Users/davidyu/NewsBreak Polling Extension`).

**Terminal A: backend** (kills any old copy first)

```bash
pkill -f "uvicorn backend.main:app"; LLM_PROVIDER=ollama DEMO_SIM_VOTES=1 .venv/bin/uvicorn backend.main:app --port 8000
```

Check: http://localhost:8000/api/health shows `"ok": true, "provider": "ollama"`.

**Terminal B: local model** (only needed if you open an article nobody has opened; harmless to leave running)

```bash
ollama serve
```

**Terminal B, then: refresh the feed polls.** The Mountain View feed changes daily, so the two San Jose stories that
carry badges today may have scrolled off. Open https://www.newsbreak.com/mountain-view-ca in Chrome, pick one or two
stories on the front page that are about a pending decision, and open each once with the extension on. The local
model generates a poll in 1-3 minutes and `DEMO_SIM_VOTES=1` fills it with votes, so those cards show badges on the feed.

**Terminal B, then: pre-run the agent trace** so you can scroll it instead of waiting on camera (about 1 minute):

```bash
LLM_PROVIDER=ollama .venv/bin/python -m backend.cli eval/articles/demo_bike_lane.txt --city "Mountain View, CA" --fresh
```

Leave this terminal visible for step 5 of the run of show.

**Chrome**

- `chrome://extensions`: the "NewsBreak Community Polls" card is on. If you changed any file, click its reload arrow.
- Extension popup: ZIP `94040`, backend `http://localhost:8000`, position "Right sidebar", trace on.
- Zoom Chrome to 125% (Cmd and +) so the widget is legible on a projector or recording.
- Do Not Disturb on (click the clock in the menu bar, then Focus).
- Open the tabs below, in this order, left to right.

## 2. Right before you start (and after every rehearsal)

Clear your own votes so the "vote, then see the split" moment happens live. Keeps all polls and simulated votes:

```bash
.venv/bin/python -m scripts.seed_demo --forget-real-votes
```

Then reload the article tabs. The widget footer should read `ZIP 94040 · v0.5`.

## 3. Tabs, in order

| # | Purpose | Link |
|---|---|---|
| 1 | Feed with badges (counts only) | https://www.newsbreak.com/mountain-view-ca |
| 2 | Vote: Mountain View poll, 214 votes | https://www.newsbreak.com/san-jos-spotlight-510761/3702094647051-mountain-view-planning-commission-backs-affordable-housing-development-with-little-parking |
| 3 | Geo gate: San Jose poll, view only from 94040 | https://www.newsbreak.com/news/4892773502565-san-jose-could-be-first-bay-area-city-to-introduce-self-checkout-line-regulations |
| 4 | Declined: crime/court story, shows triage reason | https://www.newsbreak.com/news/4894641156677-charges-dropped-against-former-mountain-view-el-camino-hospital-manager |
| 5 | Admin dashboard, on a second screen if you have one | http://localhost:8000/admin |
| 6 | Eval numbers (README, "Evaluation" section) | `README.md` in the project folder |

Spare articles with polls, if you want more: parking minimums
https://www.newsbreak.com/news/3606213450231-mountain-view-looks-to-eliminate-parking-requirements-for-housing-in-parts-of-the-city ·
teacher-housing land https://www.newsbreak.com/news/3770002815473-mountain-view-whisman-looks-to-buy-the-land-teacher-housing-is-built-on ·
San Jose data centers (12 votes, shows the "be one of the first" state) https://www.newsbreak.com/news/4893256207854-san-jose-mayor-meets-with-neighbors-complaining-about-data-center-noise

## 4. Run of show (2 minutes)

| Time | Tab | Do | Say |
|---|---|---|---|
| 0:00 | 1 | Scroll to a badge | "Local news tells you what's happening. Nobody knows what the town actually thinks. We attach a neutral poll to stories about decisions that haven't been made yet. Cards show only how many neighbors voted, never the split, so nobody gets anchored." |
| 0:15 | 2 | Point at question, for/against, sources. Click an option. Split appears. | "The decision body, the specific proposal, the case for and against, with sources. I'm in 94040 so I can vote. Only after I vote, and only once 30 neighbors have, do I see the split: 214 neighbors." |
| 0:45 | 5 | Show the vote in "Recent votes" | "Every vote lands in one place. Here's mine, seconds later." |
| 0:55 | 3 | Show the view-only notice | "Same widget on a San Jose story. My ZIP is outside the area, so I can read but not vote. Polls are location-gated." |
| 1:10 | 4 | Show the declined notice | "A crime story gets no poll. We poll decisions, never incidents: no crime, tragedy, obituaries, or things already decided." |
| 1:25 | Terminal B | Scroll the trace: triage, tools, draft, critic, published | "One agent run per story, then cached for everyone. Triage, three research tools, a draft, then an independent critic checking for loaded wording, missing options, unsupported claims. It runs on this laptop on a 7B model. Zero API cost." |
| 1:50 | 6 | Eval table | "49 hand-labeled local articles: 84% precision, 94% recall. Every miss was a case we'd marked borderline ourselves. Built as an extension, designed to ship as a native NewsBreak feature." |

Numbers to say out loud: 214 neighbors, 30-vote threshold, 49 articles, 84 / 94, zero API cost, one run per story.

## 5. If something goes wrong

| Symptom | Fix |
|---|---|
| No widget on an article | Reload the extension card in `chrome://extensions`, then reload the page. Footer must say v0.5. |
| "Community poll unavailable: HTTP…" or "extension messaging failed" | Backend is down. Re-run the Terminal A command; check http://localhost:8000/api/health. |
| Options greyed out, "Enter your ZIP" box shown | Type 94040 in the box and press Save. |
| Options greyed out, "your vote" already marked | You already voted. Run the step 2 command and reload. |
| Widget says "Checking for a community poll…" for a long time | First open of an unseen story; the local model is generating (1-3 min). Use a link from section 3 instead. |
| Badges missing on the feed | Those stories scrolled off the front page. Use the direct article links; polls still work there. |
| Port 8000 busy | `pkill -f "uvicorn backend.main:app"` then start again. |

## 6. Recording (Mac)

Cmd + Shift + 5, Record Selected Portion around the Chrome window, Options: pick your microphone and Show Mouse
Clicks. Stop with the square icon in the menu bar. The .mov lands on the desktop; trim in QuickTime with Cmd + T.

// Article page: extract -> get-or-create poll -> render widget in a Shadow DOM (sidebar / end of article / under headline).
(function () {
  const VERSION = "0.9";
  const NB = window.NBPolls;
  const articleId = NB.articleIdFromUrl(location.href);
  if (!articleId) return; // not an article page

  const CSS = `
    :host { all: initial; display: block; }
    .card { container-type: inline-size; font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1e1b4b;
            border: 2px solid #4f46e5; border-radius: 14px; padding: 0 18px 16px; margin: 16px 0; background: #f5f3ff;
            box-shadow: 0 6px 18px rgba(79,70,229,.18); overflow: hidden; }
    .kicker { display: flex; align-items: center; gap: 8px; margin: 0 -18px 14px; padding: 9px 18px; background: #4f46e5; color: #fff;
              font-size: 11.5px; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
    .kicker span { color: #e0e7ff; font-weight: 500; letter-spacing: 0; text-transform: none; margin-left: auto; font-size: 11.5px; }
    .q { font-size: 16px; font-weight: 800; margin: 0 0 12px; line-height: 1.3; color: #1e1b4b; }
    .opt { display: flex; align-items: center; width: 100%; box-sizing: border-box; text-align: left; margin: 6px 0; padding: 10px 12px;
           border: 1.5px solid #c7d2fe; border-radius: 9px; background: #fff; cursor: pointer; font: inherit; color: #1e1b4b; position: relative; overflow: hidden; }
    .opt:hover:not(:disabled) { border-color: #4f46e5; background: #eef2ff; }
    .opt:disabled { cursor: default; }
    .opt .bar { position: absolute; left: 0; top: 0; bottom: 0; background: #c7d2fe; z-index: 0; transition: width .4s; }
    .opt .lbl { position: relative; z-index: 1; flex: 1; }
    .opt .pct { position: relative; z-index: 1; font-weight: 800; margin-left: 10px; color: #3730a3; white-space: nowrap; }
    .opt .pct small { font-weight: 500; color: #4b5563; font-size: 12px; margin-right: 6px; }
    .opt.mine { border-color: #4f46e5; box-shadow: 0 0 0 2px #c7d2fe inset; }
    .opt.mine .lbl::after { content: " ✓ your vote"; color: #4f46e5; font-size: 12px; font-weight: 700; }
    .meta { color: #4b5563; font-size: 12.5px; margin-top: 10px; }
    .notice { background: #fff7ed; border: 1px solid #fdba74; color: #7c2d12; padding: 8px 10px; border-radius: 8px; font-size: 13px; margin: 8px 0; }
    .notice input { width: 80px; padding: 5px 7px; border: 1px solid #fdba74; border-radius: 6px; font: inherit; margin: 0 6px; }
    .notice button { padding: 5px 10px; border: 0; border-radius: 6px; background: #4f46e5; color: #fff; font: inherit; font-weight: 700; cursor: pointer; }
    .ctx { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 12px; }
    .ctx div { background: #fff; border: 1px solid #e0e7ff; border-radius: 8px; padding: 10px; font-size: 13px; color: #1f2937; }
    .ctx b { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: #4f46e5; margin-bottom: 4px; }
    details { margin-top: 10px; font-size: 12.5px; color: #4b5563; }
    summary { cursor: pointer; color: #3730a3; font-weight: 700; }
    .trace { font-family: ui-monospace, Menlo, monospace; font-size: 11.5px; white-space: pre-wrap; background: #fff; border: 1px solid #e0e7ff; padding: 8px; border-radius: 6px; margin-top: 6px; }
    .muted { color: #6b7280; font-size: 12.5px; }
    .foot { color: #8b8fa8; font-size: 11px; margin-top: 10px; }
    .spin { display: inline-block; width: 12px; height: 12px; border: 2px solid #c7d2fe; border-top-color: #4f46e5; border-radius: 50%; animation: s 1s linear infinite; vertical-align: -2px; margin-right: 6px; }
    @keyframes s { to { transform: rotate(360deg); } }
    a { color: #4f46e5; }
    @container (max-width: 560px) { .ctx { grid-template-columns: 1fr; } .q { font-size: 15px; } }
  `;

  let host, root, state = { poll: null, settings: null, extracted: null, error: null, stage: "extracting", triage: null, placement: "" };
  console.log(`[nb-polls] v${VERSION} content script running on article ${articleId}`);

  // ---------- placement ----------
  function findSidebarColumn() {
    // The publisher card ("Posts" / "Followers") sits at the top of the right column. Climb from it until the
    // element's parent is much wider (that parent is the content+sidebar row); the element is the sidebar column.
    // Markers seen at the top of NewsBreak's right column: publisher card ("Followers") or the location panel.
    // Only consider elements that actually sit in the right half near the top, so recommendation cards
    // lower in the main column ("user · 1.6K followers") are ignored.
    const marker = /Followers|NEARBY LOCATION|Nearby/i;
    const vw = window.innerWidth;
    const leaf = [...document.querySelectorAll("main div, main section, aside div, aside section")]
      .filter((el) => {
        if (!marker.test(el.innerText || "") || (el.innerText || "").length > 600) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.left > vw * 0.55 && r.top < 1400;
      })
      .sort((a, b) => a.innerText.length - b.innerText.length)[0];
    if (!leaf) return null;
    let el = leaf;
    for (let i = 0; i < 12 && el.parentElement; i++) {
      const r = el.getBoundingClientRect();
      const pr = el.parentElement.getBoundingClientRect();
      if (r.width >= 260 && r.width <= 640 && r.left > vw * 0.5 && pr.width > r.width * 1.4) return el;
      el = el.parentElement;
    }
    return null;
  }
  function findArticleEnd() {
    let best = null, bestLen = 0;
    for (const el of document.querySelectorAll("article, section, div")) {
      const ps = [...el.querySelectorAll(":scope > p")];
      if (ps.length < 3) continue;
      const len = ps.reduce((n, p) => n + p.innerText.length, 0);
      if (len > bestLen) { best = el; bestLen = len; }
    }
    return best;
  }
  function mount() {
    if (host) return;
    host = document.createElement("div");
    host.id = "nb-polls-host";
    root = host.attachShadow({ mode: "open" });
    const pref = (state.settings && state.settings.position) || "top";
    const h1 = document.querySelector("h1");
    let placed = false;
    if (pref === "sidebar") {
      const col = findSidebarColumn();
      if (col) {
        // Cap the widget at the column's current width: a flex column with auto basis would otherwise grow to
        // fit the widget's longest line and squeeze the article.
        const w = Math.round(col.getBoundingClientRect().width);
        host.style.cssText = `display:block;width:100%;max-width:${w}px;min-width:0;margin-bottom:16px`;
        col.insertAdjacentElement("afterbegin", host); placed = true;
      }
    }
    if (!placed && pref !== "top") {
      const end = findArticleEnd();
      if (end) { end.insertAdjacentElement("afterend", host); placed = true; }
    }
    if (!placed) {
      const anchor = h1 ? (h1.closest("header") || h1) : document.querySelector("main") || document.body;
      anchor.insertAdjacentElement(h1 ? "afterend" : "afterbegin", host);
      state.placement = h1 ? "under-headline" : "page-top";
    } else state.placement = pref;
    console.log(`[nb-polls] v${VERSION} mounted (${state.placement})`);
  }

  // The page is a client-rendered app: it can replace the DOM around our node after we insert it, or the headline
  // may not exist yet when we first run. Re-attach if we get detached, and move under the headline once it appears.
  setInterval(() => {
    if (!host) return;
    const detached = !document.contains(host);
    const betterAnchor = state.placement === "page-top" && document.querySelector("h1");
    if (detached || betterAnchor) {
      console.log(`[nb-polls] re-mounting (${detached ? "detached by page" : "headline appeared"})`);
      host.remove(); host = null; root = null;
      render();
    }
  }, 1000);

  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // ---------- rendering ----------
  function render() {
    mount();
    const { poll, settings, error, stage } = state;
    let body = "";
    if (error) body = `<div class="notice">Community poll unavailable: ${esc(error)}</div>`;
    else if (stage === "extracting") body = `<div class="muted"><span class="spin"></span>Reading article…</div>`;
    else if (stage === "loading") body = `<div class="muted"><span class="spin"></span>Checking for a community poll… (first reader of a story waits for the agent: triage → draft → critic)</div>`;
    else if (stage === "declined") {
      // Always shown: declining incidents is a feature, not an absence.
      const t = state.triage || {};
      const cat = (t.category || "not pollable").replace(/_/g, " ");
      body = `<div class="muted"><b>No poll for this story.</b> We poll decisions, never incidents. Triage: <b>${esc(cat)}</b>${settings.showTrace && t.reason ? " — " + esc(t.reason) : ""}</div>`;
    } else if (poll) body = renderPoll(poll, settings);
    const zipTxt = settings && settings.zip ? `ZIP ${esc(settings.zip)}` : "no ZIP set";
    const cityRaw = (poll && poll.city) ? poll.city.split(",")[0] : "";
    const city = cityRaw ? cityRaw.replace(/\b\w/g, (c) => c.toUpperCase()) : "my town";
    root.innerHTML = `<style>${CSS}</style><div class="card"><div class="kicker">📊 Community Poll <span>What does ${esc(city)} actually think?</span></div>${body}<div class="foot">${zipTxt} · v${VERSION}</div></div>`;
    root.querySelectorAll("button.opt").forEach((b) => b.addEventListener("click", () => vote(+b.dataset.idx)));
    const zipBtn = root.querySelector("#zipsave");
    if (zipBtn) zipBtn.addEventListener("click", () => saveZip(root.querySelector("#zipin").value.trim()));
    const zipIn = root.querySelector("#zipin");
    if (zipIn) zipIn.addEventListener("keydown", (e) => { if (e.key === "Enter") saveZip(zipIn.value.trim()); });
  }

  function renderPoll(p, s) {
    const r = p.results || {};
    const total = r.total || 0;
    const voted = r.your_vote != null;
    const zipOk = p.eligible;
    const zip = s.zip;
    let opts = p.options.map((o, i) => {
      const mine = r.your_vote === i ? " mine" : "";
      let inner = `<span class="lbl">${esc(o)}</span>`;
      if (r.show_split && r.counts) {
        const pct = total ? Math.round((r.counts[i] / total) * 100) : 0;
        const n = r.counts[i];
        inner = `<span class="bar" style="width:${pct}%"></span>` + inner + `<span class="pct"><small>${n} ${n === 1 ? "vote" : "votes"}</small> ${pct}%</span>`;
      }
      const disabled = voted || !zip || !zipOk ? "disabled" : "";
      return `<button class="opt${mine}" data-idx="${i}" ${disabled}>${inner}</button>`;
    }).join("");

    let notice = "";
    if (!zip) notice = `<div class="notice">Enter your ZIP to vote (everyone can view): <input id="zipin" maxlength="5" inputmode="numeric" placeholder="94040"><button id="zipsave">Save</button></div>`;
    else if (!zipOk) {
      const cityName = (p.city || "").split(",")[0].replace(/\b\w/g, (c) => c.toUpperCase());
      const zips = p.geo_scope || [];
      const area = zips.length > 6 ? `${cityName || "this area"} residents (ZIPs ${zips[0]} to ${zips[zips.length - 1]})` : `residents of ${zips.join(", ")}`;
      notice = `<div class="notice">Voting is limited to ${esc(area)}. Your ZIP (${esc(zip)}) is outside this area. You can still see the results.</div>`;
    }

    let status;
    if (r.status === "shown") status = `${total} neighbors voted` + (!zipOk && zip ? " · results visible to non-residents" : "");
    else if (voted) status = `Poll open — you're one of the first ${total} to vote. Results appear once ${r.min_votes} neighbors have voted.`;
    else if (r.status === "vote_to_see") status = `${total} neighbors voted · vote to see the split`;
    else status = `Poll open — be one of the first to vote (${total} so far)`;

    const date = p.decision_date ? ` · Decision expected ${esc(p.decision_date)}` : "";
    const critic = p.critic_log || [];
    const caught = critic.flatMap((c) => c.issues || []).map((i) => i.type.replace(/_/g, " "));
    const criticLine = critic.length
      ? `Neutrality check: ${critic.length} critic pass${critic.length > 1 ? "es" : ""}${caught.length ? ", revised for: " + [...new Set(caught)].join(", ") : ", no issues"}${p.critic_passed ? "" : " (final draft still flagged)"}`
      : "";
    const trace = s.showTrace && critic.length
      ? `<details><summary>How this poll was made</summary><div class="trace">${esc(critic.map((c) =>
          `attempt ${c.attempt}: ${c.passed ? "PASS" : "FAIL"} — ${c.summary}` +
          (c.issues || []).map((i) => `\n   • [${i.severity || "major"}] ${i.type}: ${i.detail}`).join("")).join("\n"))}</div></details>`
      : "";
    const sources = (p.sources || []).filter((x) => /^https?:/.test(x)).slice(0, 4)
      .map((u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\//, "").slice(0, 50))}</a>`).join(" · ");

    return `<p class="q">${esc(p.question)}</p>${notice}${opts}
      <div class="meta">${esc(status)}${date}</div>
      <div class="ctx"><div><b>The case for</b>${esc(p.context.for)}</div><div><b>The case against</b>${esc(p.context.against)}</div></div>
      <div class="meta">${esc(criticLine)}${sources ? " · Sources: " + sources : ""}</div>${trace}`;
  }

  // ---------- actions ----------
  async function refresh() {
    try {
      state.settings = await NB.settings();
      if (state.poll) {
        state.poll = await NB.api("GET", `/api/polls/${state.poll.poll_id}?voter_id=${encodeURIComponent(state.settings.voterId)}&zip=${encodeURIComponent(state.settings.zip || "")}`);
      }
      render();
    } catch (e) { state.error = e.message; render(); state.error = null; }
  }

  async function saveZip(z) {
    if (!/^\d{5}$/.test(z)) { state.error = "ZIP must be 5 digits"; render(); state.error = null; return; }
    const r = await NB.send({ type: "saveSettings", settings: { zip: z } });
    if (!r || !r.ok) { state.error = (r && r.error) || "could not save ZIP"; render(); state.error = null; return; }
    await refresh();
  }

  async function vote(idx) {
    const { poll, settings } = state;
    if (!poll || !settings.zip) return;
    try {
      const r = await NB.api("POST", `/api/polls/${poll.poll_id}/vote`, { voter_id: settings.voterId, option_idx: idx, zip: settings.zip });
      state.poll = { ...poll, results: r.results };
      render();
    } catch (e) {
      state.error = e.message; render(); state.error = null;
    }
  }

  async function run() {
    try {
      state.settings = await NB.settings();
    } catch (e) {
      // Happens when the extension was reloaded while this tab was open: the old content script is orphaned.
      state.settings = { zip: "", showTrace: true, position: "top", voterId: "" };
      state.error = "the extension was updated; reload this page";
      return render();
    }
    render();
    let art = null;
    for (let i = 0; i < 5; i++) {
      art = NB.extractArticle();
      if (art && art.text.length >= 40) break;
      await new Promise((r) => setTimeout(r, 1200));
    }
    if (!art || art.text.length < 40) { state.error = "could not extract article text"; return render(); }
    state.extracted = art; state.stage = "loading"; render();
    try {
      const res = await NB.api("POST", "/api/polls/get-or-create", {
        article_id: articleId, url: location.href, headline: art.headline, text: art.text,
        city_hint: art.cityHint || "", voter_id: state.settings.voterId, zip: state.settings.zip,
      });
      if (!res.pollable) { state.stage = "declined"; state.triage = res.triage; }
      else { state.stage = "ready"; state.poll = res.poll; }
    } catch (e) { state.error = e.message; }
    render();
  }

  // Popup saved new settings: refresh eligibility and results without a page reload.
  chrome.storage.onChanged.addListener(() => refresh());

  // Re-run on SPA navigation between articles.
  let last = location.href;
  setInterval(() => { if (location.href !== last) { last = location.href; location.reload(); } }, 1000);

  run();
})();

// Feed pages: find article cards, batch-lookup which have polls, badge them with the vote COUNT only (never the split).
(function () {
  const NB = window.NBPolls;
  const selfId = NB.articleIdFromUrl(location.href);
  const known = new Map(); // article_id -> {poll_id,total} | null
  let timer = null;

  function cardFor(link) {
    return link.closest("section, article, li") || link.parentElement;
  }

  function badge(card, info) {
    if (card.querySelector(".nb-poll-badge")) return;
    const b = document.createElement("div");
    b.className = "nb-poll-badge";
    b.textContent = info.total >= 30 ? `📊 ${info.total} neighbors voted` : `📊 Poll open — be one of the first to vote`;
    b.style.cssText = "display:inline-block;margin:6px 0 0;padding:4px 10px;border-radius:999px;background:#4f46e5;color:#fff;font:700 12px/1.4 -apple-system,BlinkMacSystemFont,Roboto,sans-serif;box-shadow:0 2px 6px rgba(79,70,229,.3);";
    const title = card.querySelector("h1,h2,h3") || card.querySelector("a[href]");
    (title || card).insertAdjacentElement("afterend", b);
  }

  async function scan() {
    const links = [...document.querySelectorAll('a[href*="newsbreak.com/"], a[href^="/"]')];
    const byId = new Map();
    for (const a of links) {
      const id = NB.articleIdFromUrl(a.href);
      if (!id || id === selfId) continue;
      if (!byId.has(id)) byId.set(id, a);
    }
    const unknown = [...byId.keys()].filter((id) => !known.has(id));
    if (unknown.length) {
      try {
        const res = await NB.api("POST", "/api/polls/batch", { article_ids: unknown });
        for (const id of unknown) known.set(id, res[id] || null);
      } catch { return; }
    }
    for (const [id, a] of byId) {
      const info = known.get(id);
      if (info) badge(cardFor(a), info);
    }
  }

  const schedule = () => { clearTimeout(timer); timer = setTimeout(scan, 600); };
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
  schedule();
})();

// Article extraction. Primary: JSON-LD NewsArticle (NewsBreak embeds the full body).
// Fallback: <h1> + the container with the most paragraph text, in case markup changes.
window.NBPolls = window.NBPolls || {};

(function () {
  const BOILERPLATE = /getting your trinity audio player ready/i;

  function htmlToText(html) {
    const doc = new DOMParser().parseFromString(html, "text/html");
    doc.querySelectorAll("script,style,figure,img,iframe,noscript").forEach((n) => n.remove());
    const blocks = [...doc.querySelectorAll("p,h2,h3,li,blockquote")];
    const parts = (blocks.length ? blocks.map((b) => b.textContent) : [doc.body.textContent])
      .map((t) => t.replace(/\s+/g, " ").trim())
      .filter((t) => t.length > 1 && !BOILERPLATE.test(t));
    return parts.join("\n\n");
  }

  function cleanHeadline(h) {
    return (h || "").replace(/\s*[-|]\s*NewsBreak\s*$/i, "").trim();
  }

  function fromJsonLd() {
    let hint = "";
    let article = null;
    for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
      let j;
      try { j = JSON.parse(s.textContent); } catch { continue; }
      for (const it of Array.isArray(j) ? j : [j]) {
        if (!it || typeof it !== "object") continue;
        if (it["@type"] === "BreadcrumbList" && Array.isArray(it.itemListElement)) {
          for (const el of it.itemListElement) {
            const name = el && (el.name || (el.item && el.item.name));
            if (name && /^[A-Za-z .'-]+, [A-Z]{2}$/.test(name)) hint = name;
          }
        }
        if (it["@type"] === "NewsArticle" || it["@type"] === "Article") {
          const text = it.articleBody ? htmlToText(it.articleBody) : "";
          if (text.length > 200) article = { headline: cleanHeadline(it.headline), text, url: it.url || location.href, method: "jsonld" };
          else if (!article) {
            // Some publishers only syndicate the headline + description to the web page.
            const desc = (it.description || document.querySelector('meta[name="description"]')?.content || "").replace(/getting your trinity audio player ready\.*\s*/i, "").trim();
            if (desc.length > 40) article = { headline: cleanHeadline(it.headline), text: desc, url: it.url || location.href, method: "jsonld-description" };
          }
        }
      }
    }
    if (article) article.cityHint = hint;
    return article;
  }

  function fromLargestBlock() {
    let best = "", bestLen = 0;
    for (const el of document.querySelectorAll("article,section,div")) {
      const ps = [...el.querySelectorAll(":scope > p")];
      if (ps.length < 3) continue;
      const t = ps.map((p) => p.innerText.trim()).filter((x) => x.length > 40 && !BOILERPLATE.test(x)).join("\n\n");
      if (t.length > bestLen) { best = t; bestLen = t.length; }
    }
    const h1 = document.querySelector("h1");
    return { headline: cleanHeadline(h1 ? h1.innerText : document.title), text: best, url: location.href, method: "largest-block", cityHint: "" };
  }

  window.NBPolls.extractArticle = function () {
    const a = fromJsonLd();
    if (a) return a;
    return fromLargestBlock();
  };

  window.NBPolls.articleIdFromUrl = function (url) {
    const m = (url || "").split("?")[0].match(/\/(\d{10,})(?:-|$)/);
    return m ? m[1] : null;
  };

  window.NBPolls.send = (msg) => new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
  window.NBPolls.api = async (method, path, body) => {
    const r = await window.NBPolls.send({ type: "api", method, path, body });
    if (!r || !r.ok) throw new Error((r && r.error) || "extension messaging failed");
    return r.data;
  };
  window.NBPolls.settings = async () => {
    const r = await window.NBPolls.send({ type: "settings" });
    if (!r || !r.ok) throw new Error((r && r.error) || "extension messaging failed");
    return r.data;
  };
})();

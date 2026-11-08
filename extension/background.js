// Service worker: all backend calls go through here so page CSP/CORS never gets in the way.
// Settings live in chrome.storage.local (sync can be disabled by managed profiles); legacy sync values are read as a fallback.
const DEFAULTS = { backendUrl: "http://localhost:8000", zip: "", showTrace: true, position: "top" };

async function getSettings() {
  const sync = await chrome.storage.sync.get(null).catch(() => ({}));
  const local = await chrome.storage.local.get(null).catch(() => ({}));
  const s = { ...DEFAULTS };
  for (const k of Object.keys(DEFAULTS)) {
    if (local[k] !== undefined && local[k] !== "") s[k] = local[k];
    else if (sync[k] !== undefined && sync[k] !== "") s[k] = sync[k];
  }
  return s;
}

async function api(method, path, body) {
  const { backendUrl } = await getSettings();
  const r = await fetch(backendUrl.replace(/\/$/, "") + path, {
    method,
    headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "1" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
  return data;
}

async function voterId() {
  const { voterId } = await chrome.storage.local.get("voterId");
  if (voterId) return voterId;
  const id = crypto.randomUUID();
  await chrome.storage.local.set({ voterId: id });
  return id;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    try {
      if (msg.type === "api") sendResponse({ ok: true, data: await api(msg.method, msg.path, msg.body) });
      else if (msg.type === "settings") sendResponse({ ok: true, data: { ...(await getSettings()), voterId: await voterId() } });
      else if (msg.type === "saveSettings") {
        await chrome.storage.local.set(msg.settings || {});
        sendResponse({ ok: true, data: { ...(await getSettings()), voterId: await voterId() } });
      } else sendResponse({ ok: false, error: "unknown message" });
    } catch (e) {
      sendResponse({ ok: false, error: String(e.message || e) });
    }
  })();
  return true; // keep the channel open for the async response
});

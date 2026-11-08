const send = (msg) => new Promise((resolve) => chrome.runtime.sendMessage(msg, resolve));
send({ type: "settings" }).then((r) => {
  const s = (r && r.data) || {};
  zip.value = s.zip || ""; backendUrl.value = s.backendUrl || "http://localhost:8000";
  showTrace.checked = s.showTrace !== false; position.value = s.position || "top";
  vid.textContent = s.voterId ? "anonymous voter id: " + s.voterId.slice(0, 8) + "…" : "";
});
save.onclick = async () => {
  const z = zip.value.trim();
  if (z && !/^\d{5}$/.test(z)) { ok.textContent = "ZIP must be 5 digits"; ok.style.color = "#b91c1c"; return; }
  const r = await send({ type: "saveSettings", settings: { zip: z, backendUrl: backendUrl.value.trim() || "http://localhost:8000", showTrace: showTrace.checked, position: position.value } });
  ok.style.color = r && r.ok ? "#15803d" : "#b91c1c";
  ok.textContent = r && r.ok ? `Saved (ZIP ${r.data.zip || "not set"}). Open pages update automatically.` : "Save failed: " + (r && r.error);
};

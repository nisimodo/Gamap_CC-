// Android アプリ用の起動処理: 店舗データを公開サイトから読み込んでから画面（js/app.js）を動かす
//   1. 公開サイトの最新データ（取得できたらオフライン用に保存）
//   2. 取得できなければ、前回保存したデータとアプリ同梱のデータのうち新しい方
// Web サイト版は index.html から data/stores.js と js/app.js を直接読み込むので、このファイルは使わない
(async () => {
  const REMOTE = "https://nisimodo.github.io/Gamap_CC-/data/stores.js";
  const CACHE_NAME = "gamap-data";
  const TIMEOUT_MS = 6000;

  const runScript = text => {
    const el = document.createElement("script");
    el.textContent = text;
    document.head.appendChild(el);
  };
  const loadScript = src => new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = src;
    el.onload = resolve;
    el.onerror = reject;
    document.head.appendChild(el);
  });
  const generatedOf = text => (text.match(/"generated":"([^"]+)"/) || [])[1] || "";

  document.getElementById("count").textContent = "読み込み中…";
  let cache = null;
  try { cache = await caches.open(CACHE_NAME); } catch { /* Cache API が使えない環境 */ }

  let text = null;
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    const res = await fetch(`${REMOTE}?t=${Date.now()}`, { cache: "no-store", signal: ctrl.signal });
    clearTimeout(timer);
    if (res.ok) {
      text = await res.text();
      if (!text.includes("window.TAIKO_DATA")) text = null;
      else if (cache) cache.put("stores.js", new Response(text)).catch(() => {});
    }
  } catch { /* オフライン・タイムアウト */ }

  if (text) {
    runScript(text);
  } else {
    await loadScript("data/stores.js").catch(() => {});
    const saved = cache && await cache.match("stores.js").then(r => r && r.text()).catch(() => null);
    if (saved && generatedOf(saved) > (window.TAIKO_DATA?.generated || "")) runScript(saved);
  }

  await loadScript("js/app.js");
})();

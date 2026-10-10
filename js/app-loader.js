// Android アプリ用の起動処理: 画面（HTML・CSS・JavaScript）と店舗データを公開サイトの最新版で動かす
//   1. 公開サイトから 4 ファイルをまとめて取得できたら、その版で表示し、オフライン用に保存
//   2. 取得できなければ、保存済みの版（アプリ同梱の版より新しい場合）
//   3. どちらもなければ、アプリ同梱の版
// 4 ファイルがそろわないと切り替えないので、一部だけ新しくなって表示が崩れることはない。
// 地図ライブラリやスマホの機能（位置情報など）はアプリ同梱のものを使うため、それらを変えたときは APK の更新が必要。
// Web サイト版は index.html から data/stores.js と js/app.js を直接読み込むので、このファイルは使わない。
(async () => {
  const BASE = "https://nisimodo.github.io/Gamap_CC-/";
  const FILES = ["index.html", "css/style.css", "js/app.js", "data/stores.js"];
  const CACHE_NAME = "gamap-web";
  const TIMEOUT_MS = 6000;

  const runScript = text => {
    const el = document.createElement("script");
    el.textContent = text;
    document.head.appendChild(el);
  };
  // 実行時のエラーも拾う（インラインのスクリプトのエラーは例外ではなく window の error イベントになる）
  const runChecked = text => {
    let err = null;
    const onError = e => { err = err || e.error || new Error(e.message); };
    window.addEventListener("error", onError);
    try { runScript(text); } finally { window.removeEventListener("error", onError); }
    if (err) throw err;
  };
  const loadScript = src => new Promise((resolve, reject) => {
    const el = document.createElement("script");
    el.src = src;
    el.onload = resolve;
    el.onerror = reject;
    document.head.appendChild(el);
  });

  // 取得した版で画面を組み立てる（HTML の本文・CSS を差し替えてから、データと app.js を実行）
  function applyRemote(set) {
    const doc = new DOMParser().parseFromString(set["index.html"], "text/html");
    doc.querySelectorAll("script").forEach(el => el.remove());
    document.body.replaceChildren(...[...doc.body.childNodes].map(n => document.importNode(n, true)));
    if (doc.title) document.title = doc.title;
    const link = document.querySelector('link[href="css/style.css"]');
    const style = document.createElement("style");
    style.textContent = set["css/style.css"];
    if (link) link.replaceWith(style); else document.head.appendChild(style);
    runChecked(set["data/stores.js"]);
    runChecked(set["js/app.js"]);
  }

  const looksValid = set =>
    set["index.html"].includes('id="map"') && set["data/stores.js"].includes("window.TAIKO_DATA") && set["js/app.js"].length > 1000;

  // 前回、公開サイト版の表示に失敗して読み込み直したときは、同梱の版だけを使う
  let useBundledOnly = false;
  try { useBundledOnly = sessionStorage.getItem("gamap-fallback") === "1"; sessionStorage.removeItem("gamap-fallback"); } catch {}

  const count = document.getElementById("count");
  if (count) count.textContent = "読み込み中…";
  let cache = null;
  try { cache = await caches.open(CACHE_NAME); } catch { /* Cache API が使えない環境 */ }

  // 1. 公開サイトの最新版
  let set = null;
  if (!useBundledOnly) try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
    const t = Date.now();
    const texts = await Promise.all(FILES.map(f =>
      fetch(`${BASE}${f}?t=${t}`, { cache: "no-store", signal: ctrl.signal }).then(r => {
        if (!r.ok) throw new Error(`${f}: ${r.status}`);
        return r.text();
      })));
    clearTimeout(timer);
    set = Object.fromEntries(FILES.map((f, i) => [f, texts[i]]));
    if (!looksValid(set)) set = null;
    else if (cache) cache.put("set.json", new Response(JSON.stringify({ fetchedAt: new Date().toISOString(), files: set }))).catch(() => {});
  } catch { /* オフライン・タイムアウト */ }

  // 2. 保存済みの版（アプリを更新した直後など、同梱の版の方が新しいときは使わない）
  if (!set && cache && !useBundledOnly) {
    try {
      const saved = await cache.match("set.json").then(r => r && r.json());
      if (saved && saved.fetchedAt > (window.GAMAP_BUILD || "") && looksValid(saved.files)) set = saved.files;
    } catch { /* 壊れていたら使わない */ }
  }

  if (set) {
    try {
      applyRemote(set);
      return;
    } catch (e) {
      // 途中まで差し替えた画面を元に戻すため、同梱の版を使う印を付けて読み込み直す
      console.error("公開サイト版の表示に失敗したため、アプリ同梱の版で表示します", e);
      await cache?.delete("set.json").catch(() => {});
      try { sessionStorage.setItem("gamap-fallback", "1"); } catch {}
      location.reload();
      return;
    }
  }

  // 3. アプリ同梱の版
  await loadScript("data/stores.js").catch(() => {});
  await loadScript("js/app.js");
})();

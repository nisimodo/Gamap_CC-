// オフラインでも前回のデータで開けるようにするサービスワーカー
// 画面のファイル・ライブラリはキャッシュを優先し、裏で新しいものに更新する。
// 店舗データ (data/stores.js) はネットワークを優先し、つながらないときだけキャッシュを使う。
const VERSION = "v3";
const APP_CACHE = `app-${VERSION}`;
const TILE_CACHE = "tiles";
const TILE_LIMIT = 800;  // 地図画像は見た範囲を最大この枚数まで保存

const APP_SHELL = [
  "./", "index.html", "css/style.css", "js/app.js", "data/stores.js", "manifest.webmanifest",
  "icons/icon-192.png", "icons/apple-touch-icon.png", "icons/favicon-32.png",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.Default.min.css",
  "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.min.js",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(APP_CACHE).then(c => c.addAll(APP_SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k.startsWith("app-") && k !== APP_CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

async function networkFirst(req) {
  const cache = await caches.open(APP_CACHE);
  try {
    const res = await fetch(req, { cache: "no-cache" });
    if (res.ok) cache.put(req, res.clone());
    return res;
  } catch {
    return (await cache.match(req, { ignoreSearch: true })) || Response.error();
  }
}

async function staleWhileRevalidate(req) {
  const cache = await caches.open(APP_CACHE);
  const cached = await cache.match(req, { ignoreSearch: true });
  const fresh = fetch(req).then(res => {
    if (res.ok) cache.put(req, res.clone());
    return res;
  }).catch(() => cached || Response.error());
  return cached || fresh;
}

async function tile(req) {
  const cache = await caches.open(TILE_CACHE);
  const cached = await cache.match(req);
  if (cached) return cached;
  const res = await fetch(req);
  if (res.ok || res.type === "opaque") {
    await cache.put(req, res.clone());
    const keys = await cache.keys();
    for (const k of keys.slice(0, Math.max(0, keys.length - TILE_LIMIT))) await cache.delete(k);
  }
  return res;
}

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin === location.origin) {
    if (url.pathname.endsWith("/data/stores.js") || req.mode === "navigate") e.respondWith(networkFirst(req));
    else e.respondWith(staleWhileRevalidate(req));
  } else if (url.hostname === "cdnjs.cloudflare.com") {
    e.respondWith(staleWhileRevalidate(req));
  } else if (url.hostname === "cyberjapandata.gsi.go.jp" || url.hostname === "tile.openstreetmap.org") {
    e.respondWith(tile(req));
  }
  // それ以外（地名検索など）はそのままネットワークへ
});

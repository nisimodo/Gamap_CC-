// サイト本体（../index.html など）を app/www にコピーし、CDN のライブラリをアプリ内に同梱する
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const APP = join(dirname(fileURLToPath(import.meta.url)), "..");
const SITE = join(APP, "..");
const WWW = join(APP, "www");
const CACHE = join(APP, "vendor-cache");

const CDN = "https://cdnjs.cloudflare.com/ajax/libs/";
const VENDOR = [
  "leaflet/1.9.4/leaflet.min.css",
  "leaflet/1.9.4/leaflet.min.js",
  "leaflet/1.9.4/images/layers.png",
  "leaflet/1.9.4/images/layers-2x.png",
  "leaflet.markercluster/1.5.3/MarkerCluster.min.css",
  "leaflet.markercluster/1.5.3/MarkerCluster.Default.min.css",
  "leaflet.markercluster/1.5.3/leaflet.markercluster.min.js",
];

rmSync(WWW, { recursive: true, force: true });
mkdirSync(WWW, { recursive: true });
for (const p of ["css", "js", "data", "icons", "manifest.webmanifest"]) cpSync(join(SITE, p), join(WWW, p), { recursive: true });

for (const p of VENDOR) {
  const cached = join(CACHE, p);
  if (!existsSync(cached)) {
    const res = await fetch(CDN + p);
    if (!res.ok) throw new Error(`${p} の取得に失敗しました: ${res.status}`);
    mkdirSync(dirname(cached), { recursive: true });
    writeFileSync(cached, Buffer.from(await res.arrayBuffer()));
  }
  mkdirSync(dirname(join(WWW, "vendor", p)), { recursive: true });
  cpSync(cached, join(WWW, "vendor", p));
}

const html = readFileSync(join(SITE, "index.html"), "utf8").replaceAll(CDN, "vendor/");
if (html.includes("cdnjs.cloudflare.com")) throw new Error("index.html に置き換えられなかった CDN の参照があります");
writeFileSync(join(WWW, "index.html"), html);
console.log("www を作成しました");

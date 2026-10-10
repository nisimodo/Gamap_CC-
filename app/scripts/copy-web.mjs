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

const html = readFileSync(join(SITE, "index.html"), "utf8").replaceAll(CDN, "vendor/")
  // アプリでは起動時に公開サイトから最新の店舗データを読み込む（js/app-loader.js が data/stores.js と js/app.js を読む）
  .replace(/<script src="data\/stores\.js"><\/script>\s*<script src="js\/app\.js"><\/script>/,
    '<script src="js/build-info.js"></script>\n  <script src="js/app-loader.js"></script>');
if (!html.includes("app-loader.js")) throw new Error("index.html の読み込み部分を置き換えられませんでした");
if (html.includes("cdnjs.cloudflare.com")) throw new Error("index.html に置き換えられなかった CDN の参照があります");
writeFileSync(join(WWW, "index.html"), html);
// アプリに同梱した画面・データの作成日時（js/app-loader.js が、保存済みの公開サイト版と比べるのに使う）
writeFileSync(join(WWW, "js", "build-info.js"), `window.GAMAP_BUILD = ${JSON.stringify(new Date().toISOString())};\n`);
console.log("www を作成しました");

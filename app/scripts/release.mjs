// ビルドした APK を公開用フォルダ（../apk）に置き、アプリの更新確認に使う version.json を書く
//   npm run release -- "この版の変更点"
// その後 git で commit・push すると、GitHub Pages から配布され、アプリ起動時に更新が案内される
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const APP = join(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(APP, "..", "apk");

const gradle = readFileSync(join(APP, "android", "app", "build.gradle"), "utf8");
const versionCode = Number(gradle.match(/versionCode\s+(\d+)/)[1]);
const versionName = gradle.match(/versionName\s+"([^"]+)"/)[1];
const notes = process.argv.slice(2).join(" ").trim();

mkdirSync(OUT, { recursive: true });
copyFileSync(join(APP, "taiko-map.apk"), join(OUT, "gamap.apk"));
writeFileSync(join(OUT, "version.json"), JSON.stringify({
  versionCode, versionName, apk: "gamap.apk", notes, released: new Date().toISOString().slice(0, 10),
}, null, 2) + "\n");
console.log(`apk/gamap.apk と apk/version.json を作成しました（${versionName} / ${versionCode}）`);

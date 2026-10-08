# Gamap

太鼓の達人の設置店舗マップ

xlsx の設置店舗リストを地図上のピンで表示し、ピンを選ぶと筐体情報（料金・曲数・台数・シリアル・備考）を確認できる静的サイトです。
有料 API・API キーは一切使っていません。

| 用途 | 使っているもの（すべて無料・キー不要） |
| --- | --- |
| 地図表示 | [Leaflet](https://leafletjs.com/) + [国土地理院タイル](https://maps.gsi.go.jp/development/ichiran.html)（OpenStreetMap タイルに切替可） |
| ピンのまとめ表示 | Leaflet.markercluster |
| 市区町村の位置 | 国土地理院 住所検索 API |
| 店舗の位置 | OpenStreetMap のデータ（Overpass API）と店舗名を照合 |

## 見方

- ピンの数字は**台数**です。
- 塗りつぶしのピン … OpenStreetMap で店舗（または入居している商業施設）が見つかった位置
- 点線のピン … 見つからなかったため**市区町村付近に仮配置**した位置（ポップアップの「Googleマップで探す」で正確な場所を確認できます）
- グレーのピン … 情報募集中（シリアル等が不明）の店舗
- オレンジの縁取り … 閉店予定の店舗
- 検索欄は店舗名・市区町村・シリアル番号で絞り込めます。

## サイトを開く

`data/stores.js` に変換済みデータが入っているので、`index.html` をそのままブラウザで開けば動きます。
GitHub Pages などの静的ホスティングにフォルダごと置くだけで公開できます。

ローカルサーバーで確認する場合:

```bash
python3 -m http.server 8765
```

## 自動更新（OneDrive の共有リンクから取得）

`tools/config.json` の `shareUrl` に設定した OneDrive の共有 xlsx を取得し、更新されていれば `data/stores.js` を作り直します。

```bash
python3 tools/update.py
```

- 共有ファイルの更新を検知（eTag で比較）し、変わっていないときは何もしません。`--force` で強制的に作り直します。
- 共有リンクは `https://1drv.ms/...` 形式でも、ブラウザのアドレスバーの `https://onedrive.live.com/...redeem=...` 形式でも使えます。
- ログイン不要の匿名アクセスで取得しています（OneDrive Web と同じ仕組み）。非公式な方法のため、Microsoft 側の仕様変更で使えなくなる可能性があります。その場合は手動でダウンロードして下の手順で更新してください。

### GitHub で完全自動化する（無料）

1. このフォルダを GitHub のリポジトリに push する
2. リポジトリの Settings → Pages で「Deploy from a branch」→ `main` / `(root)` を選ぶ
3. Settings → Actions → General → Workflow permissions を「Read and write permissions」にする

これで `.github/workflows/update.yml` が 3 時間ごとに `tools/update.py` を実行し、xlsx が更新されていればデータをコミットします。GitHub Pages が自動で公開し直すので、サイトは常に最新になります（Actions 画面から手動実行も可能）。

## xlsx を手動で更新したとき

```bash
python3 tools/build_data.py "/path/to/太鼓の達人.xlsx"
```

- `data/stores.js` が作り直されます。
- 取得済みの位置は `tools/geocode_cache.json`・`tools/osm_poi.json` に保存されているので、2 回目以降はすぐ終わります。
- OpenStreetMap の施設データを最新にしたいときは `--refresh-osm` を付けてください（十数分かかります）。
- `--nominatim` を付けると、見つからなかった店舗を OpenStreetMap Nominatim でも検索します（利用規約により 1 秒 1 件なので時間がかかります）。

## Android アプリ（APK）

`app/` フォルダに Capacitor（無料）を使った Android アプリのプロジェクトがあります。サイトと同じ画面・データを同梱したアプリになります。

```bash
cd app
npm install
npm run build:apk
```

- `app/taiko-map.apk` ができます。スマホに送ってインストールできます（「提供元不明のアプリ」の許可が必要です）。
- 必要なもの: Node.js、JDK 21、Android SDK（Android Studio を入れると揃います）
- アプリアイコンは `app/resources/icon.png` です。差し替えたら `npm run icons` → `npm run build:apk` で反映されます。
- アプリ内では端末の位置情報機能で現在地を取得します。
- 店舗データはビルド時点のものが入ります。データを更新したら `tools/update.py` の後にもう一度 `npm run build:apk` してください。
- 今の APK はデバッグ署名です。Google Play で配布する場合はリリース用の署名鍵を作ってビルドする必要があります。

## 構成

```
index.html          画面
css/style.css       スタイル
js/app.js           地図・検索・ポップアップ
data/stores.js      xlsx から変換した店舗データ
tools/build_data.py xlsx → stores.js 変換・位置取得スクリプト（Python 標準ライブラリのみ）
tools/update.py     OneDrive から取得して build_data.py を実行
tools/config.json   共有リンクの設定
.github/workflows/update.yml  GitHub Actions による定期自動更新
app/                Android アプリ（Capacitor）。npm run build:apk で APK を作成
```

地図データ: © 国土地理院 / © OpenStreetMap contributors

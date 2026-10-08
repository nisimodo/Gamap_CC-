#!/usr/bin/env python3
"""太鼓の達人 設置店舗 xlsx → data/stores.js 変換スクリプト

使い方:
    python3 tools/build_data.py "/path/to/太鼓の達人.xlsx"
    オプション:
      --refresh-osm  OpenStreetMap の施設データを取り直す（初回は自動取得。数分〜十数分かかる）
      --nominatim    見つからなかった店舗を Nominatim でも検索する（1 秒 1 件なので時間がかかる）
    OneDrive の共有リンクから自動で取得して変換するときは tools/update.py を使います。

座標は無料のサービスのみで取得します（APIキー不要）。
  1. 市区町村の代表点: 国土地理院 住所検索API
  2. 店舗の位置:       OpenStreetMap（Overpass API）のゲームセンター・商業施設等と店舗名を照合
取得結果は tools/geocode_cache.json / tools/osm_poi.json に保存され、次回以降は再利用されます。
店舗が見つからない場合は市区町村の代表点の周囲に配置し「おおよその位置」として表示します。
"""
import json
import math
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_PATH = ROOT / "tools" / "geocode_cache.json"
OUT_PATH = ROOT / "data" / "stores.js"

REGION_SHEETS = ["北海道・東北", "関東", "信越・北陸", "東海", "関西", "中国・四国", "九州・沖縄"]
UA = "taiko-arcade-map/1.0 (personal non-commercial project)"

# 店舗名の先頭に付く運営ブランド名。外すとモール名などになり検索に当たりやすい
BRANDS = [
    "モーリーファンタジー・f", "モーリーファンタジー", "GiGO", "namco", "タイトーステーション", "タイトーＦステーション",
    "タイトーFステーション", "タイトー", "ラウンドワンスタジアム", "ラウンドワン", "アピナ", "楽市楽座", "ソユーゲームフィールド",
    "ふぇすたらんど", "NICOPA", "ハローズガーデン", "アミパラ", "ファンタジープラザ", "プラサカプコン", "アミュージアム",
    "ゲオ", "PALO", "キッズーナ", "ファミリーランド", "アドアーズ", "あそびパーク", "セガ", "アミューズメントシティ",
    "アミューズメント", "ゲームパニック", "マンガ倉庫", "カプコサーカス", "ピノキオ",
]
SUFFIXES = ["ゲームコーナー", "店あそびのくに", "あそびのくに", "あそびタウン", "店"]

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


# ---------- xlsx 読み込み（標準ライブラリのみ） ----------
def read_xlsx(path):
    z = zipfile.ZipFile(path)
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}

    def col_index(ref):
        n = 0
        for ch in re.match(r"[A-Z]+", ref).group():
            n = n * 26 + ord(ch) - 64
        return n - 1

    sheets = {}
    for s in wb.find("m:sheets", NS):
        target = rels[s.get("{%s}id" % NS["r"])].lstrip("/")
        if not target.startswith("xl/"):
            target = "xl/" + target
        rows = []
        for row in ET.fromstring(z.read(target)).iter("{%s}row" % NS["m"]):
            cells = {}
            for c in row.findall("m:c", NS):
                v, t = c.find("m:v", NS), c.get("t")
                if t == "inlineStr":
                    val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                elif v is None:
                    continue
                elif t == "s":
                    val = shared[int(v.text)]
                else:
                    val = v.text
                cells[col_index(c.get("r"))] = (val or "").strip()
            if cells:
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
        sheets[s.get("name")] = rows
    return sheets


def zen2han(s):
    return s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def parse_stores(sheets):
    stores, pref_updates = [], {}
    for region in REGION_SHEETS:
        current_header = None
        for row in sheets.get(region, []):
            row = row + [""] * (13 - len(row))
            if row[0] and not row[1] and not row[6]:
                current_header = row[0].strip("　 ")
                m = re.search(r"\((\d{4}/\d{1,2}/\d{1,2})更新\)|（(\d{4}/\d{1,2}/\d{1,2})更新\)", current_header)
                key = re.split(r"[　 ]", current_header)[0]
                pref_updates[key] = (m.group(1) or m.group(2)) if m else ""
                continue
            if not (row[1] and row[6]):
                continue
            serials = [x for x in row[12:] if x]
            if row[1] in ("２３区", "23区"):  # 東京23区のシートは都道府県欄が「２３区」
                row[1] = "東京都"
            stores.append({
                "id": len(stores) + 1,
                "region": region,
                "area": re.split(r"[　 ]", current_header or "")[0],
                "pref": row[1],
                "city": row[2],
                "town": row[3],
                "status": row[4],
                "change": row[5],
                "name": row[6],
                "price": zen2han(row[7]),
                "songs": zen2han(row[8]),
                "units": zen2han(row[9]),
                "note": row[10],
                "serials": serials,
            })
    return stores, pref_updates


# ---------- 座標取得 ----------
# 1. 市区町村の代表点 … 国土地理院 住所検索API（無料・キー不要）
# 2. 店舗の位置       … OpenStreetMap のゲームセンター・商業施設などを Overpass API（無料）で一括取得し、
#                        店舗名と照合。市区町村の代表点から MAX_KM 以内のものだけ採用する
# 3. 見つからない店舗 … 市区町村の代表点付近に「おおよその位置」として配置
#    --nominatim を付けると、見つからない店舗を Nominatim（1 秒 1 件）でも検索する（時間がかかる）
OSM_PATH = ROOT / "tools" / "osm_poi.json"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERIES = [
    'nwr["leisure"~"^(amusement_arcade|bowling_alley)$"]["name"](area.jp);'
    'nwr["name"~"ラウンドワン|GiGO|ギーゴ|タイトー|namco|ナムコ|モーリーファンタジー|アピナ|楽市楽座|ゲームセンター|アミューズメント|ゲーム|あそびのくに|ファンタジー"](area.jp);',
    'nwr["shop"~"^(mall|department_store)$"]["name"](area.jp);',
    'nwr["shop"="supermarket"]["name"](area.jp);',
    'nwr["shop"~"^(games|video_games|video|books|variety_store|general|toys|electronics|doityourself)$"]["name"](area.jp);',
]
MAX_KM = 25   # 市区町村の代表点からこの距離以内の施設だけ採用


def fetch_json(url, data=None, timeout=60):
    body = urllib.parse.urlencode({"data": data}).encode() if data else None
    req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def haversine(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def geocode_city(query, cache):
    key = "gsi:" + query
    if key in cache:
        return cache[key]
    res = None
    for q in dict.fromkeys((query, re.sub(r"郡.+$", "郡", query), re.sub(r"(市|区|郡).*$", r"\1", query))):
        try:
            data = fetch_json("https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(q))
        except Exception as e:
            print("  GSI error", q, e)
            return None  # エラーはキャッシュしない
        time.sleep(0.2)
        if data:
            lon, lat = data[0]["geometry"]["coordinates"]
            res = [lat, lon]
            break
    cache[key] = res
    return res


def load_osm(refresh=False):
    """OSM の施設一覧 [[正規化名, 緯度, 経度, 種別, 元の名前], ...] を返す（tools/osm_poi.json にキャッシュ）"""
    if OSM_PATH.exists() and not refresh:
        return json.loads(OSM_PATH.read_text("utf-8"))
    pois, seen = [], set()
    for q in OVERPASS_QUERIES:
        query = ('[out:json][timeout:900];area["ISO3166-1"="JP"][admin_level=2]->.jp;(' + q + ");out center tags;")
        for attempt in range(3):
            print("  Overpass 取得中…", q[:40])
            try:
                d = fetch_json(OVERPASS_URL, query, timeout=1000)
                if not d.get("remark"):
                    break
                print("   ", d["remark"][:80])
            except Exception as e:
                print("   ", e)
            time.sleep(60)
        else:
            sys.exit("Overpass API から取得できませんでした。時間をおいて再実行してください。")
        for e in d["elements"]:
            if (e["type"], e["id"]) in seen:
                continue
            seen.add((e["type"], e["id"]))
            t = e.get("tags", {})
            lat, lon = (e["lat"], e["lon"]) if "lat" in e else (e["center"]["lat"], e["center"]["lon"])
            kind = t.get("leisure") or t.get("shop") or "other"
            for n in dict.fromkeys(filter(None, (t.get("name"), t.get("name:ja"), t.get("brand:ja", "") + t.get("branch", "")))):
                pois.append([norm(n), round(lat, 6), round(lon, 6), kind, n])
    OSM_PATH.write_text(json.dumps(pois, ensure_ascii=False, separators=(",", ":")), "utf-8")
    return pois


def norm(s):
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[（(].*?[)）]", "", s)
    s = re.sub(r"[\s・･\-‐－_/／!！☆★]", "", s)
    return re.sub(r"店$", "", s)


def name_variants(name):
    """照合に使う名前の候補（正規化済み）。ブランド名を外すとモール名になることが多い"""
    out = [norm(name)]
    n = name
    for b in sorted(BRANDS, key=len, reverse=True):
        if n.startswith(b):
            n = n[len(b):].strip(" 　・")
            break
    for s in SUFFIXES:
        if n.endswith(s) and len(n) - len(s) >= 3:
            n = n[: -len(s)].strip()
            break
    if n != name and len(norm(n)) >= 4:
        out.append(norm(n))
    return list(dict.fromkeys(out))


def similarity(v, c):
    """店舗名 v と OSM の名前 c の一致度 (0〜1)"""
    if v == c:
        return 1.0
    if len(v) >= 4 and v in c:
        return 0.75 + 0.2 * len(v) / len(c)
    if len(c) >= 3 and c in v:
        return 0.7 + 0.2 * len(c) / len(v)
    return 0.0


class PoiIndex:
    """緯度経度 0.25 度のグリッドで近傍検索"""
    def __init__(self, pois):
        self.grid = {}
        for p in pois:
            self.grid.setdefault((int(p[1] * 4), int(p[2] * 4)), []).append(p)

    def near(self, center, km):
        r = int(km / 25) + 1
        gy, gx = int(center[0] * 4), int(center[1] * 4)
        for y in range(gy - r, gy + r + 1):
            for x in range(gx - r, gx + r + 1):
                for p in self.grid.get((y, x), ()):
                    if haversine(center, (p[1], p[2])) <= km:
                        yield p


def match_store(s, index, center):
    if not center:
        return None
    best = None
    nearby = list(index.near(center, MAX_KM))
    variants = name_variants(s["name"])
    core = variants[-1]  # ブランド名などを外した固有部分（地名・施設名）
    for i, v in enumerate(variants):
        for p in nearby:
            # 固有部分を含まない名前（「GiGO」「モーリーファンタジー」だけ等）は別の支店の可能性があるので使わない
            if core not in p[0]:
                continue
            # 「姫路飾磨店」のような支店名だけの施設は、ブランド名を外した名前とは照合しない（別チェーンの店の可能性が高い）
            if i and p[3] not in ARCADE_KINDS and p[4].endswith("店") and len(p[0]) <= len(v):
                continue
            # ブランド名を外した名前が別の店名に含まれるだけの一致も除外（「ゲオ札幌麻生店」「三宮駅前書店」など。「〜南館」「〜南棟」は可）
            if i and v in p[0] and v != p[0] and not (p[0].startswith(v) and re.fullmatch(r"[東西南北本新]?[館棟]|sc", p[0][len(v):])):
                continue
            sc = similarity(v, p[0])
            if sc < 0.7:
                continue
            sc -= 0.05 * i                       # ブランド名を外した名前での一致は少し減点
            sc += 0.03 if p[3] in ARCADE_KINDS else 0
            key = (sc, -haversine(center, (p[1], p[2])))
            if best is None or key > best[0]:
                best = (key, p)
    return best[1] if best else None


ARCADE_KINDS = {"amusement_arcade", "bowling_alley", "games", "video_games"}


_last_nominatim = [0.0]


def nominatim(query, cache):
    key = "osm:" + query
    if key in cache:
        return cache[key]
    wait = 1.1 - (time.time() - _last_nominatim[0])
    if wait > 0:
        time.sleep(wait)
    url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=jp&limit=5&q="
           + urllib.parse.quote(query))
    try:
        data = fetch_json(url)
    except Exception as e:
        print("  Nominatim error", query, e)
        _last_nominatim[0] = time.time()
        return []
    _last_nominatim[0] = time.time()
    res = [[float(d["lat"]), float(d["lon"]), d.get("category", ""), d.get("type", ""), d.get("display_name", "")]
           for d in data]
    cache[key] = res
    return res


def nominatim_pick(results, center):
    best = None
    for lat, lon, cat, typ, _ in results:
        if cat in ("boundary", "place") or typ in ("administrative", "city", "town", "village", "suburb",
                                                   "quarter", "neighbourhood", "hamlet", "station"):
            continue
        d = haversine(center, (lat, lon))
        if d <= MAX_KM and (best is None or d < best[0]):
            best = (d, lat, lon)
    return best


def spread(stores):
    """同じ市区町村の代表点に置いた店舗が重ならないよう、らせん状に少しずらす"""
    groups = {}
    for s in stores:
        if s["precision"] == "city" and s["lat"] is not None:
            groups.setdefault((s["lat"], s["lng"]), []).append(s)
    for (lat, lng), members in groups.items():
        if len(members) == 1:
            continue
        for i, s in enumerate(members):
            r = 0.004 * math.sqrt(i + 1)
            a = i * 2.39996  # 黄金角
            s["lat"] = round(lat + r * math.cos(a), 6)
            s["lng"] = round(lng + r * math.sin(a) / math.cos(math.radians(lat)), 6)


def arg_value(name):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else None


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    xlsx = sys.argv[1]
    use_nominatim = "--nominatim" in sys.argv
    sheets = read_xlsx(xlsx)
    stores, pref_updates = parse_stores(sheets)
    print(f"{len(stores)} 店舗を読み込みました")

    cache = json.loads(CACHE_PATH.read_text("utf-8")) if CACHE_PATH.exists() else {}
    save_cache = lambda: CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=0), "utf-8")

    print("市区町村の位置を取得中（国土地理院）…")
    centers = {}
    for i, key in enumerate(dict.fromkeys(s["pref"] + s["city"] + s["town"] for s in stores), 1):
        pref = next(s["pref"] for s in stores if (s["pref"] + s["city"] + s["town"]) == key)
        centers[key] = geocode_city(key, cache) or geocode_city(pref, cache)
        if i % 100 == 0:
            save_cache()
            print(f"  {i}")
    save_cache()

    print("店舗の位置を照合中（OpenStreetMap）…")
    index = PoiIndex(load_osm("--refresh-osm" in sys.argv))
    for i, s in enumerate(stores, 1):
        center = centers[s["pref"] + s["city"] + s["town"]]
        pos, prec, matched = center, "city", None
        hit = match_store(s, index, center)
        if hit:
            pos, prec, matched = [hit[1], hit[2]], "store", hit[4]
        elif use_nominatim and center:
            for q in name_variants(s["name"]):
                nh = nominatim_pick(nominatim(q, cache), center)
                if nh:
                    pos, prec = [nh[1], nh[2]], "store"
                    break
            if i % 25 == 0:
                save_cache()
        s["lat"], s["lng"] = (round(pos[0], 6), round(pos[1], 6)) if pos else (None, None)
        s["precision"] = prec
        if matched and matched != s["name"]:
            s["osmName"] = matched
    save_cache()
    spread(stores)

    news, section = [], ""
    for row in sheets.get("開店・閉店", []):
        if len(row) == 1 and row[0]:
            section = {"新規設置店舗": "new", "閉店(撤去)が発表されている店舗": "closing"}.get(row[0], "closed")
            continue
        if len(row) < 5 or not row[4] or row[0] == "シリアル回収状況":
            continue
        date = row[3]
        if re.fullmatch(r"\d{5}", date):  # Excel のシリアル日付
            date = time.strftime("%Y/%m/%d", time.gmtime((int(date) - 25569) * 86400))
        news.append({"type": section, "area": row[1].replace("　", " "), "date": date, "name": row[4]})
    by_name = {s["name"]: s for s in stores}
    for n in news:
        if n["type"] != "new" and n["name"] in by_name:
            by_name[n["name"]]["closing"] = {"type": n["type"], "date": n["date"]}

    payload = {
        "generated": time.strftime("%Y-%m-%d %H:%M"),
        "source": arg_value("--source-name") or Path(xlsx).name,
        "sourceUpdated": arg_value("--source-updated") or "",
        "prefUpdates": pref_updates,
        "stores": stores,
        "news": news,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("window.TAIKO_DATA = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n", "utf-8")
    n_store = sum(1 for s in stores if s["precision"] == "store")
    print(f"完了: {OUT_PATH}  店舗位置 {n_store} / 市区町村代表点 {len(stores) - n_store}")


if __name__ == "__main__":
    main()

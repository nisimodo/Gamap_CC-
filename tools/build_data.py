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


# ---------- 店舗名の地名から位置を推定（OSM の施設が見つからなかった店舗用） ----------
# 例: 「GiGO 赤羽駅前」→ 赤羽駅、「モーリーファンタジー南砂」→ 江東区南砂
# Excel の市区町村欄が誤っている店舗（赤羽駅前なのに港区など）も、店舗名の地名の位置に置ける
STATIONS_PATH = ROOT / "tools" / "osm_stations.json"
STATIONS_JS = ROOT / "data" / "stations.js"
NAME_GUESS_KM = 40  # 市区町村の代表点からこの距離以内の駅・地名だけ採用
TOWN_NEAR_KM = 8    # 別の市区町村の町名は、この距離以内（東京23区の隣の区など）のときだけ採用
STATION_RESIDUES = {"", "駅", "駅前", "前", "東口", "西口", "南口", "北口", "中央口",
                    "駅東口", "駅西口", "駅南口", "駅北口", "駅中央口", "駅ビル", "駅南", "駅北", "駅東", "駅西"}


def load_stations(refresh=False):
    """全国の駅 [[駅名, 緯度, 経度, [事業者...]], ...]（tools/osm_stations.json にキャッシュ）"""
    if STATIONS_PATH.exists() and not refresh:
        return json.loads(STATIONS_PATH.read_text("utf-8"))
    query = ('[out:json][timeout:900];area["ISO3166-1"="JP"][admin_level=2]->.jp;'
             '(node["railway"~"^(station|halt)$"]["name"](area.jp););out body;')
    print("  Overpass から駅を取得中…")
    d = fetch_json(OVERPASS_URL, query, timeout=1000)
    out, seen = [], {}
    for e in d["elements"]:
        t = e["tags"]
        name = (t.get("name:ja") or t["name"]).strip()
        lat, lon = round(e["lat"], 5), round(e["lon"], 5)
        for la, lo, i in seen.get(name, []):  # 路線ごとに別の点があるので 1.5km 以内の同名駅はまとめる
            if abs(la - lat) < 0.015 and abs(lo - lon) < 0.015:
                if t.get("operator") and t["operator"] not in out[i][3]:
                    out[i][3].append(t["operator"])
                break
        else:
            seen.setdefault(name, []).append((lat, lon, len(out)))
            out.append([name, lat, lon, [t["operator"]] if t.get("operator") else []])
    STATIONS_PATH.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), "utf-8")
    return out


def core_name(name):
    """ブランド名・「ゲームコーナー」などを外した、店舗名の地名部分（正規化済み）"""
    n = re.sub(r"[（(].*?[)）]", "", name).strip()
    for b in sorted(BRANDS + EXTRA_BRANDS, key=len, reverse=True):
        if n.startswith(b) and len(n) > len(b):
            n = n[len(b):].strip(" 　・")
            break
    for suf in SUFFIXES:
        if n.endswith(suf) and len(n) > len(suf):
            n = n[: -len(suf)].strip()
            break
    return norm(n)


# BRANDS（OSM 照合用）に加えて、地名推定のときだけ外すブランド名
EXTRA_BRANDS = ["アミューズメントスペース", "ゲームセンター", "プレイランド", "ゲームランド", "ゲームプラザ", "シルクハット",
                "キャッツアイ", "東京レジャーランド", "レジャーランド", "ユーズランド", "ウェアハウス", "NICOPA", "ニコパ",
                "あそびパーク", "ふぇすたらんど", "テクモピア", "キャロット", "ラクガキ王国", "パラディッソ", "スーパージャンボ"]


def guess_station(core, center, station_index):
    """店舗名の地名部分が「駅名＋駅前／東口など」なら、その駅の位置"""
    best = None
    for k in range(len(core), 1, -1):
        prefix, residue = core[:k], core[k:]
        if residue not in STATION_RESIDUES:
            continue
        for st in station_index.get(prefix, ()):
            d = haversine(center, (st[1], st[2]))
            if d <= NAME_GUESS_KM and (best is None or d < best[0]):
                best = (d, st)
        if best:
            return best[1]
    return None


def gsi_places(q, cache):
    """国土地理院 住所検索の結果 [[名称, 緯度, 経度], ...]（キャッシュ付き）"""
    key = "gsi:" + q
    if key not in cache:
        try:
            data = fetch_json("https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + urllib.parse.quote(q))
            time.sleep(0.2)
        except Exception as e:
            print("  GSI error", q, e)
            return []
        cache[key] = [[x["properties"]["title"], x["geometry"]["coordinates"][1], x["geometry"]["coordinates"][0]] for x in data]
    return cache[key] or []


def names_other_city(core, s, cache):
    """店舗名の地名が、Excel の市区町村とは別の市町村の名前か（「アピナ宇都宮」が上三川町にある場合など）。
    その場合は地域名として付けられた店名なので、駅名・町名からの推定に使わない"""
    if not re.search(r"[一-龥ぁ-んァ-ン]", core):
        return False
    own = norm(s["city"] + s["town"])
    for title, _, _ in gsi_places(core, cache):
        m = re.fullmatch(re.escape(s["pref"]) + r"(?:.+郡)?(.+[市町村])", title)
        if m and norm(m.group(1)).removesuffix("市").removesuffix("町").removesuffix("村") == core \
                and norm(m.group(1)) not in own:
            return True
    return False


MUNI_PATH = ROOT / "tools" / "gsi_muni.json"
CORRECTIONS_PATH = ROOT / "tools" / "corrections.json"


def apply_correction(s, corr, center, station_index):
    """tools/corrections.json の手動修正。(位置, 精度, 説明) を返す。該当しなければ None"""
    if "lat" in corr and "lng" in corr:
        return [corr["lat"], corr["lng"]], "store", corr.get("note", "")
    if "station" in corr:
        cands = station_index.get(norm(corr["station"]), [])
        if center:
            cands = sorted(cands, key=lambda st: haversine(center, (st[1], st[2])))
        if cands:
            return [cands[0][1], cands[0][2]], "station", corr.get("note") or f"{cands[0][0]}駅付近"
        print(f"  手動修正の駅が見つかりません: {s['name']} → {corr['station']}")
    return None


def load_muni():
    """国土地理院の市区町村コード表 {コード: [都道府県, 市区町村名]}（tools/gsi_muni.json にキャッシュ）"""
    if MUNI_PATH.exists():
        return json.loads(MUNI_PATH.read_text("utf-8"))
    req = urllib.request.Request("https://maps.gsi.go.jp/js/muni.js", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        text = r.read().decode("utf-8")
    muni = {str(int(code)): [pref, name.replace("　", "")]
            for code, pref, name in re.findall(r"\[\"(\d+)\"\] = '\d+,([^,]+),\d+,([^']+)'", text)}
    MUNI_PATH.write_text(json.dumps(muni, ensure_ascii=False, separators=(",", ":")), "utf-8")
    return muni


def municipality_at(pos, muni, cache):
    """その地点の [都道府県, 市区町村名]（国土地理院 逆ジオコーダー）"""
    key = f"rev:{pos[0]:.5f},{pos[1]:.5f}"
    if key not in cache:
        try:
            d = fetch_json("https://mreversegeocoder.gsi.go.jp/reverse-geocoder/LonLatToAddress"
                           f"?lat={pos[0]}&lon={pos[1]}")
            time.sleep(0.2)
            cache[key] = (d.get("results") or {}).get("muniCd")
        except Exception as e:
            print("  逆ジオコーダー error", pos, e)
            return None
    code = cache[key]
    return muni.get(str(int(code))) if code else None


def same_municipality(found, s):
    """地点の市区町村が Excel の市区町村と同じか（「札幌市清田区」と Excel の「札幌市」、「塩竈市」と「塩竃市」は同じとみなす）"""
    variants = str.maketrans({"竃": "竈", "ヶ": "ケ", "ケ": "ケ", "檜": "桧", "﨑": "崎", "邊": "辺", "邉": "辺"})
    pref, name = found[0], found[1].translate(variants)
    excel = (s["city"] + s["town"]).translate(variants)
    city = re.match(r".+?市(?=.+区$)", name)  # 政令指定都市の「〇〇市」部分
    return pref == s["pref"] and (name in excel or (city and city.group(0) in excel) or excel in name)


def names_own_city(core, s):
    """店舗名の地名が、その店舗の市区町村名そのものか（「ラウンドワン浜松」が浜松市にある場合など）。
    市の名前を付けただけで駅前とは限らないので、駅・町名からの推定に使わない"""
    own = norm(s["city"] + s["town"])
    return any(core + suf in own for suf in ("市", "町", "村", "区"))


def guess_town(core, s, center, cache):
    """店舗名の地名部分が町名なら、その位置（国土地理院 住所検索）。
    同じ市区町村の中か、Excel の市区町村の代表点から TOWN_NEAR_KM 以内のものだけ使う"""
    if len(core) < 2 or not re.search(r"[一-龥]", core):
        return None
    best = None
    for title, lat, lon in gsi_places(core, cache):
        t = re.sub(r"[一二三四五六七八九十〇]+丁目$", "", title)
        if not (t.startswith(s["pref"]) and norm(t).endswith(core)):
            continue
        d = haversine(center, (lat, lon))
        same_city = norm(t).startswith(norm(s["pref"] + s["city"]))
        if (same_city and d <= NAME_GUESS_KM) or d <= TOWN_NEAR_KM:
            if best is None or d < best[0]:
                best = (d, title, lat, lon)
    return best[1:] if best else None


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
    """同じ点（市区町村の代表点・駅など）に置いた店舗が重ならないよう、らせん状に少しずらす"""
    groups = {}
    for s in stores:
        if s["precision"] != "store" and s["lat"] is not None:
            groups.setdefault((s["lat"], s["lng"]), []).append(s)
    for (lat, lng), members in groups.items():
        if len(members) == 1:
            continue
        step = 0.004 if members[0]["precision"] == "city" else 0.0012  # 駅・町名付近はあまり離さない
        for i, s in enumerate(members):
            r = step * math.sqrt(i + 1)
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
    stations = load_stations("--refresh-osm" in sys.argv)
    muni = load_muni()
    corrections = {k: v for k, v in json.loads(CORRECTIONS_PATH.read_text("utf-8")).items() if not k.startswith("_")} \
        if CORRECTIONS_PATH.exists() else {}
    unknown = [k for k in corrections if k not in {x["name"] for x in stores}]
    if unknown:
        print("手動修正に Excel に無い店舗名があります:", "、".join(unknown))
    station_index = {}
    for st in stations:
        station_index.setdefault(norm(st[0]), []).append(st)
    suspicious = []
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
        if prec == "city" and center:
            core = core_name(s["name"])
            skip = names_own_city(core, s) or names_other_city(core, s, cache)
            st = None if skip else guess_station(core, center, station_index)
            if st:
                pos, prec = [st[1], st[2]], "station"
                s["locNote"] = f"{st[0]}駅付近"
            else:
                town = None if skip else guess_town(core, s, center, cache)
                if town:
                    pos, prec = [town[1], town[2]], "area"
                    s["locNote"] = f"{town[0].removeprefix(s['pref'])}付近"
            if i % 50 == 0:
                save_cache()
        corr = corrections.get(s["name"])
        if corr:
            fixed = apply_correction(s, corr, center, station_index)
            if fixed:
                pos, prec, s["locNote"] = fixed
                s["manual"] = True
                s.pop("osmName", None)
                matched = None
        s["lat"], s["lng"] = (round(pos[0], 6), round(pos[1], 6)) if pos else (None, None)
        s["precision"] = prec
        if matched and matched != s["name"]:
            s["osmName"] = matched
        # 店舗名から推定した位置が Excel と別の区なら、表示する区を直す（Excel の値は元データとして残す）。
        # Excel の東京23区の表は区の欄に明らかな誤りが多いため、この表だけを対象にする。
        # ほかの地域で食い違うのは、市境の近くで隣の市の駅名を付けた店舗（アピナ津田沼が船橋市など）が多く、Excel の方が正しい
        if prec in ("station", "area") and "２３区" in s["area"] and "外" not in s["area"]:
            found = municipality_at(pos, muni, cache)
            if found and not same_municipality(found, s):
                s["fixedPref"], s["fixedCity"] = found
        # Excel の市区町村から大きく離れた位置になった店舗（市区町村欄の誤りの可能性）
        if prec in ("station", "area") and center and haversine(center, pos) > 8:
            s["farFromCity"] = True
            suspicious.append(f"{s['name']}（Excel: {s['pref']}{s['city']}{s['town']} → {s['locNote']}）")
    save_cache()
    spread(stores)
    STATIONS_JS.write_text("window.TAIKO_STATIONS = " + json.dumps(
        [[n, la, lo, "・".join(ops[:2])] for n, la, lo, ops in stations], ensure_ascii=False, separators=(",", ":")) + ";\n", "utf-8")
    counts = {p: sum(1 for x in stores if x["precision"] == p) for p in ("store", "station", "area", "city")}
    print(f"位置: 施設 {counts['store']} / 駅 {counts['station']} / 町名 {counts['area']} / 市区町村 {counts['city']}")
    fixed = [x for x in stores if x.get("fixedCity")]
    print(f"市区町村の表示を直した店舗 ({len(fixed)}):")
    for x in fixed:
        print(f"  {x['name']}: {x['pref']}{x['city']}{x['town']} → {x['fixedPref']}{x['fixedCity']}")
    if suspicious:
        print(f"Excel の市区町村と店舗名の地名が離れている店舗 ({len(suspicious)}):")
        for x in suspicious:
            print("  " + x)

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
    print(f"完了: {OUT_PATH}")


if __name__ == "__main__":
    main()

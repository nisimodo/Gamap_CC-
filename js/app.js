(() => {
  const DATA = window.TAIKO_DATA;
  const stores = DATA.stores.filter(s => s.lat != null);
  const LIST_LIMIT = 300;

  const $ = id => document.getElementById(id);
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const unitsOf = s => parseInt(String(s.units).replace(/[^0-9]/g, ""), 10) || 0;
  const isUnknown = s => s.status === "情報募集中" || s.serials.includes("不明");
  // 元データの区が店舗名と食い違う店舗は、店舗名の地名から求めた区を表示する（fixedCity）
  const addr = s => s.fixedCity ? `${s.fixedPref} ${s.fixedCity}` : [s.pref, s.city, s.town].filter(Boolean).join(" ");
  const excelAddr = s => [s.city, s.town].filter(Boolean).join(" ");

  // ---------- 地図（国土地理院タイル / OpenStreetMap：どちらも無料・キー不要） ----------
  const gsiPale = L.tileLayer("https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: '<a href="https://maps.gsi.go.jp/development/ichiran.html" target="_blank" rel="noopener">国土地理院</a>',
  });
  const osm = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
  });
  const map = L.map("map", { layers: [gsiPale], zoomControl: true, preferCanvas: false }).setView([36.2, 137.9], 5);
  L.control.layers({ "地理院 淡色地図": gsiPale, "OpenStreetMap": osm }, null, { position: "topright" }).addTo(map);
  L.control.scale({ imperial: false }).addTo(map);

  const cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50, spiderfyOnMaxZoom: true, chunkedLoading: true });
  map.addLayer(cluster);

  // ---------- ポップアップ ----------
  function popupHtml(s) {
    const serials = s.serials.length
      ? s.serials.map(x => `<span class="serial${x === "不明" ? " unk" : ""}">${esc(x)}</span>`).join("")
      : '<span class="serial unk">記載なし</span>';
    const notes = [];
    if (s.closing) notes.push(`<span class="note">${s.closing.type === "closing" ? "閉店予定" : "閉店済み"} ${esc(s.closing.date)}</span>`);
    if (s.status) notes.push(`<span class="note">${esc(s.status)}</span>`);
    if (s.change) notes.push(`<span class="note info">${esc(s.change)}</span>`);
    if (s.note) notes.push(`<span class="note info">${esc(s.note)}</span>`);
    const q = encodeURIComponent(`${s.name} ${addr(s).replace(/ /g, "")}`);
    return `<div class="pop">
      <h3>${esc(s.name)}</h3>
      <div class="addr">${esc(addr(s))}${s.fixedCity ? `<span class="orig">（元データでは${esc(excelAddr(s))}）</span>` : ""}</div>
      <div class="stats">
        <div class="stat"><b>${esc(s.price || "?")}</b><small>料金</small></div>
        <div class="stat"><b>${esc(s.songs || "?")}</b><small>曲数</small></div>
        <div class="stat"><b>${esc(s.units || "?")}</b><small>台数</small></div>
      </div>
      <div class="label">筐体シリアル</div>
      <div class="serials">${serials}</div>
      ${notes.length ? `<div class="notes">${notes.join("")}</div>` : ""}
      ${s.precision === "city" ? '<div class="approx-msg">※ 店舗の正確な位置が取得できなかったため、市区町村付近に表示しています</div>' : ""}
      ${s.precision === "area" ? `<div class="approx-msg">※ 店舗名の地名から、${esc(s.locNote)}に表示しています（正確な位置ではありません）</div>` : ""}
      ${s.precision === "station" ? `<div class="osm-msg">地図上の位置: ${esc(s.locNote)}（店舗名から推定）</div>` : ""}
      ${s.farFromCity && !s.fixedCity ? `<div class="approx-msg">※ 元データの市区町村（${esc(s.city + s.town)}）から離れた場所です。店舗名の地名をもとに表示しています</div>` : ""}
      ${s.osmName ? `<div class="osm-msg">地図上の位置: OpenStreetMap「${esc(s.osmName)}」</div>` : ""}
      <div class="links">
        <a href="https://www.google.com/maps/search/?api=1&query=${q}" target="_blank" rel="noopener">Googleマップで探す</a>
        <a class="sub" href="https://www.openstreetmap.org/?mlat=${s.lat}&mlon=${s.lng}#map=${s.precision === "city" ? 15 : 18}/${s.lat}/${s.lng}" target="_blank" rel="noopener" title="この位置を OpenStreetMap で開く">OpenStreetMap</a>
      </div>
    </div>`;
  }

  function iconFor(s) {
    const cls = ["pin"];
    if (s.precision === "city" || s.precision === "area") cls.push("approx");
    if (isUnknown(s)) cls.push("unknown");
    if (s.closing) cls.push("closing");
    const n = unitsOf(s);
    return L.divIcon({ className: "", html: `<div class="${cls.join(" ")}">${n || "?"}</div>`, iconSize: [28, 28], iconAnchor: [14, 14], popupAnchor: [0, -12] });
  }

  const markers = new Map();
  for (const s of stores) {
    const m = L.marker([s.lat, s.lng], { icon: iconFor(s), title: s.name });
    m.bindPopup(() => popupHtml(s), { maxWidth: 320, autoPanPadding: [20, 20] });
    m.on("click", () => highlight(s.id));
    markers.set(s.id, m);
  }

  // ---------- フィルタ ----------
  const regions = [...new Set(stores.map(s => s.region))];
  const prefsByRegion = {};
  for (const s of stores) (prefsByRegion[s.region] ||= new Set()).add(s.pref);
  $("region").innerHTML += regions.map(r => `<option>${esc(r)}</option>`).join("");

  function fillPrefs() {
    const r = $("region").value;
    const prefs = r ? [...prefsByRegion[r]] : regions.flatMap(x => [...prefsByRegion[x]]);
    $("pref").innerHTML = '<option value="">すべて</option>' + [...new Set(prefs)].map(p => `<option>${esc(p)}</option>`).join("");
  }
  fillPrefs();

  const norm = s => s.normalize("NFKC").toLowerCase().replace(/\s+/g, "");
  for (const s of stores) s._key = norm([s.name, addr(s), ...s.serials].join(" "));

  let current = [];
  let distances = null;  // 店舗 id → 距離 (km)。地名検索では地点から、ヒットが少ないときはヒットした店舗からの距離
  let distPrefix = "";
  // 地方・都道府県・台数・表示の絞り込み条件に合う店舗（地図に出すピン）
  function filteredBase() {
    const region = $("region").value, pref = $("pref").value;
    const minUnits = +$("units").value, extra = $("extra").value;
    const base = stores.filter(s =>
      (!region || s.region === region) &&
      (!pref || s.pref === pref) &&
      (!minUnits || unitsOf(s) >= minUnits) &&
      (!extra || (extra === "store" && s.precision === "store") || (extra === "unknown" && isUnknown(s)) || (extra === "closing" && s.closing)));
    return { base, mapKey: [region, pref, minUnits, extra].join("|") };
  }

  function apply(fit) {
    const raw = $("q").value.trim();
    const q = norm(raw);
    const { base, mapKey } = filteredBase();
    // 地図のピンは絞り込み条件（地方・台数など）だけで決め、検索語では減らさない。検索結果は一覧とズームに使う
    const matched = q ? base.filter(s => s._key.includes(q)) : base;

    placeReq++;  // 実行中の地名検索の結果は使わない
    distances = null;
    if (!matched.length && q.length >= 2) {
      showStores(base, [], mapKey);
      searchPlace(raw, base, mapKey);
      return;
    }
    clearPlace();
    if (q && matched.length < MIN_RESULTS) {
      // ヒットが少ないときは、ヒットした店舗の近くの店舗も加えて MIN_RESULTS 件にする
      const hit = new Set(matched.map(s => s.id));
      const extra = base.filter(s => !hit.has(s.id))
        .map(s => ({ s, d: Math.min(...matched.map(m => map.distance([m.lat, m.lng], [s.lat, s.lng]))) / 1000 }))
        .sort((a, b) => a.d - b.d).slice(0, MIN_RESULTS - matched.length);
      distances = new Map(extra.map(x => [x.s.id, x.d]));
      distPrefix = "近く ";
      showStores(base, [...matched, ...extra.map(x => x.s)], mapKey);
      if (extra.length) setNote(`「${esc(raw)}」に一致する店舗は ${matched.length} 件です。<br>近くの店舗を合わせて ${current.length} 件表示しています。`);
    } else {
      showStores(base, matched, mapKey);
    }
    if (fit && current.length) {
      const b = L.latLngBounds(current.map(s => [s.lat, s.lng]));
      map.fitBounds(b, fitOptions(15));
    }
  }

  // スマホで一覧が開いているときは、一覧に隠れない地図の上側に収まるよう余白をとる
  const isMobile = () => window.innerWidth <= 760;
  function fitOptions(maxZoom) {
    const pad = isMobile() ? 24 : 40;
    const covered = isMobile() && $("side").classList.contains("open") ? $("side").offsetHeight : 0;
    return { paddingTopLeft: [pad, pad], paddingBottomRight: [pad, pad + covered], maxZoom };
  }

  let shownMapKey = null;
  function showStores(onMap, inList, mapKey) {
    if (mapKey !== shownMapKey) {  // 条件が変わったときだけピンを入れ替える（検索の入力ごとに作り直さない）
      cluster.clearLayers();
      cluster.addLayers(onMap.map(s => markers.get(s.id)));
      shownMapKey = mapKey;
    }
    current = inList;
    $("count").textContent = current.length.toLocaleString();
    $("unitsTotal").textContent = current.reduce((a, s) => a + unitsOf(s), 0).toLocaleString();
    renderList();
  }

  // ---------- 地名検索：店舗名で見つからないとき、国土地理院の地名検索（無料・キー不要）で場所へ移動 ----------
  const NEARBY_KM = 10, NEARBY_MAX = 50, MIN_RESULTS = 10;
  const PREF_RE = /^(北海道|東京都|大阪府|京都府|.{2,3}県)/;
  const placeCache = new Map();
  let placeReq = 0, placeMarker = null;

  function clearPlace() {
    if (placeMarker) { map.removeLayer(placeMarker); placeMarker = null; }
    $("placeNote").hidden = true;
  }

  function setNote(html) {
    $("placeNote").innerHTML = html;
    $("placeNote").hidden = false;
  }

  // 駅の一覧（data/stations.js）は地名検索を初めて使うときに読み込む
  let stationsPromise = null;
  function loadStations() {
    stationsPromise ||= new Promise(resolve => {
      const el = document.createElement("script");
      el.src = "data/stations.js";
      el.onload = () => resolve(window.TAIKO_STATIONS || []);
      el.onerror = () => { stationsPromise = null; resolve([]); };
      document.head.appendChild(el);
    });
    return stationsPromise;
  }

  // 1. 駅名（OpenStreetMap の駅一覧）  2. 地名・住所（国土地理院）  3. その他の場所（OpenStreetMap Nominatim）の順に探す
  async function lookupPlace(q) {
    if (placeCache.has(q)) return placeCache.get(q);
    const key = norm(q).replace(/駅$/, "");
    let place = null;

    const stations = (await loadStations()).filter(st => norm(st[0]) === key);
    if (stations.length) {
      // 同じ名前の駅が複数あるときは、いま見ている地図の中心に近いもの
      const c = map.getCenter();
      const st = stations.reduce((a, b) => map.distance(c, [a[1], a[2]]) <= map.distance(c, [b[1], b[2]]) ? a : b);
      place = { title: `${st[0]}駅${st[3] ? `（${st[3]}）` : ""}`, ll: [st[1], st[2]] };
    }

    if (!place) {
      const res = await fetch("https://msearch.gsi.go.jp/address-search/AddressSearch?q=" + encodeURIComponent(q));
      if (!res.ok) throw new Error(res.status);
      // 検索語を含まない結果（「東行田」で「札幌市東区」など、一部の文字だけ一致したもの）は使わない
      const list = (await res.json()).filter(x => norm(x.properties.title).includes(key));
      // 「東京都渋谷区恵比寿」のような住所形式の結果を優先（「恵比寿岩」などの地物より）
      const best = list.find(x => PREF_RE.test(x.properties.title)) || list[0];
      if (best) place = { title: best.properties.title, ll: [best.geometry.coordinates[1], best.geometry.coordinates[0]] };
    }

    if (!place) {
      try {
        const res = await fetch("https://nominatim.openstreetmap.org/search?format=jsonv2&countrycodes=jp&limit=1&accept-language=ja&q=" + encodeURIComponent(q));
        const [hit] = res.ok ? await res.json() : [];
        if (hit) place = { title: hit.display_name.split(",").slice(0, 3).map(x => x.trim()).join(" "), ll: [+hit.lat, +hit.lon] };
      } catch { /* つながらなければ見つからなかった扱い */ }
    }

    placeCache.set(q, place);
    return place;
  }

  async function searchPlace(raw, base, mapKey) {
    const req = placeReq;
    clearPlace();
    setNote(`「${esc(raw)}」を含む店舗はありません。地名として検索中…`);
    let place;
    try {
      place = await lookupPlace(raw);
    } catch {
      if (req === placeReq) setNote(`「${esc(raw)}」を含む店舗はありません。（地名検索に接続できませんでした）`);
      return;
    }
    if (req !== placeReq) return;  // 待っている間に検索語や条件が変わった
    if (!place) {
      setNote(`「${esc(raw)}」を含む店舗・地名は見つかりませんでした。`);
      return;
    }

    const { near, rangeText } = listNearby(place.ll, base, mapKey);
    setNote(`「${esc(raw)}」を含む店舗はありません。<br>地名「<b>${esc(place.title)}</b>」から${rangeText}表示しています。`);

    placeMarker = L.marker(place.ll, {
      icon: L.divIcon({ className: "", html: '<div class="place-pin"></div>', iconSize: [22, 22], iconAnchor: [11, 22] }),
      zIndexOffset: 1000, interactive: false,
    }).addTo(map);
    flyToNearby(place.ll, near);
  }

  // 地点から NEARBY_KM 以内の店舗（最大 NEARBY_MAX 件）を距離順に一覧に出す。少なければ距離に関係なく近い順に MIN_RESULTS 件
  function listNearby(ll, base, mapKey) {
    const sorted = base.map(s => ({ s, d: map.distance(ll, [s.lat, s.lng]) / 1000 })).sort((a, b) => a.d - b.d);
    const within = sorted.filter(x => x.d <= NEARBY_KM).slice(0, NEARBY_MAX);
    const near = within.length >= MIN_RESULTS ? within : sorted.slice(0, MIN_RESULTS);
    distances = new Map(near.map(x => [x.s.id, x.d]));
    distPrefix = "";
    showStores(base, near.map(x => x.s), mapKey);
    const rangeText = within.length >= MIN_RESULTS ? ` ${NEARBY_KM}km 以内の店舗を近い順に` : `近い順に ${near.length} 店舗を`;
    return { near, rangeText };
  }

  // 地点と近い店舗 3 件が収まるように移動
  function flyToNearby(ll, near) {
    const b = L.latLngBounds([ll, ...near.slice(0, 3).map(x => [x.s.lat, x.s.lng])]);
    map.flyToBounds(near.length ? b.pad(0.2) : b, { ...fitOptions(near.length ? 15 : 14), duration: 1 });
  }

  function renderList() {
    const km = d => d < 1 ? `${Math.round(d * 1000)}m` : `${d.toFixed(1)}km`;
    const items = current.slice(0, LIST_LIMIT).map(s =>
      `<li data-id="${s.id}"><span class="name">${esc(s.name)}</span><span class="units">${unitsOf(s) || "?"}台</span>
       <span class="meta">${distances?.has(s.id) ? `<b class="dist">${distPrefix}${km(distances.get(s.id))}</b>・` : ""}${esc(addr(s))}・${esc(s.price || "料金?")}／${esc(s.songs || "曲数?")}${s.closing ? "・閉店予定" : ""}</span></li>`);
    if (current.length > LIST_LIMIT) items.push(`<li class="more">他 ${current.length - LIST_LIMIT} 件（絞り込むと表示されます）</li>`);
    if (!current.length) items.push('<li class="more">該当する店舗がありません</li>');
    $("list").innerHTML = items.join("");
  }

  function highlight(id) {
    document.querySelectorAll(".list li.active").forEach(el => el.classList.remove("active"));
    const el = document.querySelector(`.list li[data-id="${id}"]`);
    if (!el) return;
    el.classList.add("active");
    const list = $("list");  // scrollIntoView だとページ全体が動くため一覧だけをスクロール
    if (el.offsetTop < list.scrollTop || el.offsetTop + el.offsetHeight > list.scrollTop + list.clientHeight)
      list.scrollTop = el.offsetTop - list.clientHeight / 3;
  }

  function focusStore(id) {
    const m = markers.get(id);
    if (!m) return;
    if (!cluster.hasLayer(m)) {  // フィルタで隠れている場合は条件を解除して表示
      $("q").value = ""; $("region").value = ""; fillPrefs(); $("units").value = "0"; $("extra").value = "";
      apply(false);
    }
    if (isMobile()) $("side").classList.remove("open");
    cluster.zoomToShowLayer(m, () => { m.openPopup(); highlight(id); });
  }

  $("list").addEventListener("click", e => {
    const li = e.target.closest("li[data-id]");
    if (li) focusStore(+li.dataset.id);
  });

  let t;
  // 検索欄の × ボタン: 検索語を消して一覧を元に戻す（地図の位置はそのまま）
  const syncClear = () => { $("qClear").hidden = !$("q").value; };
  $("qClear").addEventListener("click", () => {
    clearTimeout(t);
    $("q").value = "";
    syncClear();
    apply(false);
  });
  $("q").addEventListener("input", syncClear);
  $("q").addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(() => {
      if (isMobile() && $("q").value.trim()) $("side").classList.add("open");  // スマホでは検索したら一覧を開く
      apply(true);
    }, 250);
  });
  // Enter（キーボードの「検索」）でキーボードを閉じ、一覧を見やすくする
  $("q").addEventListener("keydown", e => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    clearTimeout(t);
    if (isMobile() && $("q").value.trim()) $("side").classList.add("open");
    apply(true);
    $("q").blur();
  });
  $("region").addEventListener("change", () => { fillPrefs(); apply(true); });
  $("pref").addEventListener("change", () => apply(true));
  $("units").addEventListener("change", () => apply(false));
  $("extra").addEventListener("change", () => apply(false));
  $("toggleSide").addEventListener("click", () => $("side").classList.toggle("open"));

  // ---------- 新規設置・閉店情報 ----------
  const byName = new Map(stores.map(s => [s.name, s]));
  const tagText = { new: "新規", closing: "閉店予定", closed: "閉店済" };
  $("newsList").innerHTML = (DATA.news || []).map(n => {
    const s = byName.get(n.name);
    return `<li class="${s ? "clickable" : ""}" ${s ? `data-id="${s.id}"` : ""}>
      <span class="tag ${n.type}">${tagText[n.type] || ""}</span>
      <span class="n-name">${esc(n.name)}</span><span class="n-date">${esc(n.area)} ${esc(n.date)}</span></li>`;
  }).join("") || "<li>なし</li>";
  $("newsList").addEventListener("click", e => {
    const li = e.target.closest("li[data-id]");
    if (li) focusStore(+li.dataset.id);
  });

  // ---------- 現在地（ブラウザ標準機能。Android アプリ内では端末の位置情報機能を使う） ----------
  const LOCATE_ZOOM = 14;
  const nativeGeo = window.Capacitor?.isNativePlatform?.() && window.Capacitor.Plugins?.Geolocation;
  const GEO_OPTIONS = { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 };
  function getPosition(ok, ng) {
    if (nativeGeo) nativeGeo.getCurrentPosition(GEO_OPTIONS).then(ok, ng);
    else navigator.geolocation.getCurrentPosition(ok, ng, GEO_OPTIONS);
  }
  let me, meAccuracy;
  // 現在地の青い点（と誤差の円）を表示して、その座標を返す
  function showMe(p) {
    const ll = [p.coords.latitude, p.coords.longitude];
    if (me) map.removeLayer(me).removeLayer(meAccuracy);
    meAccuracy = L.circle(ll, { radius: p.coords.accuracy, color: "#2f8fd6", weight: 1, fillOpacity: .08, interactive: false }).addTo(map);
    me = L.circleMarker(ll, { radius: 8, color: "#fff", weight: 3, fillColor: "#2f8fd6", fillOpacity: 1 }).addTo(map).bindTooltip("現在地");
    return ll;
  }
  // auto: ページを開いたときの自動取得。失敗しても何も表示せず全国表示のままにする
  function locate(auto) {
    if (!nativeGeo && !navigator.geolocation) {
      if (!auto) alert("このブラウザは現在地取得に対応していません");
      return;
    }
    $("locate").classList.add("busy");
    getPosition(p => {
      $("locate").classList.remove("busy");
      // 自動取得中にユーザーが検索・店舗選択などで地図を動かしていたら邪魔しない
      if (auto && userMoved) return;
      const ll = showMe(p);
      if (isMobile()) $("side").classList.remove("open");
      map.flyTo(ll, LOCATE_ZOOM, { duration: 1.2 });
    }, () => {
      $("locate").classList.remove("busy");
      if (!auto) alert("現在地を取得できませんでした。位置情報の許可と、端末の位置情報がオンになっているかを確認してください。");
    });
  }
  let userMoved = false;
  map.on("dragstart zoomstart", () => { userMoved = true; });
  $("locate").addEventListener("click", () => locate(false));
  locate(true);

  // ---------- 周辺検索: 現在地から近い店舗を距離順に一覧に出す ----------
  function nearbySearch() {
    if (!nativeGeo && !navigator.geolocation) return alert("このブラウザは現在地取得に対応していません");
    const btn = $("nearby");
    const done = () => { btn.classList.remove("busy"); btn.disabled = false; btn.textContent = "周辺検索"; };
    btn.classList.add("busy");
    btn.disabled = true;
    btn.textContent = "取得中…";
    // PC のブラウザでは位置情報の許可を求める表示がアドレスバー付近に小さく出るため、案内を出しておく
    clearPlace();
    setNote("現在地を取得しています…<br>位置情報の許可を求められたら「許可」を選んでください。");
    if (isMobile()) $("side").classList.add("open");
    getPosition(p => {
      done();
      const ll = showMe(p);
      // 検索語は消して、絞り込み条件（地方・台数など）だけを適用
      clearTimeout(t);
      $("q").value = "";
      syncClear();
      placeReq++;
      clearPlace();
      const { base, mapKey } = filteredBase();
      const { near, rangeText } = listNearby(ll, base, mapKey);
      setNote(`<b>現在地</b>から${rangeText}表示しています。`);
      $("list").scrollTop = 0;
      if (isMobile()) $("side").classList.add("open");
      flyToNearby(ll, near);
    }, err => {
      done();
      const denied = err && err.code === 1;
      setNote(denied
        ? "現在地を取得できませんでした。<br>ブラウザ（アドレスバーの左側の設定）で、このサイトの位置情報を「許可」にしてください。"
        : "現在地を取得できませんでした。<br>端末の位置情報がオンになっているか確認してください（Mac では「システム設定 → プライバシーとセキュリティ → 位置情報サービス」でブラウザを許可）。");
    });
  }
  $("nearby").addEventListener("click", nearbySearch);

  $("source").textContent = DATA.source;
  $("generated").textContent = DATA.generated;
  if (DATA.sourceUpdated) {
    const d = new Date(DATA.sourceUpdated);
    $("sourceUpdated").textContent = ` ・元データ更新 ${d.toLocaleString("ja-JP", { dateStyle: "short", timeStyle: "short" })}`;
  }
  apply(false);

  // ---------- Android アプリの更新確認 ----------
  // 起動時に公開サイトの apk/version.json を見て、新しい版があれば更新するか確認し、APK をダウンロードする
  const UPDATE_INFO_URL = "https://nisimodo.github.io/Gamap_CC-/apk/version.json";
  async function checkAppUpdate() {
    const AppPlugin = window.Capacitor?.isNativePlatform?.() && window.Capacitor.Plugins?.App;
    if (!AppPlugin) return;
    try {
      const [info, latest] = await Promise.all([
        AppPlugin.getInfo(),
        fetch(`${UPDATE_INFO_URL}?t=${Date.now()}`, { cache: "no-store" }).then(r => r.ok ? r.json() : null),
      ]);
      if (!latest || Number(latest.versionCode) <= Number(info.build)) return;
      const msg = `新しいバージョン ${latest.versionName} があります（現在 ${info.version}）。\n`
        + (latest.notes ? `\n${latest.notes}\n` : "")
        + "\n更新しますか？\n（ダウンロード後、通知またはファイルから開いてインストールしてください）";
      if (confirm(msg)) window.open(new URL(latest.apk, UPDATE_INFO_URL).href, "_blank");
    } catch { /* オフラインなどで確認できないときは何もしない */ }
  }
  checkAppUpdate();

  // ホーム画面に追加したときのオフライン対応（Android アプリ内では不要）
  if ("serviceWorker" in navigator && window.isSecureContext && !window.Capacitor?.isNativePlatform?.()) {
    // サイトが更新されて新しいサービスワーカーに切り替わったら、新しいファイルで開き直す（初回の登録時は除く）
    const hadController = !!navigator.serviceWorker.controller;
    let reloading = false;
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (hadController && !reloading) { reloading = true; location.reload(); }
    });
    navigator.serviceWorker.register("sw.js").catch(() => {});
  }
})();

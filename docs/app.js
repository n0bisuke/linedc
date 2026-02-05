const PREF_TILES = [
  // x,y are in grid units. Rendered as a "tile map" (not geographic polygons).
  // 北海道・東北
  { pref: "北海道", x: 12, y: 0 },
  { pref: "青森県", x: 11, y: 1 },
  { pref: "秋田県", x: 11, y: 2 },
  { pref: "岩手県", x: 12, y: 2 },
  { pref: "山形県", x: 11, y: 3 },
  { pref: "宮城県", x: 12, y: 3 },
  { pref: "福島県", x: 11, y: 4 },
  // 北陸〜甲信越
  { pref: "新潟県", x: 10, y: 4 },
  { pref: "富山県", x: 9, y: 5 },
  { pref: "石川県", x: 8, y: 5 },
  { pref: "福井県", x: 8, y: 6 },
  { pref: "長野県", x: 9, y: 6 },
  { pref: "山梨県", x: 9, y: 7 },
  // 関東
  { pref: "群馬県", x: 10, y: 5 },
  { pref: "栃木県", x: 11, y: 5 },
  { pref: "茨城県", x: 12, y: 5 },
  { pref: "埼玉県", x: 10, y: 6 },
  { pref: "千葉県", x: 11, y: 6 },
  { pref: "東京都", x: 10, y: 7 },
  { pref: "神奈川県", x: 10, y: 8 },
  // 東海
  { pref: "岐阜県", x: 8, y: 7 },
  { pref: "静岡県", x: 9, y: 8 },
  { pref: "愛知県", x: 8, y: 8 },
  { pref: "三重県", x: 7, y: 9 },
  // 近畿
  { pref: "滋賀県", x: 7, y: 7 },
  { pref: "京都府", x: 6, y: 7 },
  { pref: "兵庫県", x: 5, y: 7 },
  { pref: "大阪府", x: 6, y: 8 },
  { pref: "奈良県", x: 7, y: 8 },
  { pref: "和歌山県", x: 6, y: 9 },
  // 中国
  { pref: "島根県", x: 3, y: 7 },
  { pref: "鳥取県", x: 4, y: 7 },
  { pref: "広島県", x: 3, y: 8 },
  { pref: "岡山県", x: 4, y: 8 },
  { pref: "山口県", x: 2, y: 8 },
  // 四国
  { pref: "愛媛県", x: 3, y: 9 },
  { pref: "香川県", x: 4, y: 9 },
  { pref: "徳島県", x: 5, y: 9 },
  { pref: "高知県", x: 4, y: 10 },
  // 九州・沖縄
  { pref: "福岡県", x: 2, y: 10 },
  { pref: "佐賀県", x: 1, y: 11 },
  { pref: "長崎県", x: 0, y: 12 },
  { pref: "大分県", x: 3, y: 11 },
  { pref: "熊本県", x: 2, y: 12 },
  { pref: "宮崎県", x: 3, y: 12 },
  { pref: "鹿児島県", x: 2, y: 13 },
  { pref: "沖縄県", x: 5, y: 13 },
]

const REGION_LABELS = [
  { name: "北海道", x: 11.0, y: 0.0 },
  { name: "東北", x: 10.6, y: 2.7 },
  { name: "関東", x: 10.2, y: 6.9 },
  { name: "中部", x: 8.4, y: 6.0 },
  { name: "近畿", x: 5.9, y: 7.9 },
  { name: "中国", x: 2.6, y: 7.8 },
  { name: "四国", x: 3.3, y: 9.8 },
  { name: "九州", x: 1.5, y: 11.6 },
  { name: "沖縄", x: 5.0, y: 13.0 },
]

const TOKYO_WARDS = new Set([
  "千代田区",
  "中央区",
  "港区",
  "新宿区",
  "文京区",
  "台東区",
  "墨田区",
  "江東区",
  "品川区",
  "目黒区",
  "大田区",
  "世田谷区",
  "渋谷区",
  "中野区",
  "杉並区",
  "豊島区",
  "北区",
  "荒川区",
  "板橋区",
  "練馬区",
  "足立区",
  "葛飾区",
  "江戸川区",
])

function shortPrefName(pref) {
  return pref.replace(/(都|道|府|県)$/, "")
}

function colorForCount(count) {
  if (count >= 20) return "var(--c4)"
  if (count >= 10) return "var(--c3)"
  if (count >= 5) return "var(--c2)"
  if (count >= 1) return "var(--c1)"
  return "var(--c0)"
}

function yearFromIsoDate(dateIso) {
  if (!dateIso) return null
  const m = /^(\d{4})-/.exec(dateIso)
  return m ? Number(m[1]) : null
}

function normalizeText(s) {
  return (s || "").toString().toLowerCase()
}

function inferPrefectureFallback(event) {
  // For rows where prefecture is null but address contains a ward (mostly Tokyo).
  const addr = (event.address || "").trim()
  for (const ward of TOKYO_WARDS) {
    if (addr.includes(ward)) return "東京都"
  }
  return null
}

async function loadEvents() {
  const params = new URL(import.meta.url).searchParams
  const dataPath = params.get("data") || "./events.json"
  const res = await fetch(dataPath, { cache: "no-store" })
  if (!res.ok) throw new Error(`failed to fetch ${dataPath}: ${res.status}`)
  const data = await res.json()
  return data.events || []
}

function buildYearOptions(events) {
  const years = new Set()
  for (const ev of events) {
    const y = yearFromIsoDate(ev.date)
    if (y) years.add(y)
  }
  const list = [...years].sort((a, b) => b - a)
  return list
}

function filterEvents(events, { kindFilter, yearFilter }) {
  return events.filter((ev) => {
    if (kindFilter === "onsite") {
      if (ev.location_kind !== "onsite") return false
    }
    if (yearFilter !== "all") {
      const y = yearFromIsoDate(ev.date)
      if (String(y) !== yearFilter) return false
    }
    return true
  })
}

function groupByPrefecture(events) {
  const byPref = new Map()
  for (const ev of events) {
    const pref = ev.prefecture || inferPrefectureFallback(ev)
    if (!pref) continue
    const arr = byPref.get(pref) || []
    arr.push(ev)
    byPref.set(pref, arr)
  }
  for (const [pref, arr] of byPref.entries()) {
    arr.sort((a, b) => String(b.date || "").localeCompare(String(a.date || "")))
    byPref.set(pref, arr)
  }
  return byPref
}

function createSvgEl(tag) {
  return document.createElementNS("http://www.w3.org/2000/svg", tag)
}

function renderRegionLabels({ svg, tileSize, gap, pad }) {
  for (const r of REGION_LABELS) {
    const x = pad + r.x * (tileSize + gap)
    const y = pad + r.y * (tileSize + gap)

    const text = createSvgEl("text")
    text.setAttribute("x", String(x))
    text.setAttribute("y", String(y))
    text.setAttribute("class", "regionLabel")
    text.textContent = r.name

    // Background pill sized after measuring (roughly).
    const paddingX = 10
    const paddingY = 7
    const approxWidth = Math.max(42, r.name.length * 13)
    const approxHeight = 22

    const bg = createSvgEl("rect")
    bg.setAttribute("x", String(x - paddingX))
    bg.setAttribute("y", String(y - approxHeight + paddingY))
    bg.setAttribute("width", String(approxWidth))
    bg.setAttribute("height", String(approxHeight))
    bg.setAttribute("rx", "10")
    bg.setAttribute("class", "regionLabelBg")

    const g = createSvgEl("g")
    g.append(bg, text)
    svg.appendChild(g)
  }
}

function renderMap({ svg, byPref, selectedPref, onSelect, tooltip }) {
  svg.replaceChildren()

  const tileSize = 54
  const gap = 10
  const pad = 20
  const radius = 12

  const maxX = Math.max(...PREF_TILES.map((t) => t.x))
  const maxY = Math.max(...PREF_TILES.map((t) => t.y))
  const width = pad * 2 + (maxX + 1) * (tileSize + gap) - gap
  const height = pad * 2 + (maxY + 1) * (tileSize + gap) - gap
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`)

  for (const t of PREF_TILES) {
    const count = (byPref.get(t.pref) || []).length
    const x = pad + t.x * (tileSize + gap)
    const y = pad + t.y * (tileSize + gap)
    const isSelected = selectedPref === t.pref

    const g = createSvgEl("g")

    const rect = createSvgEl("rect")
    rect.setAttribute("x", String(x))
    rect.setAttribute("y", String(y))
    rect.setAttribute("width", String(tileSize))
    rect.setAttribute("height", String(tileSize))
    rect.setAttribute("rx", String(radius))
    rect.setAttribute("fill", colorForCount(count))
    rect.setAttribute("class", `tile${isSelected ? " tile--selected" : ""}`)
    rect.dataset.pref = t.pref

    rect.addEventListener("click", () => onSelect(t.pref))
    rect.addEventListener("mousemove", (e) => {
      tooltip.hidden = false
      const title = `${t.pref}`
      const meta = `開催: ${count} 件`
      tooltip.innerHTML = `<div class="tooltip__title">${title}</div><div class="tooltip__meta">${meta}</div>`
      const wrap = svg.parentElement
      const bounds = wrap ? wrap.getBoundingClientRect() : svg.getBoundingClientRect()
      const px = e.clientX - bounds.left + 12
      const py = e.clientY - bounds.top + 12
      tooltip.style.transform = `translate(${Math.min(px, bounds.width - 360)}px, ${Math.min(py, bounds.height - 120)}px)`
    })
    rect.addEventListener("mouseleave", () => {
      tooltip.hidden = true
    })

    const label = createSvgEl("text")
    label.setAttribute("x", String(x + 10))
    label.setAttribute("y", String(y + 20))
    label.setAttribute("class", "tileLabel")
    label.textContent = shortPrefName(t.pref)

    const countText = createSvgEl("text")
    countText.setAttribute("x", String(x + 10))
    countText.setAttribute("y", String(y + tileSize - 14))
    countText.setAttribute("class", "tileCount")
    countText.textContent = String(count)

    g.append(rect, label, countText)
    svg.appendChild(g)
  }

  renderRegionLabels({ svg, tileSize, gap, pad })
}

function renderList({ listEl, events, selectedPref, searchText }) {
  listEl.replaceChildren()
  if (!selectedPref) {
    const div = document.createElement("div")
    div.className = "muted"
    div.textContent = "左の地図から都道府県をクリックすると、開催イベント一覧を表示します。"
    listEl.appendChild(div)
    return
  }

  const q = normalizeText(searchText)
  const filtered = events.filter((ev) => {
    if (!q) return true
    const hay =
      normalizeText(ev.title) +
      "\n" +
      normalizeText(ev.venue_name) +
      "\n" +
      normalizeText(ev.address) +
      "\n" +
      normalizeText(ev.type) +
      "\n" +
      normalizeText(ev.vol)
    return hay.includes(q)
  })

  if (filtered.length === 0) {
    const div = document.createElement("div")
    div.className = "muted"
    div.textContent = "該当するイベントがありません。"
    listEl.appendChild(div)
    return
  }

  for (const ev of filtered) {
    const item = document.createElement("div")
    item.className = "item"

    const title = document.createElement("div")
    title.className = "item__title"

    const link = document.createElement("a")
    link.href = ev.connpass_url || "#"
    link.target = "_blank"
    link.rel = "noreferrer"
    link.textContent = ev.title || "(no title)"
    title.appendChild(link)

    const meta = document.createElement("div")
    meta.className = "item__meta"

    const badge = document.createElement("span")
    badge.className = "badge"
    badge.textContent = ev.type || "type"

    const date = document.createElement("span")
    date.textContent = ev.date || ""

    const venue = document.createElement("span")
    venue.textContent = ev.venue_name || ""

    meta.append(badge, date, venue)

    item.append(title, meta)
    listEl.appendChild(item)
  }
}

function setSelectionHeader({ titleEl, metaEl, pref, events }) {
  if (!pref) {
    titleEl.textContent = "都道府県を選択"
    metaEl.textContent = ""
    return
  }
  titleEl.textContent = pref
  const onsite = events.filter((e) => e.location_kind === "onsite").length
  const online = events.filter((e) => e.location_kind === "online").length
  const overseas = events.filter((e) => e.location_kind === "overseas").length
  metaEl.textContent = `合計 ${events.length} 件（現地 ${onsite} / オンライン ${online} / 海外 ${overseas}）`
}

async function main() {
  const svg = document.getElementById("jpMap")
  const tooltip = document.getElementById("tooltip")
  const kindFilterEl = document.getElementById("kindFilter")
  const yearFilterEl = document.getElementById("yearFilter")
  const themeSelectEl = document.getElementById("themeSelect")
  const selectionTitle = document.getElementById("selectionTitle")
  const selectionMeta = document.getElementById("selectionMeta")
  const listEl = document.getElementById("list")
  const searchBox = document.getElementById("searchBox")

  const THEME_KEY = "linedc_theme"
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null
  function applyTheme(mode) {
    const root = document.documentElement
    if (mode === "system") {
      const isDark = media ? media.matches : false
      root.dataset.theme = isDark ? "dark" : "light"
      root.dataset.themeMode = "system"
    } else if (mode === "dark") {
      root.dataset.theme = "dark"
      root.dataset.themeMode = "dark"
    } else {
      root.dataset.theme = "light"
      root.dataset.themeMode = "light"
    }
  }
  const storedTheme = localStorage.getItem(THEME_KEY) || "light"
  if (themeSelectEl) themeSelectEl.value = storedTheme
  applyTheme(storedTheme)
  if (media) {
    media.addEventListener?.("change", () => {
      const mode = localStorage.getItem(THEME_KEY) || "light"
      if (mode === "system") applyTheme("system")
    })
  }
  themeSelectEl?.addEventListener("change", () => {
    const mode = themeSelectEl.value
    localStorage.setItem(THEME_KEY, mode)
    applyTheme(mode)
  })

  const allEvents = await loadEvents()
  const years = buildYearOptions(allEvents)
  for (const y of years) {
    const opt = document.createElement("option")
    opt.value = String(y)
    opt.textContent = String(y)
    yearFilterEl.appendChild(opt)
  }

  let selectedPref = null
  let current = {
    kindFilter: kindFilterEl.value,
    yearFilter: yearFilterEl.value,
    searchText: "",
  }

  function rerender() {
    const filtered = filterEvents(allEvents, current)
    const byPref = groupByPrefecture(filtered)

    renderMap({
      svg,
      byPref,
      selectedPref,
      tooltip,
      onSelect: (pref) => {
        selectedPref = pref
        rerender()
      },
    })

    const selectedEvents = selectedPref ? byPref.get(selectedPref) || [] : []
    setSelectionHeader({ titleEl: selectionTitle, metaEl: selectionMeta, pref: selectedPref, events: selectedEvents })
    renderList({ listEl, events: selectedEvents, selectedPref, searchText: current.searchText })
  }

  kindFilterEl.addEventListener("change", () => {
    current = { ...current, kindFilter: kindFilterEl.value }
    rerender()
  })
  yearFilterEl.addEventListener("change", () => {
    current = { ...current, yearFilter: yearFilterEl.value }
    rerender()
  })
  searchBox.addEventListener("input", () => {
    current = { ...current, searchText: searchBox.value }
    rerender()
  })

  rerender()
}

main().catch((err) => {
  console.error(err)
  const el = document.createElement("pre")
  el.style.whiteSpace = "pre-wrap"
  el.style.color = "white"
  el.textContent = String(err?.stack || err)
  document.body.appendChild(el)
})

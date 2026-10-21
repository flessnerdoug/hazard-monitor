const CATEGORY_COLORS = {
  "Tropical Cyclone": "#7c3aed",
  "Severe Storm": "#f59e0b",
  "Flood": "#2563eb",
  "Winter Weather": "#06b6d4",
  "Wildfire": "#dc2626",
  "Heat": "#db2777",
  "Earthquake": "#92400e",
  "Volcano": "#57534e",
  "Tsunami": "#0d9488",
  "Drought": "#65a30d",
  "Other": "#94a3b8",
};
const SEVERITY_LABELS = { 1: "Advisory", 2: "Elevated", 3: "Extreme" };
const MAX_LISTED = 300;

const data = window.RISK_DATA;
const state = { hidden: new Set(), minSeverity: 1, query: "", activeId: null };
const markers = new Map();

const map = L.map("map", { worldCopyJump: true }).setView([30, -60], 3);
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 16,
  attribution: "Tiles &copy; Esri &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors",
}).addTo(map);
L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
  maxZoom: 16,
}).addTo(map);
const layer = L.layerGroup().addTo(map);

function colorFor(category) {
  return CATEGORY_COLORS[category] || CATEGORY_COLORS.Other;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function timeAgo(iso) {
  const minutes = Math.round((Date.now() - new Date(iso)) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function sevBadge(sev) {
  return `<span class="sev sev-${sev}">${SEVERITY_LABELS[sev]}</span>`;
}

function isVisible(e) {
  return (
    !state.hidden.has(e.category) &&
    e.severity >= state.minSeverity &&
    (!state.query || `${e.title} ${e.source} ${e.category}`.toLowerCase().includes(state.query))
  );
}

function renderHeader() {
  const updated = new Date(data.generated);
  const sources = Object.keys(data.sources).length;
  document.getElementById("updated").textContent =
    `Updated ${updated.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} · ${data.events.length} events from ${sources} sources`;

  const failed = Object.entries(data.sources).filter(([, s]) => !s.ok).map(([name]) => name);
  if (failed.length) {
    const warning = document.getElementById("source-warning");
    warning.textContent = `Could not reach ${failed.join(", ")} on the last update. Showing their previous headlines.`;
    warning.hidden = false;
  }
}

function renderChips() {
  const counts = {};
  for (const e of data.events) counts[e.category] = (counts[e.category] || 0) + 1;
  const nav = document.getElementById("categories");
  nav.innerHTML = "";
  for (const category of Object.keys(CATEGORY_COLORS).filter((c) => counts[c])) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.setAttribute("aria-pressed", String(!state.hidden.has(category)));
    chip.innerHTML = `<span class="dot" style="background:${colorFor(category)}"></span>${escapeHtml(category)} <span class="n">${counts[category]}</span>`;
    chip.addEventListener("click", () => {
      state.hidden.has(category) ? state.hidden.delete(category) : state.hidden.add(category);
      chip.setAttribute("aria-pressed", String(!state.hidden.has(category)));
      render();
    });
    nav.appendChild(chip);
  }
}

function popupHtml(e) {
  return `<div class="popup-title">${escapeHtml(e.title)}</div>
    <div class="meta">${sevBadge(e.severity)} ${escapeHtml(e.source)} · ${timeAgo(e.time)}
    · <a href="${encodeURI(e.url)}" target="_blank" rel="noopener">Source ↗</a></div>`;
}

function focus(e) {
  state.activeId = e.id;
  document.querySelectorAll("#headlines li").forEach((li) => li.classList.toggle("active", li.dataset.id === e.id));
  map.flyTo([e.lat, e.lon], Math.max(map.getZoom(), 6), { duration: 0.8 });
  markers.get(e.id)?.openPopup();
}

function render() {
  const visible = data.events.filter(isVisible);

  layer.clearLayers();
  markers.clear();
  // Draw low severity first so extreme events sit on top.
  for (const e of [...visible].sort((a, b) => a.severity - b.severity)) {
    const marker = L.circleMarker([e.lat, e.lon], {
      radius: 4 + e.severity * 2.5,
      color: e.severity === 3 ? "#111" : "#fff",
      weight: e.severity === 3 ? 2 : 1,
      fillColor: colorFor(e.category),
      fillOpacity: 0.85,
    }).bindPopup(popupHtml(e));
    marker.on("click", () => focus(e));
    marker.addTo(layer);
    markers.set(e.id, marker);
  }

  const list = document.getElementById("headlines");
  list.innerHTML = "";
  for (const e of visible.slice(0, MAX_LISTED)) {
    const li = document.createElement("li");
    li.dataset.id = e.id;
    li.classList.toggle("active", e.id === state.activeId);
    li.innerHTML = `<span class="dot" style="background:${colorFor(e.category)}"></span>
      <div>
        <div class="headline">${escapeHtml(e.title)}</div>
        <div class="meta">${sevBadge(e.severity)}<span>${escapeHtml(e.source)}</span><span>${timeAgo(e.time)}</span>
          <a href="${encodeURI(e.url)}" target="_blank" rel="noopener">Source ↗</a></div>
      </div>`;
    li.addEventListener("click", (ev) => {
      if (ev.target.tagName !== "A") focus(e);
    });
    list.appendChild(li);
  }
  if (!visible.length) {
    list.innerHTML = `<li class="empty">No headlines match these filters.</li>`;
  }

  const shown = Math.min(visible.length, MAX_LISTED);
  document.getElementById("count").textContent =
    visible.length > MAX_LISTED
      ? `Showing ${shown} of ${visible.length} headlines (all ${visible.length} are on the map)`
      : `${visible.length} headline${visible.length === 1 ? "" : "s"}`;
}

if (!data) {
  document.getElementById("updated").textContent = "No data yet";
  document.getElementById("headlines").innerHTML =
    `<li class="empty">Run <code>python fetch_data.py</code> to download the latest headlines, then reload this page.</li>`;
} else {
  renderHeader();
  renderChips();
  render();

  document.getElementById("severity").addEventListener("change", (ev) => {
    state.minSeverity = Number(ev.target.value);
    render();
  });
  document.getElementById("search").addEventListener("input", (ev) => {
    state.query = ev.target.value.trim().toLowerCase();
    render();
  });
}

// ---- tabs (#hazards / #research) ----

function showTab() {
  const active = location.hash === "#research" ? "research" : "hazards";
  for (const name of ["hazards", "research"]) {
    document.getElementById(`tab-${name}`).hidden = name !== active;
    document.getElementById(`tab-btn-${name}`).setAttribute("aria-selected", String(name === active));
  }
  // Leaflet can't measure a hidden map; re-measure when it becomes visible.
  if (active === "hazards") map.invalidateSize();
}

window.addEventListener("hashchange", showTab);
showTab();

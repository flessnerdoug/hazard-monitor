// Research & Trends tab. Uses escapeHtml() and timeAgo() from script.js.
(() => {
  const data = window.RESEARCH_DATA;
  const state = { kind: "news", topic: "", query: "" };
  const TREND_READY_DAYS = 14;

  const $ = (id) => document.getElementById(id);

  if (!data) {
    $("briefing").innerHTML =
      `<li class="empty">Run <code>python fetch_research.py</code> to collect the latest research, then reload this page.</li>`;
    return;
  }

  const byId = new Map(data.items.map((it) => [it.id, it]));
  const generated = new Date(data.generated);
  const trackedDays = (generated - new Date(data.tracking_since)) / 86400000;
  const trendReady = trackedDays >= TREND_READY_DAYS;

  function tagsHtml(topics, limit = 3) {
    return `<div class="tags">${topics
      .slice(0, limit)
      .map((t) => `<button class="tag" data-topic="${escapeHtml(t)}">${escapeHtml(t)}</button>`)
      .join("")}</div>`;
  }

  function setTopic(topic) {
    state.topic = state.topic === topic ? "" : topic;
    $("r-topic").value = state.topic;
    renderTopics();
    renderReading();
  }

  // ---- morning briefing ----

  function renderBriefing() {
    $("briefing-title").textContent =
      `Morning briefing · ${generated.toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}`;
    $("r-updated").textContent =
      `${data.items.length} stories & papers from the last 2 weeks · updated ${generated.toLocaleTimeString(undefined, { timeStyle: "short" })}`;

    const cards = data.briefing.map((id) => byId.get(id)).filter(Boolean);
    $("briefing").innerHTML = cards
      .map(
        (it) => `<li class="card ${it.kind === "research" ? "paper" : ""}">
          <span class="kicker">${it.kind === "research" ? "From the journals" : "In the news"}</span>
          <h3><a href="${encodeURI(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a></h3>
          ${it.summary ? `<p class="summary">${escapeHtml(it.summary)}</p>` : ""}
          ${tagsHtml(it.topics)}
          <div class="meta"><span>${escapeHtml(it.source)}</span><span>${timeAgo(it.published)}</span></div>
        </li>`
      )
      .join("") || `<li class="empty">Nothing new in the last week.</li>`;
  }

  // ---- trending topics ----

  function renderTopics() {
    const rows = data.topics
      .map((t) => ({ name: t.name, now: t.weekly.at(-1), prev: t.weekly.at(-2) }))
      .filter((t) => t.now || t.prev)
      .sort((a, b) => b.now - a.now || a.name.localeCompare(b.name));
    const max = Math.max(1, ...rows.map((r) => r.now));

    $("topics").innerHTML = rows
      .map((r) => {
        const diff = r.now - r.prev;
        const change = !trendReady
          ? ""
          : diff > 0
            ? ` <span class="up">▲ ${diff}</span>`
            : diff < 0
              ? ` <span class="down">▼ ${-diff}</span>`
              : ` <span>· no change</span>`;
        const tip = `${r.name}: ${r.now} this week, ${r.prev} the week before`;
        return `<li data-topic="${escapeHtml(r.name)}" class="${state.topic === r.name ? "active" : ""}" title="${escapeHtml(tip)}">
          <span>${escapeHtml(r.name)}</span>
          <span class="num">${r.now}${change}</span>
          <span class="track"><span class="fill" style="width:${(r.now / max) * 100}%"></span></span>
        </li>`;
      })
      .join("");

    const since = new Date(data.tracking_since).toLocaleDateString(undefined, { month: "short", day: "numeric" });
    $("trend-note").textContent = trendReady
      ? "▲ / ▼ compare with the 7 days before. Click a topic to filter the reading list."
      : `Week-over-week changes will appear after two weeks of daily collection (tracking since ${since}). Click a topic to filter the reading list.`;
  }

  // ---- reading list ----

  function renderReading() {
    const q = state.query;
    const items = data.items.filter(
      (it) =>
        (state.kind === "all" || it.kind === state.kind) &&
        (!state.topic || it.topics.includes(state.topic)) &&
        (!q || `${it.title} ${it.summary} ${it.source}`.toLowerCase().includes(q))
    );

    $("r-count").textContent = `${items.length} item${items.length === 1 ? "" : "s"}${state.topic ? ` on ${state.topic}` : ""}`;
    $("reading").innerHTML = items
      .map(
        (it) => `<li>
          <h3><a href="${encodeURI(it.url)}" target="_blank" rel="noopener">${escapeHtml(it.title)}</a></h3>
          ${it.summary ? `<p class="summary">${escapeHtml(it.summary)}</p>` : ""}
          <div class="meta">${it.kind === "research" ? "<span>Paper</span>" : ""}<span>${escapeHtml(it.source)}</span><span>${timeAgo(it.published)}</span></div>
          ${it.topics.length ? tagsHtml(it.topics) : ""}
        </li>`
      )
      .join("") || `<li class="empty">Nothing matches these filters.</li>`;
  }

  // ---- wiring ----

  for (const t of data.topics) {
    $("r-topic").insertAdjacentHTML("beforeend", `<option>${escapeHtml(t.name)}</option>`);
  }
  $("r-topic").addEventListener("change", (ev) => setTopic(ev.target.value || state.topic));
  $("r-search").addEventListener("input", (ev) => {
    state.query = ev.target.value.trim().toLowerCase();
    renderReading();
  });
  document.querySelectorAll(".segmented button").forEach((btn) =>
    btn.addEventListener("click", () => {
      state.kind = btn.dataset.kind;
      document.querySelectorAll(".segmented button").forEach((b) => b.setAttribute("aria-pressed", String(b === btn)));
      renderReading();
    })
  );
  $("tab-research").addEventListener("click", (ev) => {
    const el = ev.target.closest("[data-topic]");
    if (el && !el.closest("a")) setTopic(el.dataset.topic);
  });

  renderBriefing();
  renderTopics();
  renderReading();
})();

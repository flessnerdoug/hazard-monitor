#!/usr/bin/env python3
"""Collect recent weather and climate research headlines for the Research tab.

Two kinds of sources:
  news      plain-language write-ups of new studies (ScienceDaily, Phys.org,
            Carbon Brief, Yale Climate Connections, NOAA News)
  research  newly published journal papers (Nature Climate Change, GRL,
            Weather and Climate Dynamics, BAMS, Journal of Climate)

Every item seen is kept in data/research_archive.json for ~9 weeks so topic
trends can be compared week over week. The page reads data/research.js.
Standard library only.
"""
import hashlib
import html
import json
import re
import sys
import traceback
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ARCHIVE = DATA / "research_archive.json"
USER_AGENT = "RiskMonitor/1.0 (personal hazard dashboard)"
KEEP_DAYS = 63      # archive window: 9 weeks of history for trend comparisons
LIST_DAYS = 14      # how far back the reading list on the page goes
BRIEFING_SIZE = 5

NOW = datetime.now(timezone.utc)

# name, kind, url, format, use the feed's summary text, require a weather/climate keyword
FEEDS = [
    ("ScienceDaily", "news", "https://www.sciencedaily.com/rss/earth_climate/weather.xml", "rss", True, False),
    ("ScienceDaily", "news", "https://www.sciencedaily.com/rss/earth_climate/climate.xml", "rss", True, False),
    ("Phys.org", "news", "https://phys.org/rss-feed/earth-news/earth-sciences/", "rss", True, True),
    ("Phys.org", "news", "https://phys.org/rss-feed/earth-news/environment/", "rss", True, True),
    ("Carbon Brief", "news", "https://www.carbonbrief.org/feed/", "rss", True, False),
    ("Yale Climate Connections", "news", "https://yaleclimateconnections.org/feed/", "rss", True, False),
    ("NOAA News", "news", "https://www.noaa.gov/rss.xml", "rss", False, False),
    ("Nature Climate Change", "research", "https://api.crossref.org/journals/1758-6798/works?sort=created&order=desc&rows=40", "crossref", True, False),
    ("Geophysical Research Letters", "research", "https://agupubs.onlinelibrary.wiley.com/feed/19448007/most-recent", "rss", False, True),
    ("Weather and Climate Dynamics", "research", "https://wcd.copernicus.org/xml/rss2_0.xml", "rss", False, False),
    ("Bulletin of the AMS", "research", "https://api.crossref.org/journals/1520-0477/works?sort=created&order=desc&rows=40", "crossref", True, False),
    ("Journal of Climate", "research", "https://api.crossref.org/journals/1520-0442/works?sort=created&order=desc&rows=40", "crossref", True, False),
]

TOPICS = {
    "Hurricanes & Tropical": r"hurricane|typhoon|cyclone|tropical storm",
    "Heat": r"heat ?waves?|extreme heat|\bheat\b|hottest|record temperature",
    "Rain & Flooding": r"flood|rainfall|heavy rain|precipitation|atmospheric rivers?|monsoon",
    "Drought & Water": r"drought|aridity|water (supply|scarcity|resources|systems)|groundwater",
    "Wildfire & Smoke": r"wildfire|\bfires?\b|smoke",
    "Severe Storms": r"tornado|thunderstorm|\bhail\b|lightning|derecho|severe weather",
    "Snow & Winter": r"\bsnow|blizzard|winter storm|polar vortex|cold snap|winter outlook",
    "Ice & Polar": r"arctic|antarctic|glacier|ice sheet|sea ice|permafrost|greenland",
    "Oceans & Sea Level": r"sea[- ]level|ocean|marine heat|coral|coastal",
    "El Niño & La Niña": r"el ni[ñn]o|la ni[ñn]a|\benso\b",
    "Forecasting & AI": r"forecast|machine learning|artificial intelligence|\bAI\b|neural network|satellite|radar|weather model",
    "Emissions & Policy": r"emission|carbon|\bco2\b|methane|ipcc|\bcop\d*\b|net[- ]zero|climate policy|renewable|fossil fuel|hydrogen",
    "Air Quality": r"aerosol|air quality|air pollution|\bdust\b|ozone",
    "Health & Society": r"health|mortality|agricultur|\bcrops?\b|food security|economic|insurance|infrastructure|drinking water",
}
TOPIC_RES = {name: re.compile(rx, re.I) for name, rx in TOPICS.items()}
RELEVANT = re.compile(r"climate|weather|atmospher|meteorolog|warming|temperature", re.I)
NOT_ARTICLES = re.compile(r"(journal information|table of contents|issue information|front matter|masthead|"
                          r"cover image|erratum|corrigendum|correction to|retraction)", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read()


def fetch_retry(url, parse):
    """Fetch and parse, retrying once: some publishers intermittently serve a non-feed page."""
    try:
        return list(parse(fetch(url)))
    except (ET.ParseError, ValueError):
        return list(parse(fetch(url)))


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def excerpt(text, limit=300):
    """First couple of sentences, capped at `limit` characters."""
    text = re.sub(r"^(abstract|summary)[:.\s]+", "", clean(text), flags=re.I)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "))
    return cut[: end + 1] if end > limit * 0.4 else cut.rsplit(" ", 1)[0] + "…"


def parse_date(text):
    if not text:
        return None
    text = text.strip()
    try:
        dt = parsedate_to_datetime(text)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return min(dt, NOW)


def topics_for(text):
    return [name for name, rx in TOPIC_RES.items() if rx.search(text)]


# ---------------------------------------------------------------- parsers

def parse_rss(raw):
    """Yield (title, link, date, summary) from RSS 2.0, RSS 1.0 or Atom."""
    root = ET.fromstring(raw)
    entries = [el for el in root.iter() if el.tag.split("}")[-1] in ("item", "entry")]
    for el in entries:
        fields = {}
        for child in el:
            tag = child.tag.split("}")[-1]
            if tag == "link" and child.get("href"):
                fields.setdefault("link", child.get("href"))
            elif (child.text or "").strip():
                fields.setdefault(tag, child.text.strip())
        date = next((fields[k] for k in ("pubDate", "date", "published", "updated", "publicationDate") if k in fields), None)
        summary = fields.get("description") or fields.get("summary") or ""
        yield fields.get("title", ""), fields.get("link", ""), parse_date(date), summary


def parse_crossref(raw):
    for w in json.loads(raw)["message"]["items"]:
        if w.get("type") != "journal-article" or not w.get("title"):
            continue
        created = (w.get("created") or {}).get("date-time")
        link = w.get("URL") or f"https://doi.org/{w['DOI']}"
        yield w["title"][0], link, parse_date(created), w.get("abstract", "")


# ---------------------------------------------------------------- collect

def collect(feed):
    name, kind, url, fmt, use_summary, needs_keyword = feed
    parser = parse_crossref if fmt == "crossref" else parse_rss
    out = []
    for title, link, date, summary in fetch_retry(url, parser):
        title = clean(title)
        if not title or not link or NOT_ARTICLES.match(title):
            continue
        summary = excerpt(summary) if use_summary else ""
        if summary.lower().startswith(title.lower()):
            summary = ""  # some feeds just repeat the headline
        text = f"{title} {summary}"
        if needs_keyword and not (RELEVANT.search(text) or topics_for(text)):
            continue
        out.append({
            "id": hashlib.sha1(link.encode()).hexdigest()[:12],
            "title": title,
            "url": link,
            "source": name,
            "kind": kind,
            "published": iso(date) if date else None,
            "summary": summary,
            "topics": topics_for(text),
        })
    return out


def week_counts(items, weeks=8):
    """Items per topic for each of the last `weeks` 7-day windows, oldest first."""
    counts = {name: [0] * weeks for name in TOPICS}
    for it in items:
        age_days = (NOW - datetime.fromisoformat(it["published"])).total_seconds() / 86400
        week = int(age_days // 7)
        if week < weeks:
            for t in it["topics"]:
                counts[t][weeks - 1 - week] += 1
    return counts


def pick_briefing(items):
    """A short, varied morning read: mostly plain-language news plus one paper."""
    def age_h(it):
        return (NOW - datetime.fromisoformat(it["published"])).total_seconds() / 3600

    for window in (36, 72, 168):
        recent = [it for it in items if age_h(it) <= window]
        if sum(it["kind"] == "news" for it in recent) >= BRIEFING_SIZE - 1:
            break

    def score(it):
        return -age_h(it) / 12 + (1 if it["summary"] else 0) + min(len(it["topics"]), 2) * 0.5

    picks, used_topics, per_source = [], set(), {}
    for it in sorted((i for i in recent if i["kind"] == "news"), key=score, reverse=True):
        main = it["topics"][0] if it["topics"] else None
        if main in used_topics or per_source.get(it["source"], 0) >= 2:
            continue
        picks.append(it["id"])
        used_topics.add(main)
        per_source[it["source"]] = per_source.get(it["source"], 0) + 1
        if len(picks) == BRIEFING_SIZE - 1:
            break
    papers = sorted((i for i in recent if i["kind"] == "research" and i["summary"]), key=score, reverse=True)
    if papers:
        picks.append(papers[0]["id"])
    return picks


def main():
    DATA.mkdir(exist_ok=True)
    archive = {}
    if ARCHIVE.exists():
        archive = {it["id"]: it for it in json.loads(ARCHIVE.read_text(encoding="utf-8"))["items"]}

    status = {}
    for feed in FEEDS:
        name = feed[0]
        try:
            items = collect(feed)
            prev = status.get(name, {"ok": True, "count": 0})
            status[name] = {"ok": prev["ok"], "count": prev["count"] + len(items)}
        except Exception as exc:
            items = []
            status[name] = {"ok": False, "count": status.get(name, {}).get("count", 0), "error": f"{type(exc).__name__}: {exc}"}
            traceback.print_exc()
        for it in items:
            old = archive.get(it["id"])
            it["first_seen"] = old["first_seen"] if old else iso(NOW)
            it["published"] = it["published"] or it["first_seen"]
            archive[it["id"]] = it

    cutoff = NOW - timedelta(days=KEEP_DAYS)
    items = sorted((it for it in archive.values() if datetime.fromisoformat(it["published"]) >= cutoff),
                   key=lambda it: it["published"], reverse=True)
    ARCHIVE.write_text(json.dumps({"items": items}, indent=1, ensure_ascii=False), encoding="utf-8")

    weekly = week_counts(items)
    tracking_since = min((it["first_seen"] for it in items), default=iso(NOW))
    list_cutoff = NOW - timedelta(days=LIST_DAYS)
    payload = {
        "generated": iso(NOW),
        "tracking_since": tracking_since,
        "sources": status,
        "briefing": pick_briefing(items),
        "topics": [{"name": t, "weekly": weekly[t]} for t in TOPICS],
        "items": [it for it in items if datetime.fromisoformat(it["published"]) >= list_cutoff],
    }
    (DATA / "research.js").write_text("window.RESEARCH_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")

    summary = ", ".join(f"{k} {'ok' if v['ok'] else 'FAILED'} ({v['count']})" for k, v in status.items())
    with open(DATA / "update.log", "a", encoding="utf-8") as log:
        log.write(f"{iso(NOW)}  research: {len(payload['items'])} items  |  {summary}\n")
    print(f"{len(payload['items'])} research items written. {summary}")
    return 0 if any(v["ok"] for v in status.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

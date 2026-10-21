#!/usr/bin/env python3
"""Collect hazard headlines from public agency feeds and write them for the site.

Sources: USGS (earthquakes), NWS (active alerts), NOAA SPC (storm reports),
NHC (tropical cyclones), NASA EONET (natural events), GDACS (global disasters).

Writes data/events.json and data/events.js (the .js copy lets index.html load
the data straight from disk without a web server). Standard library only.
"""
import csv
import io
import json
import re
import sys
import traceback
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
ZONE_CACHE = DATA / "zone_cache.json"
USER_AGENT = "RiskMonitor/1.0 (personal hazard dashboard)"

NOW = datetime.now(timezone.utc)


def fetch(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return resp.read()


def fetch_json(url):
    return json.loads(fetch(url, "application/geo+json, application/json"))


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def geometry_center(geom):
    """Bounding-box center of any GeoJSON geometry, as (lat, lon)."""
    if not geom:
        return None
    lons, lats = [], []

    def walk(c):
        if isinstance(c[0], (int, float)):
            lons.append(c[0])
            lats.append(c[1])
        else:
            for sub in c:
                walk(sub)

    walk(geom["coordinates"])
    if not lons:
        return None
    return round((min(lats) + max(lats)) / 2, 4), round((min(lons) + max(lons)) / 2, 4)


def event(source, category, title, lat, lon, time, severity, url, eid):
    time = iso(datetime.fromisoformat(time))  # feeds mix UTC and local offsets
    return {
        "id": f"{source}:{eid}",
        "source": source,
        "category": category,
        "title": title,
        "lat": lat,
        "lon": lon,
        "time": time,
        "severity": severity,  # 1 = advisory, 2 = elevated, 3 = extreme
        "url": url,
    }


# ---------------------------------------------------------------- USGS

def usgs():
    data = fetch_json("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson")
    out = []
    for f in data["features"]:
        p = f["properties"]
        lon, lat = f["geometry"]["coordinates"][:2]
        mag = p.get("mag") or 0
        alert = p.get("alert")
        if mag >= 7 or alert in ("orange", "red"):
            sev = 3
        elif mag >= 6 or alert == "yellow":
            sev = 2
        else:
            sev = 1
        title = f"M{mag:.1f} earthquake, {p.get('place') or 'unknown location'}"
        if p.get("tsunami"):
            title += " (tsunami information issued)"
        time = iso(datetime.fromtimestamp(p["time"] / 1000, timezone.utc))
        out.append(event("USGS", "Earthquake", title, lat, lon, time, sev, p["url"], f["id"]))
    return out


# ---------------------------------------------------------------- NWS

def nws_category(name):
    n = name.lower()
    rules = [
        (("hurricane", "tropical", "typhoon", "storm surge"), "Tropical Cyclone"),
        (("tsunami",), "Tsunami"),
        (("flood",), "Flood"),
        (("fire",), "Wildfire"),
        (("heat",), "Heat"),
        (("winter", "blizzard", "ice", "snow", "freeze", "frost", "cold", "chill", "sleet"), "Winter Weather"),
        (("tornado", "thunderstorm", "wind", "storm", "hail", "dust", "squall"), "Severe Storm"),
    ]
    for words, cat in rules:
        if any(w in n for w in words):
            return cat
    return "Other"


def short_area(area_desc, limit=3):
    parts = [a.strip() for a in area_desc.split(";") if a.strip()]
    text = "; ".join(parts[:limit])
    if len(parts) > limit:
        text += f" +{len(parts) - limit} more"
    return text


def nws():
    data = fetch_json("https://api.weather.gov/alerts/active?status=actual&severity=Extreme,Severe")
    cache = json.loads(ZONE_CACHE.read_text(encoding="utf-8")) if ZONE_CACHE.exists() else {}
    seen = {}
    for f in data["features"]:
        p = f["properties"]
        key = (p["event"], p["areaDesc"])
        if key in seen and seen[key]["properties"]["sent"] >= p["sent"]:
            continue
        seen[key] = f

    out = []
    for f in seen.values():
        p = f["properties"]
        center = geometry_center(f.get("geometry"))
        if not center:
            for zone in p.get("affectedZones", [])[:1]:
                if zone not in cache:
                    try:
                        cache[zone] = geometry_center(fetch_json(zone).get("geometry"))
                    except Exception:
                        cache[zone] = None
                center = cache[zone]
        if not center:
            continue
        lat, lon = center
        sev = 3 if p["severity"] == "Extreme" else 2
        title = f"{p['event']}: {short_area(p['areaDesc'])}"
        url = f"https://forecast.weather.gov/MapClick.php?lat={lat}&lon={lon}"
        out.append(event("NWS", nws_category(p["event"]), title, lat, lon, p["sent"], sev, url, p["id"].rsplit("/", 1)[-1]))

    ZONE_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return out


# ---------------------------------------------------------------- SPC

def spc():
    start_today = (NOW - timedelta(hours=12)).date()  # SPC "day" runs 12Z to 12Z
    days = [("yesterday", start_today - timedelta(days=1)), ("today", start_today)]
    out = []
    for name, day in days:
        text = fetch(f"https://www.spc.noaa.gov/climo/reports/{name}_filtered.csv", "text/csv").decode("utf-8", "replace")
        kind = None
        for i, row in enumerate(csv.reader(io.StringIO(text))):
            if not row:
                continue
            if row[0] == "Time":
                kind = {"F_Scale": "tornado", "Speed": "wind", "Size": "hail"}.get(row[1])
                continue
            if kind is None or len(row) < 7:
                continue
            hhmm, mag, loc, county, state, lat, lon = row[:7]
            try:
                lat, lon = float(lat), float(lon)
                when = datetime.combine(day, datetime.min.time(), timezone.utc) + timedelta(hours=int(hhmm[:2]), minutes=int(hhmm[2:]))
            except ValueError:
                continue
            if int(hhmm[:2]) < 12:
                when += timedelta(days=1)
            loc = re.sub(r"\b([NSEW]{1,3})\b", lambda m: m.group(1).upper(), loc.title(), flags=re.I)
            place = f"{loc}, {county.title()} County, {state}"
            if kind == "tornado":
                title, sev = f"Tornado reported near {place}", 3
            elif kind == "wind":
                speed = f" ({mag} mph)" if mag.isdigit() else ""
                title = f"Damaging wind{speed} reported near {place}"
                sev = 2 if mag.isdigit() and int(mag) >= 75 else 1
            else:
                size = f'{int(mag) / 100:.2f}" ' if mag.isdigit() else ""
                title = f"{size}hail reported near {place}"
                title = title[0].upper() + title[1:]
                sev = 2 if mag.isdigit() and int(mag) >= 200 else 1
            url = f"https://www.spc.noaa.gov/climo/reports/{name}.html"
            out.append(event("NOAA SPC", "Severe Storm", title, lat, lon, iso(when), sev, url, f"{day}-{kind}-{i}"))
    return out


# ---------------------------------------------------------------- NHC

NHC_CLASSES = {
    "HU": "Hurricane", "TS": "Tropical Storm", "TD": "Tropical Depression",
    "STS": "Subtropical Storm", "STD": "Subtropical Depression",
    "PTC": "Potential Tropical Cyclone", "PC": "Post-Tropical Cyclone",
}


def nhc():
    data = fetch_json("https://www.nhc.noaa.gov/CurrentStorms.json")
    out = []
    for s in data.get("activeStorms", []):
        cls = NHC_CLASSES.get(s.get("classification"), "Tropical Cyclone")
        kt = int(s.get("intensity") or 0)
        sev = 3 if s.get("classification") == "HU" else 2 if s.get("classification") in ("TS", "STS") else 1
        title = f"{cls} {s['name']}: {round(kt * 1.15078)} mph winds, {s.get('pressure')} mb"
        url = (s.get("publicAdvisory") or {}).get("url") or "https://www.nhc.noaa.gov/"
        out.append(event("NHC", "Tropical Cyclone", title, s["latitudeNumeric"], s["longitudeNumeric"],
                         s.get("lastUpdate") or iso(NOW), sev, url, s["id"]))
    return out


# ---------------------------------------------------------------- NASA EONET

EONET_CATEGORIES = {
    "wildfires": "Wildfire", "volcanoes": "Volcano", "floods": "Flood", "drought": "Drought",
    "snow": "Winter Weather", "tempExtremes": "Heat", "severeStorms": "Severe Storm",
}


def eonet():
    data = fetch_json("https://eonet.gsfc.nasa.gov/api/v3/events?status=open&days=7")
    out = []
    for e in data["events"]:
        cat_id = e["categories"][0]["id"]
        if cat_id == "earthquakes":
            continue  # USGS is the authoritative source
        category = EONET_CATEGORIES.get(cat_id, "Other")
        if category == "Severe Storm" and re.search(r"cyclone|hurricane|typhoon|tropical", e["title"], re.I):
            category = "Tropical Cyclone"
        last = e["geometry"][-1]
        lat, lon = geometry_center(last)
        sev = 1
        if last.get("magnitudeUnit") == "kts" and last.get("magnitudeValue"):
            sev = 3 if last["magnitudeValue"] >= 64 else 2 if last["magnitudeValue"] >= 34 else 1
        url = e["sources"][0]["url"] if e.get("sources") else e["link"]
        out.append(event("NASA EONET", category, e["title"], lat, lon, last["date"], sev, url, e["id"]))
    return out


# ---------------------------------------------------------------- GDACS

GDACS_TYPES = {"TC": "Tropical Cyclone", "FL": "Flood", "VO": "Volcano", "DR": "Drought", "WF": "Wildfire", "TS": "Tsunami"}


def gdacs():
    params = urllib.parse.urlencode({"alertlevel": "Orange;Red", "fromdate": (NOW - timedelta(days=30)).date().isoformat()})
    data = fetch_json(f"https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?{params}")
    cutoff = NOW - timedelta(days=3)
    out = []
    for f in data.get("features", []):
        p = f["properties"]
        category = GDACS_TYPES.get(p.get("eventtype"))
        if not category:
            continue  # earthquakes come from USGS
        to_date = datetime.fromisoformat(p["todate"]).replace(tzinfo=timezone.utc) if p.get("todate") else NOW
        if str(p.get("iscurrent")).lower() != "true" and to_date < cutoff:
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        sev = 3 if p.get("alertlevel") == "Red" else 2
        title = p.get("name") or p.get("description")
        if p.get("country"):
            title += f", {p['country']}"
        url = (p.get("url") or {}).get("report") or "https://www.gdacs.org/"
        out.append(event("GDACS", category, title, lat, lon, iso(to_date), sev, url, f"{p['eventtype']}{p['eventid']}"))
    return out


# ---------------------------------------------------------------- merge

SOURCES = {"USGS": usgs, "NWS": nws, "NOAA SPC": spc, "NHC": nhc, "NASA EONET": eonet, "GDACS": gdacs}
# When the same storm or volcano appears in several feeds, keep the first in this order.
PRIORITY = ["NHC", "GDACS", "NASA EONET"]


def dedupe_key(e):
    if e["source"] not in PRIORITY or e["category"] not in ("Tropical Cyclone", "Volcano"):
        return None
    name = re.sub(r"\b(super typhoon|typhoon|hurricane|tropical (cyclone|storm|depression)|"
                  r"subtropical (storm|depression)|potential tropical cyclone|post-tropical cyclone|volcano)\b",
                  "", e["title"].split(":")[0].split(",")[0], flags=re.I)
    name = re.sub(r"-\d{2}\b", "", name).strip().lower()
    return (e["category"], name.split()[0]) if name else None


def dedupe(events):
    events.sort(key=lambda e: PRIORITY.index(e["source"]) if e["source"] in PRIORITY else len(PRIORITY))
    seen, out = set(), []
    for e in events:
        key = dedupe_key(e)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        out.append(e)
    return out


def main():
    DATA.mkdir(exist_ok=True)
    previous = {}
    if (DATA / "events.json").exists():
        try:
            for e in json.loads((DATA / "events.json").read_text(encoding="utf-8"))["events"]:
                previous.setdefault(e["source"], []).append(e)
        except Exception:
            pass

    events, status = [], {}
    for name, fn in SOURCES.items():
        try:
            items = fn()
            status[name] = {"ok": True, "count": len(items)}
        except Exception as exc:
            # Keep yesterday's headlines for this source rather than dropping it from the map.
            items = previous.get(name, [])
            status[name] = {"ok": False, "count": len(items), "error": f"{type(exc).__name__}: {exc}"}
            traceback.print_exc()
        events.extend(items)

    events = dedupe(events)
    events.sort(key=lambda e: (e["severity"], e["time"]), reverse=True)
    payload = {"generated": iso(NOW), "sources": status, "events": events}

    (DATA / "events.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    (DATA / "events.js").write_text("window.RISK_DATA = " + json.dumps(payload, ensure_ascii=False) + ";\n", encoding="utf-8")

    summary = ", ".join(f"{k} {'ok' if v['ok'] else 'FAILED'} ({v['count']})" for k, v in status.items())
    with open(DATA / "update.log", "a", encoding="utf-8") as log:
        log.write(f"{iso(NOW)}  {len(events)} events  |  {summary}\n")
    print(f"{len(events)} events written. {summary}")
    return 0 if any(v["ok"] for v in status.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

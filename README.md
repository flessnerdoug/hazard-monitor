# Hazard Monitor

A one-page dashboard of current natural-hazard headlines, with a map of where each one is happening.

## Sources

| Source | What it adds | Feed |
|---|---|---|
| USGS | Earthquakes M4.5+ in the past day | `earthquake.usgs.gov` GeoJSON summary feed |
| NWS | Active **Severe** and **Extreme** US alerts | `api.weather.gov/alerts/active` |
| NOAA SPC | Tornado, damaging wind, and large hail reports (yesterday + today) | `spc.noaa.gov/climo/reports` CSV |
| NHC | Active Atlantic / Pacific tropical cyclones | `nhc.noaa.gov/CurrentStorms.json` |
| NASA EONET | Wildfires, volcanoes, storms, ice, other natural events (open, last 7 days) | `eonet.gsfc.nasa.gov/api/v3/events` |
| GDACS | Orange/Red global disaster alerts (cyclones, floods, drought, volcanoes, wildfires) | `gdacs.org/gdacsapi` |

Only headlines and coordinates are stored. Each headline links back to its original source.
The same storm or volcano reported by several feeds is shown once (NHC preferred, then GDACS, then EONET).
Earthquakes come from USGS only.

## Research & Trends tab

`fetch_research.py` collects recently published weather and climate research from plain-language
science news and from journal feeds:

| Kind | Sources |
|---|---|
| News & explainers | ScienceDaily (weather, climate), Phys.org (earth sciences, environment; filtered to weather/climate), Carbon Brief, Yale Climate Connections, NOAA News |
| New papers | Nature Climate Change, BAMS, Journal of Climate (via Crossref), Geophysical Research Letters, Weather and Climate Dynamics |

- **Morning briefing**: four recent news stories on different topics plus one notable new paper.
- **What's being studied**: stories and papers per topic over the last 7 days, compared with the week before.
  Topics are assigned by keyword matching. Week-over-week changes appear once two weeks of history exist.
- **Recent reading**: everything from the last 14 days, filterable by type, topic, and text.

Every item ever seen is kept for 9 weeks in `data/research_archive.json` so the trend comparison
doesn't depend on how far back each feed reaches.

## Files

- `fetch_data.py`: downloads every feed and writes `data/events.json` and `data/events.js`. Standard-library Python, nothing to install.
- `fetch_research.py`: collects research items and writes `data/research.js` and `data/research_archive.json`.
- `index.html`, `styles.css`: the page and its two tabs.
- `script.js`: Hazards tab (Leaflet map + filterable headline list) and tab switching.
- `reading.js`: Research & Trends tab.
- `data/zone_cache.json`: cached NWS zone locations so repeat runs don't re-download them.
- `data/update.log`: one line per run with per-source status.

If a source is down during a run, its previous headlines are kept and the page shows a warning banner.

## Running

```
python fetch_data.py
```

Then open `index.html` in a browser (double-click works; no web server needed).

## Daily update & hosting

The site is hosted on GitHub Pages. The workflow in `.github/workflows/update.yml` runs every day
at 11:00 UTC: it runs both fetch scripts, commits the refreshed `data/` folder, and redeploys.
It also runs on every push to `main`, and can be started by hand from the repository's
**Actions → Update and deploy → Run workflow**.

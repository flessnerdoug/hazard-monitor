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

## Files

- `fetch_data.py`: downloads every feed and writes `data/events.json` and `data/events.js`. Standard-library Python, nothing to install.
- `index.html`, `styles.css`, `script.js`: the dashboard (Leaflet map + filterable headline list).
- `data/zone_cache.json`: cached NWS zone locations so repeat runs don't re-download them.
- `data/update.log`: one line per run with per-source status.

If a source is down during a run, its previous headlines are kept and the page shows a warning banner.

## Running

```
python fetch_data.py
```

Then open `index.html` in a browser (double-click works; no web server needed).

## Daily update

A Windows scheduled task, **Hazard Monitor Daily Update**, runs `fetch_data.py` every day at 6:00 AM.
If the PC is off at that time it runs at the next opportunity.

- Run it now: `Start-ScheduledTask "Hazard Monitor Daily Update"`
- Change time or remove it: Task Scheduler → Task Scheduler Library → *Hazard Monitor Daily Update*

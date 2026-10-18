# Tec-C web UI

Two static pages, no build step:

- `index.html`: the landing page. Jaguar hero slider; scrolling runs the jaguar into a cave, out through the light, into the forest sections.
- `app.html`: the Command Center dashboard (composer, live pipeline, ratings, portfolio and regime radar, morning review, scenarios, settings).

## Run

```bash
# 1. the Brain API (optional; without it every screen shows demo data and says so)
cd agent && .venv/bin/uvicorn tecc_brain.app:app --host 127.0.0.1 --port 8000

# 2. the UI, on an origin the API allows (TECC_CORS_ORIGINS defaults to :3000)
cd web && python3 -m http.server 3000 --bind 127.0.0.1
open http://127.0.0.1:3000/
```

Use `127.0.0.1:3000`, not `localhost:3000`, if another dev server already owns `localhost`.

## Live wiring (app.html)

| Screen | Endpoint |
|---|---|
| Brain status pill | `GET /health`, polled every 20 s |
| Ask bar and composer "Submit" | `POST /api/mandate/propose` (the six agents animate in the pipeline) |
| Execute | `POST /api/mandate/execute` (one shot per proposal) |
| Regime radar | `GET /api/risk/regimes?scenario=demo\|usdc_distress` |
| Headline sandbox | `POST /api/sentinel/headline` |
| Ratify, flag and notes on live trades | `POST /api/review/sync` |
| Emergency sweep | `POST /trigger_hourly_monitor` |
| Learned profile | `GET /api/profile/demo` |

Point at another local port with `app.html?api=http://127.0.0.1:8001` (remembered). Only loopback addresses are accepted, so a crafted link cannot redirect your commands to someone else's server.

## Landing URL switches

- `?run=sprite` swaps the photo jaguar for the 1887 Muybridge gallop sprite (also the "Run:" toggle in the hero footer).
- `?skip` skips the preloader. It is skipped automatically on a second visit in the same tab session.
- `?seq=0.4` jumps to a point in the run sequence (0 to 1). `?at=senses` jumps to a section.

## Assets

Everything under `assets/img` comes from Wikimedia Commons (licenses and authors are in the landing footer). The jaguar cut-out was made with macOS Vision subject lifting. The gallop sprite was built from Muybridge's *Animal Locomotion* plate 719: thresholded silhouettes filled with jaguar fur.

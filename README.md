# Gagarin

**Terrain Contour Matching (TERCOM) navigation for GNSS-denied UAV operations.**

Estimates position and velocity of an aircraft by correlating radar altimeter
profiles against a digital elevation model (DEM). Designed for commercial UAVs
operating without GNSS (GPS-denied environments).

Includes a **pre-flight mission planning** toolchain: analyses terrain
informativeness along the route before takeoff, identifies segments at risk of
false TERCOM matches, and packages the data for onboard use.

---

## Quick Start

Launch the interactive TERCOM simulation:

```bash
pip install -e .
uvicorn simulation_ui.main:app
```

Opens a real‑time step‑by‑step simulation of the full TERCOM pipeline
(DEM loading → NMEA parsing → correlation → ESKF → result).

## Commands

| Command | Description |
|---|---|
| `gagarin prepare-route` | Pre‑flight: evaluate terrain along waypoints, build mission package |
| `gagarin viz-mission` | Generate interactive mission viewer HTML from a mission package |
| `gagarin generate-dem` | Generate a synthetic DEM (400×400, procedural terrain) |
| `gagarin generate-all` | Generate all 10 scenario DEMs at once |
| `gagarin download-dem` | Download Copernicus GLO‑30 tiles for a region |
| `gagarin analyze NMEA_FILE` | Process a pre‑recorded NMEA log file (offline or real‑time) |

See `gagarin <command> --help` for options.

### Pre-flight workflow

```bash
# 1. Create a waypoints CSV (lat,lon per line)
cat > waypoints.csv <<EOF
lat,lon
56.10,160.60
56.12,160.63
56.15,160.68
56.18,160.72
56.20,160.75
56.23,160.77
EOF

# 2. Analyse terrain along the route, compute fingerprints, build mission package
gagarin prepare-route --waypoints waypoints.csv -d data/dem/dramatic_kamchatka.tif -o mission_pkg

# 3. Open the interactive pre-flight viewer
gagarin viz-mission mission_pkg
```

Output: `mission_viewer.html` with three panels — route map + info heatmap,
terrain informativeness profile along the route, and fingerprint NCC matrix
(lateral offset vs. self-match) for false‑fix risk assessment.

## Documentation

| Document | Contents |
|---|---|
| `AGENTS.md` | Technical context for AI coding agents |

## Project Structure

```
simulation_ui/       Interactive TERCOM simulation server (FastAPI + SSE)
  main.py            FastAPI app: GET /api/simulate/{id} → SSE stream (14 steps)
  runner.py          SimulationRunner — orchestrates DEM + pipeline → StepData
  svg_generator.py   13 SVG generators for real‑time step visualisation
  texts.py           Explanations for all 14 pipeline steps
  static/            SPA frontend (app.js + style.css)
gagarin/
  main.py            CLI (prepare-route, viz-mission, analyze, ...)
  config.py          All tunable parameters (window, steps, thresholds)
  nmea_parser.py     pynmea2 wrapper → NMEAReading dataclass
  buffer.py          NMEABuffer — sliding window with adaptive distance
  dem_loader.py      DEMLoader, CoordinateTransformer, DEMInterpolator
  correlator.py      TERCOMCorrelator, HypothesisSearch, CorrelationMetrics
  estimator.py       VelocityEstimator → NavigationEstimate (dataclass)
  geo_utils.py       Spherical coordinate formulas, batch offset
  quality.py         _assess() — good/marginal/poor + confidence score
  eskf.py            Error‑State Kalman Filter (6D, solve, degree‑bug free)
  pipeline.py        NavigationPipeline — orchestrator (buffer→corr→dr→KF)
  preprocess.py      TerrainAnalyzer, MissionPreprocessor — pre‑flight planning
                     (fingerprints, adaptive corridor, SQLite + GeoTIFF packaging)
  data_generator.py  Flight simulation → NMEA strings with noise
  profile.py         Baro/radar profile extraction and validation
  viz/mission.py     mission_viewer — pre‑flight 3‑panel HTML viewer
data/
  dem/               10 GeoTIFF files (synthetic_kamchatka.tif, caucasus.tif, …)
  output/            Mission viewer HTML, estimates.json
tests/               40 tests (config, geo_utils, eskf, nmea_parser, correlator, estimator)
```

## Performance

- 40 tests in ~0.3 s
- 231 estimates per 300 s flight in ~13 s real‑time (~60 ms/search)
- ESKF predict/update/reset ≪ 1 ms
- Pre‑flight: 6 waypoints → 122 fingerprint points in ~5 s
- Target (RPi ARM64): <100 ms/search via JIT

## DEMs

| DEM | Size | Elevation | Std | Description |
|-----|------|-----------|-----|-------------|
| `synthetic_kamchatka.tif` | 400×400 | 67–547 m | 99 m | Smooth, for development |
| `dramatic_kamchatka.tif` | 400×400 | 1–3489 m | 688 m | 6 volcanoes + ridges + canyons |
| `caucasus.tif` | 400×400 | 1–4114 m | 953 m | High peaks, deep gorges |
| `ural.tif` | 400×400 | 87–1600 m | 495 m | Gentle mountain range |
| `altai.tif` | 400×400 | 103–3671 m | 817 m | Plateau + peaks |
| `crimea.tif` | 400×400 | 1–1192 m | 326 m | Ridge + sea level |
| `siberia.tif` | 400×400 | 30–86 m | 17 m | Flat plain |
| `sakhalin.tif` | 400×400 | 1–900 m | 358 m | Island + hills |
| `karelia.tif` | 400×400 | 28–391 m | 85 m | Hills + lakes |
| `primorye.tif` | 400×400 | 1–887 m | 222 m | Coastal hills |

All generated with `gagarin generate-all`.

## Approach

- **Coarse‑to‑fine search**: 10° coarse azimuth sweep → 0.5° fine search around top‑5 candidates. Speed refined simultaneously.
- **Dead reckoning fallback**: when correlation fails (flat terrain or sensor noise), the pipeline falls back to ESKF prediction + last‑estimate extrapolation instead of producing garbage matches.
- **Pre‑flight fingerprinting**: for each waypoint, the terrain is evaluated with multiple metrics — std elevation, gradient magnitude, Minima Ratio (Akinci 2026), and NCC under lateral offset. Fingerprint profiles are stored in SQLite with an R‑Tree spatial index, packaged together with a GeoTIFF info map.

## License

MIT — see `LICENSE`.

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

```bash
pip install -e .
gagarin run
```

Opens `data/output/dashboard.html` (interactive Plotly dashboard) and
`data/output/estimates.json` after processing a simulated 300‑second flight.

For a side‑by‑side comparison of smooth vs. rugged DEMs:

```bash
gagarin run --compare
```

## Commands

| Command | Description |
|---|---|
| `gagarin run` | Full pipeline: simulate flight → correlate → visualize |
| `gagarin run --compare` | Run on both synthetic and dramatic DEMs side‑by‑side |
| `gagarin prepare-route` | Pre‑flight: evaluate terrain along waypoints, build mission package |
| `gagarin viz-mission` | Generate interactive mission viewer HTML from a mission package |
| `gagarin generate-dem` | Generate a synthetic DEM (400×400, procedural volcanoes + ridges) |
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
| `HOW_IT_WORKS.md` | Component walkthrough: physics, math, startup behaviour |
| `HOW_IT_WORKS_KIDS.md` | Simplified (non‑technical) explanation |
| `AGENTS.md` | Technical context for AI coding agents |
| `DEVELOPMENT_PLAN.md` | Roadmap with 7 phases, known weaknesses, research directions |

## Project Structure

```
gagarin/
  main.py            CLI (run, prepare-route, viz-mission, analyze, ...)
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
  viz/               Plotly HTML visualisations
    __init__.py      Public API: heatmap, trajectory, profile, dashboard, mission
    dashboard.py     navigation_dashboard (single DEM), unified_dashboard (comparison)
    mission.py       mission_viewer — pre‑flight 3‑panel HTML
    components.py    Shared trace factories (terrain, profile, timeline, error, heatmap, drift, pie)
    data_model.py    DashboardData dataclass + build_dashboard_data factory
    template.py      GitHub‑Dark HTML template with tabs
    utils.py         save_html / save_dashboard / get_grid_or_fallback
    trajectory.py    trajectory_map() — 2D true vs. estimated track
    heatmap.py       correlation_heatmap() — coarse NCC matrix
    profiles.py      profile_comparison() — observed vs. reference DEM profile
data/
  dem/               GeoTIFF files (synthetic_kamchatka.tif, dramatic_kamchatka.tif)
  output/            HTML dashboards, mission viewer, estimates.json
tests/               32 tests (config, geo_utils, eskf, nmea_parser, correlator, estimator)
```

## Performance

- 32 tests in ~0.3 s
- 231 estimates per 300 s flight in ~13 s real‑time (~60 ms/search)
- ESKF predict/update/reset ≪ 1 ms
- Pre‑flight: 6 waypoints → 122 fingerprint points in ~5 s
- Target (RPi ARM64): <100 ms/search via numba JIT

## DEMs

| DEM | Size | Elevation | Std | Description |
|-----|------|-----------|-----|-------------|
| `synthetic_kamchatka.tif` | 400×400 | 101–600 m | 95 m | Smooth, for development |
| `dramatic_kamchatka.tif` | 400×400 | 10–3489 m | 687 m | 6 volcanoes + ridges + canyons |

Both generated with `gagarin generate-dem`.

## Approach

- **Coarse‑to‑fine search**: 10° coarse azimuth sweep → 0.5° fine search around top‑5 candidates. Speed refined simultaneously.
- **Dead reckoning fallback**: when correlation fails (flat terrain or sensor noise), the pipeline falls back to ESKF prediction + last‑estimate extrapolation instead of producing garbage matches.
- **Pre‑flight fingerprinting**: for each waypoint, the terrain is evaluated with multiple metrics — std elevation, gradient magnitude, Minima Ratio (Akinci 2026), and NCC under lateral offset. Fingerprint profiles are stored in SQLite with an R‑Tree spatial index, packaged together with a GeoTIFF info map.

## License

MIT — see `LICENSE`.

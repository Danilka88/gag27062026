# Gagarin

**Terrain Contour Matching (TERCOM) navigation for GNSS-denied UAV operations.**

Estimates position and velocity of an aircraft by correlating radar altimeter
profiles against a digital elevation model (DEM). Designed for commercial UAVs
operating without GNSS (GPS-denied environments).

---

## Quick Start

```bash
pip install -e .
gagarin run
```

Opens `data/output/dashboard.html` (interactive Plotly dashboard) and
`data/output/estimates.json` after processing a simulated 300‑second flight.

## Commands

| Command | Description |
|---|---|
| `gagarin run` | Full pipeline: simulate flight → correlate → visualize |
| `gagarin run --compare` | Run on both synthetic and dramatic DEMs side‑by‑side |
| `gagarin generate-dem` | Generate a synthetic DEM (400×400, Perlin noise) |
| `gagarin download-dem` | Download Copernicus GLO‑30 tiles for a region |
| `gagarin analyze NMEA_FILE` | Process a pre‑recorded NMEA log file |

See `gagarin <command> --help` for options.

## Documentation

| Document | Contents |
|---|---|
| `HOW_IT_WORKS.md` | Component walkthrough: physics, math, startup behaviour |
| `HOW_IT_WORKS_KIDS.md` | Simplified (non‑technical) explanation |
| `TECH_STACK.md` | Why each library/algorithm was chosen, alternatives, scaling |
| `AGENTS.md` | Technical context for AI coding agents |

## Project Structure

```
gagarin/
  main.py            CLI (run, download-dem, generate-dem, analyze)
  config.py          All tunable parameters (window, steps, thresholds)
  nmea_parser.py     pynmea2 wrapper → NMEAReading
  buffer.py          NMEABuffer — sliding window over readings
  dem_loader.py      DEMLoader, CoordinateTransformer, DEMInterpolator
  correlator.py      TERCOMCorrelator, HypothesisSearch, CorrelationMetrics
  estimator.py       VelocityEstimator → NavigationEstimate (dataclass)
  geo_utils.py       Spherical coordinate formulas, batch offset
  quality.py         _assess() — good/marginal/poor classification
  eskf.py            Error‑State Kalman Filter (6D, solve, degree‑bug free)
  pipeline.py        NavigationPipeline — orchestrator (buffer→corr→dr→KF)
  data_generator.py  Flight simulation → NMEA strings with noise
  viz/               Plotly HTML visualisations (dashboard, trajectory, profile, heatmap)
data/
  dem/               GeoTIFF files (synthetic_kamchatka.tif, dramatic_kamchatka.tif)
  output/            HTML dashboards + estimates.json
tests/               32 tests (config, geo_utils, eskf, nmea_parser, correlator, estimator)
```

## Performance

- 32 tests in ~0.3 s
- 231 estimates per 300 s flight in ~13 s real‑time (~60 ms/search)
- ESKF predict/update/reset ≪ 1 ms
- Target (RPi ARM64): <100 ms/search via numba JIT

## DEMs

| DEM | Size | Elevation | Std | Description |
|-----|------|-----------|-----|-------------|
| `synthetic_kamchatka.tif` | 400×400 | 101–600 m | 95 m | Smooth, for development |
| `dramatic_kamchatka.tif` | 400×400 | 10–3489 m | 687 m | 6 volcanoes + canyons + ridges |

Both generated with `gagarin generate-dem`.

## License

MIT — see `LICENSE`.

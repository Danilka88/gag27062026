import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

import numpy as np
import plotly.graph_objects as go




def _load_features(db_path: str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    wps = [dict(r) for r in conn.execute("SELECT * FROM waypoints ORDER BY id")]
    feats = [
        dict(r) for r in conn.execute(
            "SELECT f.*, w.lat, w.lon FROM features f "
            "JOIN waypoints w ON w.id = f.waypoint_id "
            "ORDER BY f.waypoint_id"
        )
    ]
    cfg = dict(conn.execute("SELECT key, value FROM mission_config"))
    conn.close()
    for f in feats:
        if isinstance(f.get("expected_ncc_offsets"), str):
            f["expected_ncc_offsets"] = json.loads(f["expected_ncc_offsets"])
        if isinstance(f.get("offset_distances_m"), str):
            f["offset_distances_m"] = json.loads(f["offset_distances_m"])
    return wps, feats, cfg


def _build_map_traces(wps, feats, info_map_path: Optional[str], cfg: dict):
    traces = []

    if info_map_path and os.path.exists(info_map_path):
        import rioxarray
        ds = rioxarray.open_rasterio(info_map_path, masked=True).squeeze()
        lons = ds.x.values
        lats = ds.y.values
        z = ds.values
        traces.append(go.Heatmap(
            z=z,
            x=lons,
            y=lats,
            colorscale="Viridis",
            opacity=0.6,
            name="Info Map",
            colorbar=dict(title="Info score", x=1.02),
            showscale=True,
        ))

    wp_lons = [w["lon"] for w in wps]
    wp_lats = [w["lat"] for w in wps]
    traces.append(go.Scatter(
        x=wp_lons, y=wp_lats,
        mode="lines+markers",
        line=dict(color="red", width=2),
        marker=dict(color="red", size=5),
        name="Маршрут",
    ))

    if feats:
        good_x, good_y = [], []
        warn_x, warn_y = [], []
        bad_x, bad_y = [], []
        for f in feats:
            v = f.get("minima_ratio", 1.0)
            x, y = f.get("lon", 0), f.get("lat", 0)
            if v > 0.8:
                good_x.append(x)
                good_y.append(y)
            elif v > 0.5:
                warn_x.append(x)
                warn_y.append(y)
            else:
                bad_x.append(x)
                bad_y.append(y)

        if good_x:
            traces.append(go.Scatter(
                x=good_x, y=good_y,
                mode="markers", marker=dict(color="green", size=4, symbol="circle"),
                name="Надёжно (minima_ratio>0.8)",
            ))
        if warn_x:
            traces.append(go.Scatter(
                x=warn_x, y=warn_y,
                mode="markers", marker=dict(color="orange", size=4, symbol="circle"),
                name="Средне (0.5–0.8)",
            ))
        if bad_x:
            traces.append(go.Scatter(
                x=bad_x, y=bad_y,
                mode="markers", marker=dict(color="red", size=4, symbol="circle"),
                name="Риск (<0.5)",
            ))

    return traces


def _build_info_profile(feats, wp_lats):
    if not feats:
        return go.Figure().update_layout(template="plotly_dark", title="Нет данных")

    indices = [f.get("waypoint_index", i) for i, f in enumerate(feats)]
    std_vals = [f.get("std_elevation", 0) for f in feats]
    grad_vals = [f.get("gradient_magnitude", 0) for f in feats]
    minima_vals = [f.get("minima_ratio", 0) for f in feats]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=indices, y=std_vals,
        mode="lines+markers",
        name="std высот (м)",
        line=dict(color="cyan", width=2),
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        x=indices, y=grad_vals,
        mode="lines+markers",
        name="gradient magnitude",
        line=dict(color="orange", width=2),
        yaxis="y2",
    ))
    fig.add_trace(go.Scatter(
        x=indices, y=minima_vals,
        mode="lines+markers",
        name="Minima Ratio",
        line=dict(color="lime", width=2, dash="dot"),
        yaxis="y3",
    ))

    fig.update_layout(
        template="plotly_dark",
        height=350,
        margin=dict(l=60, r=60, t=30, b=40),
        xaxis=dict(title="Индекс точки вдоль маршрута"),
        yaxis=dict(title="std (м)", color="cyan"),
        yaxis2=dict(title="Gradient", overlaying="y", side="right", color="orange"),
        yaxis3=dict(title="Minima Ratio", overlaying="y", side="right", position=0.95, color="lime"),
        legend=dict(x=1.05, y=1, xanchor="left"),
    )
    return fig


def _build_fingerprint_heatmap(feats, wp_lats):
    if not feats or not feats[0].get("expected_ncc_offsets"):
        return go.Figure().update_layout(template="plotly_dark", title="Нет fingerprint данных")

    offsets = feats[0].get("offset_distances_m", [])
    n_offsets = len(offsets)
    n_pts = len(feats)
    matrix = np.zeros((n_pts, n_offsets))

    for i, f in enumerate(feats):
        vals = f.get("expected_ncc_offsets", [])
        for j in range(min(len(vals), n_offsets)):
            matrix[i, j] = vals[j] if vals[j] is not None else -1

    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=offsets,
        y=list(range(n_pts)),
        colorscale="RdYlBu_r",
        zmin=-1,
        zmax=1,
        colorbar=dict(title="NCC"),
    ))
    fig.update_layout(
        template="plotly_dark",
        height=400,
        margin=dict(l=60, r=40, t=30, b=60),
        xaxis=dict(title="Смещение от трека (м)"),
        yaxis=dict(title="Точка маршрута"),
    )
    return fig


def mission_viewer(
    mission_dir: str,
    output_path: str = "mission_viewer.html",
    dashboard_path: Optional[str] = None,
):
    p = Path(mission_dir)
    db_path = p / "fingerprints.db"
    info_map_path = p / "dem" / "info_map.tif"
    meta_path = p / "metadata.json"

    if not db_path.exists():
        raise FileNotFoundError(f"Mission package not found: {db_path}")

    wps, feats, cfg = _load_features(str(db_path))

    meta = {}
    if meta_path.exists():
        with open(meta_path) as f:
            meta = json.load(f)

    map_traces = _build_map_traces(wps, feats, str(info_map_path) if info_map_path.exists() else None, cfg)

    fig_map = go.Figure(data=map_traces)

    fig_map.update_layout(
        template="plotly_dark",
        height=500,
        margin=dict(l=40, r=40, t=10, b=40),
        xaxis=dict(title="Долгота", scaleanchor="y", scaleratio=1),
        yaxis=dict(title="Широта"),
        legend=dict(x=1.02, y=1, xanchor="left"),
    )

    fig_profile = _build_info_profile(feats, [w["lat"] for w in wps])
    fig_fp = _build_fingerprint_heatmap(feats, [w["lat"] for w in wps])

    az = meta.get("azimuth_deg", cfg.get("azimuth_deg", "?"))
    sp = meta.get("speed_ms", cfg.get("speed_ms", "?"))

    card_map = (
        '<div class="card">'
        '<div class="card-title">Карта маршрута и информативность рельефа</div>'
        '<div class="chart-container" id="chart-map"></div>'
        '<div class="caption">'
        'Красная линия — маршрут. Цветные точки — качество TERCOM: '
        '<b>зелёные</b> — высокий Minima Ratio (>0.8), <b>оранжевые</b> — средний (0.5–0.8), '
        '<b>красные</b> — низкий (<0.5), риск false fix.<br>'
        'Фон — информационная карта: gradient + std (Viridis: тёмный=плохо, яркий=хорошо).'
        '</div></div>'
    )

    card_profile = (
        '<div class="card">'
        '<div class="card-title">Профиль информативности вдоль маршрута</div>'
        '<div class="chart-container" id="chart-profile"></div>'
        '<div class="caption">'
        '<b>Голубая линия</b> — std высот в окне (чем выше, тем информативнее рельеф). '
        '<b>Оранжевая</b> — gradient magnitude. <b>Зелёная пунктирная</b> — Minima Ratio (Akinci 2026).<br>'
        'Падение Minima Ratio ниже 0.5 означает, что TERCOM может найти ложное совпадение на этом участке.'
        '</div></div>'
    )

    card_fp = (
        '<div class="card">'
        '<div class="card-title">Fingerprint-матрица: NCC при смещении от трека</div>'
        '<div class="chart-container" id="chart-fingerprint"></div>'
        '<div class="caption">'
        'Для каждой точки маршрута показан ожидаемый NCC между profile на треке и profile на расстоянии ±offset. '
        '<b>Красный</b> = высокое совпадение (профили похожи — риск false fix), '
        '<b>синий</b> = низкое (профили разные — TERCOM надёжен).'
        '</div></div>'
    )

    summary = (
        f"<b>Маршрут:</b> {len(wps)} waypoints, "
        f"<b>{len(feats)}</b> fingerprint точек | "
        f"Курс: {az}° | Скорость: {sp} м/с | "
        f"Коридор: {meta.get('corridor_width_m', cfg.get('corridor_width_m', '?'))} м"
    )

    nav_links = ""
    if dashboard_path and os.path.exists(dashboard_path):
        rel = os.path.relpath(dashboard_path, os.path.dirname(output_path))
        nav_links += (
            f'<a class="nav-link" href="{rel}" target="_blank">'
            f"&larr; TERCOM Dashboard</a>"
        )

    figs_json = json.dumps([
        {"id": "map", "figure": fig_map.to_plotly_json()},
        {"id": "profile", "figure": fig_profile.to_plotly_json()},
        {"id": "fingerprint", "figure": fig_fp.to_plotly_json()},
    ]).replace("</", "<\\/")

    html = MISSION_HTML_TEMPLATE.replace("{NAV_LINKS}", nav_links, 1)
    html = html.replace("{SUMMARIES}", summary, 1)
    html = html.replace("{CARDS_HTML}", card_map + card_profile + card_fp, 1)
    html = html.replace("{CHARTS_JSON}", figs_json, 1)

    with open(output_path, "w") as f:
        f.write(html)

    return output_path


MISSION_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Mission Viewer — TERCOM Pre-flight</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#0d1117;color:#e6edf3;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;line-height:1.5}
header{max-width:1200px;margin:0 auto;padding:24px 24px 0}
h1{font-size:22px;font-weight:600;margin-bottom:12px;letter-spacing:-0.3px}
.summaries{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:24px;padding:12px 16px;background:#161b22;border-radius:8px;border:1px solid #30363d;font-size:14px;color:#8b949e;line-height:1.6}
.summaries b{color:#f0f6fc}
.tabs{display:flex;gap:8px;margin-bottom:8px}
.tab{padding:8px 20px;border-radius:20px;border:1px solid #30363d;background:0 0;color:#8b949e;font-size:14px;cursor:pointer;transition:.2s;font-family:inherit}
.tab:hover{color:#e6edf3;border-color:#58a6ff}
.tab.active{background:#58a6ff;color:#fff;border-color:#58a6ff}
.nav-links{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
.nav-link{padding:6px 16px;border-radius:16px;border:1px solid #30363d;background:#161b22;color:#8b949e;font-size:13px;cursor:pointer;transition:.2s;text-decoration:none}
.nav-link:hover{color:#e6edf3;border-color:#58a6ff;background:#1c2333}
main{max-width:1200px;margin:0 auto;padding:0 24px 48px;display:flex;flex-direction:column;gap:20px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;overflow:hidden}
.card-title{font-size:15px;font-weight:600;padding:14px 16px 0;color:#e6edf3;letter-spacing:-0.2px}
.card-subtitle{font-size:13px;color:#8b949e;padding:4px 16px 8px}
.chart-container{width:100%}
.chart-container .js-plotly-plot,.chart-container .plot-container,.chart-container .svg-container{width:100%!important}
.caption{padding:12px 16px 16px;font-size:14px;color:#c9d1d9;line-height:1.6;border-top:1px solid #1e252e}
.caption b{color:#f0f6fc}
@media(max-width:768px){header{padding:16px 12px 0}main{padding:0 12px 24px;gap:12px}.summaries{flex-direction:column;gap:4px}}
</style>
</head>
<body>
<header>
<h1>Pre-flight Mission Analysis</h1>
<div class="nav-links">{NAV_LINKS}</div>
<div class="summaries">{SUMMARIES}</div>
</header>
<main>
{CARDS_HTML}
</main>
<script>
var CHARTS = {CHARTS_JSON};
document.addEventListener('DOMContentLoaded', function() {
  for (var i = 0; i < CHARTS.length; i++) {
    var el = document.getElementById('chart-' + CHARTS[i].id);
    if (el) {
      Plotly.newPlot(el, CHARTS[i].figure, {responsive: true, displayModeBar: false});
    }
  }
});
</script>
</body>
</html>"""

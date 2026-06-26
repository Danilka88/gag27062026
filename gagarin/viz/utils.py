import os
from typing import Optional, Tuple
import json
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

from gagarin.dem_loader import DEMLoader
from gagarin.viz.template import HTML_TEMPLATE

TEMPLATE = "plotly_dark"

BEST_MARKER = dict(color="lime", size=14, symbol="star")
ESTIMATED_LINE = dict(color="lime", width=2, dash="dash")
TRUE_LINE = dict(color="red", width=3)
OBSERVED_COLOR = "cyan"
REFERENCE_COLOR = "orange"


def get_grid_or_fallback(dem: DEMLoader) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    try:
        return dem.get_geographic_grid()
    except (NotImplementedError, AttributeError):
        xs, ys, elevation = dem.get_elevation_grid()
        return xs, ys, elevation


def save_html(fig: go.Figure, path: str):
    pio.write_html(fig, path, auto_open=False)


def save_dashboard(charts: list, path: str, mission_viewer_path: Optional[str] = None):
    nav_links = ""
    if mission_viewer_path and os.path.exists(mission_viewer_path):
        rel = os.path.relpath(mission_viewer_path, os.path.dirname(path))
        nav_links += (
            f'<a class="nav-link" href="{rel}" target="_blank">'
            f"Pre-flight Analysis &rarr;</a>"
        )

    cards_html = "\n".join(
        f'<div class="card">'
        f'<div class="card-title">{c["title"]}</div>'
        f'<div class="chart-container" id="chart-{c["id"]}"></div>'
        f'<div class="caption">{c["caption"]}</div>'
        f"</div>"
        for c in charts
    )
    charts_data = [
        {
            "id": c["id"],
            "figure": c["fig"].to_plotly_json(),
            "syn_vis": [bool(v) for v in c["syn_vis"]],
            "dram_vis": [bool(v) for v in c["dram_vis"]],
        }
        for c in charts
    ]
    charts_json = json.dumps(charts_data).replace("</", "<\\/")
    html = HTML_TEMPLATE.replace("{NAV_LINKS}", nav_links, 1)
    html = html.replace("{SUMMARIES}", "", 1)
    html = html.replace("{CARDS_HTML}", cards_html, 1)
    html = html.replace("{CHARTS_JSON}", charts_json, 1)
    with open(path, "w") as f:
        f.write(html)

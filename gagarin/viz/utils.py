from typing import Tuple
import numpy as np
import plotly.graph_objects as go
import plotly.io as pio

from gagarin.dem_loader import DEMLoader

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

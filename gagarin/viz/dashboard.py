from typing import Optional, List
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

from gagarin.dem_loader import DEMLoader


def navigation_dashboard(
    dem: DEMLoader,
    trajectory_lats: np.ndarray,
    trajectory_lons: np.ndarray,
    estimates: List[dict],
    azimuths: np.ndarray,
    speeds: np.ndarray,
    corr_matrix: np.ndarray,
    observed_profile: Optional[np.ndarray] = None,
    reference_profile: Optional[np.ndarray] = None,
) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=2,
        specs=[
            [{"type": "scene"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}],
        ],
        subplot_titles=(
            "3D Terrain & Trajectory",
            "Correlation Heatmap",
            "Profile Comparison",
            "Position Estimates",
        ),
        vertical_spacing=0.12,
        horizontal_spacing=0.1,
    )

    try:
        lons, lats, elevation = dem.get_geographic_grid()
    except (NotImplementedError, AttributeError):
        xs, ys, elevation = dem.get_elevation_grid()
        lons = xs
        lats = ys

    lon_grid, lat_grid = np.meshgrid(lons, lats)

    fig.add_trace(
        go.Surface(
            z=elevation,
            x=lon_grid if lon_grid.shape == elevation.shape else None,
            y=lat_grid if lat_grid.shape == elevation.shape else None,
            colorscale="Earth",
            name="Terrain",
            showscale=False,
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        go.Scatter3d(
            x=trajectory_lons,
            y=trajectory_lats,
            z=dem.elevation_batch(
                np.array(trajectory_lats), np.array(trajectory_lons)
            ),
            mode="lines+markers",
            line=dict(color="red", width=5),
            marker=dict(size=3, color="red"),
            name="True trajectory",
        ),
        row=1,
        col=1,
    )

    if estimates:
        est_lons = [e["position_lon"] for e in estimates]
        est_lats = [e["position_lat"] for e in estimates]
        try:
            est_zs = dem.elevation_batch(np.array(est_lats), np.array(est_lons))
        except (IndexError, ValueError):
            est_zs = [0] * len(est_lats)
        fig.add_trace(
            go.Scatter3d(
                x=est_lons,
                y=est_lats,
                z=est_zs,
                mode="lines+markers",
                line=dict(color="lime", width=3, dash="dash"),
                marker=dict(size=4, color="lime"),
                name="Estimated",
            ),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Heatmap(
            z=corr_matrix.T,
            x=azimuths,
            y=speeds,
            colorscale="RdBu_r",
            zmid=0,
            showscale=False,
            hovertemplate="Az: %{x:.1f}°<br>Speed: %{y:.1f} m/s<br>Corr: %{z:.3f}<extra></extra>",
        ),
        row=1,
        col=2,
    )

    if observed_profile is not None and reference_profile is not None:
        fig.add_trace(
            go.Scatter(y=observed_profile, mode="lines", name="Observed", line=dict(color="cyan")),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(y=reference_profile, mode="lines", name="Reference", line=dict(color="orange", dash="dash")),
            row=2,
            col=1,
        )

    if estimates:
        est_idx = list(range(len(estimates)))
        est_corr = [e.get("correlation", 0) for e in estimates]
        fig.add_trace(
            go.Scatter(x=est_idx, y=est_corr, mode="lines+markers", name="Correlation", line=dict(color="lime")),
            row=2,
            col=2,
        )
        est_conf = [e.get("confidence", 0) for e in estimates]
        fig.add_trace(
            go.Scatter(x=est_idx, y=est_conf, mode="lines+markers", name="Confidence", line=dict(color="orange", dash="dot")),
            row=2,
            col=2,
        )

    fig.update_layout(
        title="TERCOM Navigation Dashboard",
        height=900,
        template="plotly_dark",
        showlegend=True,
    )

    fig.update_xaxes(title_text="Longitude", row=2, col=2)
    fig.update_yaxes(title_text="Correlation", row=2, col=2)
    fig.update_xaxes(title_text="Sample", row=2, col=1)
    fig.update_yaxes(title_text="Height (m)", row=2, col=1)
    fig.update_xaxes(title_text="Azimuth (°)", row=1, col=2)
    fig.update_yaxes(title_text="Speed (m/s)", row=1, col=2)

    fig.update_scenes(
        aspectmode="data",
        xaxis_title="Lon",
        yaxis_title="Lat",
        zaxis_title="Height (m)",
        row=1,
        col=1,
    )

    return fig


def save_html(fig: go.Figure, path: str):
    pio.write_html(fig, path, auto_open=False)

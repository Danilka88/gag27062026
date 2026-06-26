from typing import Optional, List, Tuple
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

from gagarin.dem_loader import DEMLoader
from gagarin.config import Config


def correlation_heatmap(
    azimuths: np.ndarray,
    speeds: np.ndarray,
    corr_matrix: np.ndarray,
    best_azimuth: Optional[float] = None,
    best_speed: Optional[float] = None,
) -> go.Figure:
    fig = go.Figure(
        data=go.Heatmap(
            z=corr_matrix.T,
            x=azimuths,
            y=speeds,
            colorscale="RdBu_r",
            zmid=0,
            colorbar_title="Correlation",
            hovertemplate="Az: %{x:.1f}°<br>Speed: %{y:.1f} m/s<br>Corr: %{z:.3f}<extra></extra>",
        )
    )
    if best_azimuth is not None and best_speed is not None:
        fig.add_trace(
            go.Scatter(
                x=[best_azimuth],
                y=[best_speed],
                mode="markers",
                marker=dict(color="lime", size=14, symbol="star"),
                name=f"Best: {best_azimuth:.1f}°, {best_speed:.1f} m/s",
            )
        )

    fig.update_layout(
        title="Correlation Heatmap: Azimuth vs Speed",
        xaxis_title="Azimuth (°)",
        yaxis_title="Speed (m/s)",
        xaxis=dict(dtick=30),
        height=600,
        template="plotly_dark",
    )
    return fig


def trajectory_map(
    dem: DEMLoader,
    trajectory_lats: np.ndarray,
    trajectory_lons: np.ndarray,
    estimated_positions: Optional[List[Tuple[float, float]]] = None,
    center_lat: Optional[float] = None,
    center_lon: Optional[float] = None,
    height: int = 700,
) -> go.Figure:
    try:
        lons, lats, elevation = dem.get_geographic_grid()
    except Exception:
        xs, ys, elevation = dem.get_elevation_grid()
        lons = xs
        lats = ys

    fig = go.Figure()
    fig.add_trace(
        go.Contour(
            z=elevation,
            x=lons if len(lons) == elevation.shape[1] else np.arange(elevation.shape[1]),
            y=lats if len(lats) == elevation.shape[0] else np.arange(elevation.shape[0]),
            colorscale="Earth",
            contours=dict(coloring="heatmap"),
            name="Elevation",
            hovertemplate="Elevation: %{z:.1f} m<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=trajectory_lons,
            y=trajectory_lats,
            mode="lines+markers",
            line=dict(color="red", width=3),
            marker=dict(size=4, color="red"),
            name="True trajectory",
        )
    )

    if estimated_positions:
        est_lons = [p[1] for p in estimated_positions]
        est_lats = [p[0] for p in estimated_positions]
        fig.add_trace(
            go.Scatter(
                x=est_lons,
                y=est_lats,
                mode="lines+markers",
                line=dict(color="lime", width=2, dash="dash"),
                marker=dict(size=6, color="lime", symbol="circle"),
                name="Estimated positions",
            )
        )

    if center_lat is not None and center_lon is not None:
        fig.add_trace(
            go.Scatter(
                x=[center_lon],
                y=[center_lat],
                mode="markers",
                marker=dict(color="yellow", size=12, symbol="star"),
                name="Start (assumed center)",
            )
        )

    fig.update_layout(
        title="Trajectory on Elevation Map",
        xaxis_title="Longitude",
        yaxis_title="Latitude",
        height=height,
        template="plotly_dark",
        hovermode="closest",
    )
    return fig


def profile_comparison(
    observed: np.ndarray,
    reference: np.ndarray,
    azimuth: float,
    speed: float,
    correlation: float,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            y=observed,
            mode="lines",
            name="Observed terrain profile",
            line=dict(color="cyan", width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            y=reference,
            mode="lines",
            name=f"Reference profile (az={azimuth:.1f}°, v={speed:.1f} m/s)",
            line=dict(color="orange", width=2, dash="dash"),
        )
    )

    fig.update_layout(
        title=f"Profile Comparison | Correlation: {correlation:.4f}",
        xaxis_title="Sample",
        yaxis_title="Terrain Height (m)",
        height=450,
        template="plotly_dark",
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    return fig


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
    except Exception:
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
        except Exception:
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


def show(fig: go.Figure):
    fig.show()

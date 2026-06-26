from typing import Optional, List, Tuple
import numpy as np
import plotly.graph_objects as go

from gagarin.dem_loader import DEMLoader


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

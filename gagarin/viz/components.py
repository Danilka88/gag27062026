from typing import List, Optional
import numpy as np
import plotly.graph_objects as go

from gagarin.viz.data_model import TerrainData, TrajectoryData, CorrData, ProfileData, ErrorData, EstimateData


def terrain_traces(
    terrain: TerrainData,
    trajectory: TrajectoryData,
    estimates: List[EstimateData],
) -> List[go.Trace]:
    lons, lats = terrain.lons, terrain.lats
    lon_grid, lat_grid = np.meshgrid(lons, lats)

    traces = [
        go.Surface(
            z=terrain.elevation,
            x=lon_grid if lon_grid.shape == terrain.elevation.shape else None,
            y=lat_grid if lat_grid.shape == terrain.elevation.shape else None,
            colorscale="Earth",
            showscale=False,
            name="Рельеф",
        ),
        go.Scatter3d(
            x=trajectory.lons,
            y=trajectory.lats,
            z=trajectory.elevations,
            mode="lines+markers",
            line=dict(color="red", width=5),
            marker=dict(size=3, color="red"),
            name="Истинный путь",
        ),
    ]

    if estimates:
        elons = [e.position_lon for e in estimates]
        elats = [e.position_lat for e in estimates]
        traces.append(
            go.Scatter3d(
                x=elons, y=elats,
                z=[0] * len(elats),
                mode="lines+markers",
                line=dict(color="lime", width=3, dash="dash"),
                marker=dict(size=4, color="lime"),
                name="Оценка TERCOM",
            ),
        )

    filtered = [e for e in estimates if e.filtered_lat is not None and e.filtered_lon is not None]
    if filtered:
        traces.append(
            go.Scatter3d(
                x=[e.filtered_lon for e in filtered],
                y=[e.filtered_lat for e in filtered],
                z=[0] * len(filtered),
                mode="lines+markers",
                line=dict(color="yellow", width=3, dash="dot"),
                marker=dict(size=3, color="yellow"),
                name="ESKF filtered",
            ),
        )

    return traces


def correlation_heatmap_trace(
    corr: CorrData,
    best_azimuth: Optional[float] = None,
    best_speed: Optional[float] = None,
) -> List[go.Trace]:
    corr_range = max(abs(np.min(corr.matrix)), abs(np.max(corr.matrix)))
    zmin, zmax = -corr_range, corr_range

    traces: List[go.Trace] = [
        go.Heatmap(
            z=corr.matrix.T,
            x=corr.azimuths,
            y=corr.speeds,
            colorscale="RdBu_r",
            zmid=0,
            zmin=zmin,
            zmax=zmax,
            showscale=False,
            hovertemplate="Азимут: %{x:.1f}°<br>Скорость: %{y:.1f} м/с<br>Корреляция: %{z:.3f}<extra></extra>",
        ),
    ]

    if best_azimuth is not None and best_speed is not None:
        traces.append(
            go.Scatter(
                x=[best_azimuth],
                y=[best_speed],
                mode="markers",
                marker=dict(color="lime", size=14, symbol="star"),
                name=f"Best: {best_azimuth:.1f}°, {best_speed:.1f} м/с",
            ),
        )

    return traces


def profile_traces(profile: ProfileData) -> List[go.Scatter]:
    if len(profile.observed) == 0 and len(profile.reference) == 0:
        return []
    return [
        go.Scatter(
            y=profile.observed,
            mode="lines",
            name="Измерено",
            line=dict(color="cyan", width=2),
        ),
        go.Scatter(
            y=profile.reference,
            mode="lines",
            name=f"Эталон (az={profile.azimuth_deg:.1f}°, v={profile.speed_ms:.1f} м/с)",
            line=dict(color="orange", width=2, dash="dash"),
        ),
    ]


def timeline_traces(estimates: List[EstimateData]) -> List[go.Scatter]:
    if not estimates:
        return []
    idx = [e.idx for e in estimates]
    return [
        go.Scatter(
            x=idx,
            y=[e.correlation for e in estimates],
            mode="lines+markers",
            name="Корреляция",
            line=dict(color="lime", width=2),
            marker=dict(size=3),
        ),
        go.Scatter(
            x=idx,
            y=[e.confidence for e in estimates],
            mode="lines+markers",
            name="Доверие",
            line=dict(color="orange", width=2, dash="dot"),
            marker=dict(size=3),
        ),
    ]


def error_traces(errors: ErrorData) -> List[go.Scatter]:
    if len(errors.azimuth_errors) == 0 and len(errors.speed_errors) == 0:
        return []
    idx = list(range(max(len(errors.azimuth_errors), len(errors.speed_errors))))
    traces: List[go.Scatter] = []

    if len(errors.azimuth_errors) > 0:
        traces.append(
            go.Scatter(
                x=idx[:len(errors.azimuth_errors)],
                y=errors.azimuth_errors,
                mode="lines+markers",
                name="Ошибка азимута (°)",
                line=dict(color="magenta", width=2),
                marker=dict(size=3),
            ),
        )
    if len(errors.speed_errors) > 0:
        traces.append(
            go.Scatter(
                x=idx[:len(errors.speed_errors)],
                y=errors.speed_errors,
                mode="lines+markers",
                name="Ошибка скорости (м/с)",
                line=dict(color="cyan", width=2, dash="dash"),
                marker=dict(size=3),
                yaxis="y2",
            ),
        )
    return traces


def drift_traces(trajectory: TrajectoryData, estimates: List[EstimateData]) -> List[go.Scatter]:
    traces: List[go.Scatter] = [
        go.Scatter(
            x=trajectory.lons,
            y=trajectory.lats,
            mode="lines",
            line=dict(color="red", width=3),
            name="Истинный путь",
        ),
    ]
    if estimates:
        traces.append(
            go.Scatter(
                x=[e.position_lon for e in estimates],
                y=[e.position_lat for e in estimates],
                mode="lines+markers",
                line=dict(color="lime", width=2, dash="dash"),
                marker=dict(size=4, color="lime"),
                name="Оценка TERCOM",
            ),
        )

    filtered = [e for e in estimates if e.filtered_lat is not None and e.filtered_lon is not None]
    if filtered:
        traces.append(
            go.Scatter(
                x=[e.filtered_lon for e in filtered],
                y=[e.filtered_lat for e in filtered],
                mode="lines+markers",
                line=dict(color="yellow", width=2, dash="dot"),
                marker=dict(size=3, color="yellow"),
                name="ESKF filtered",
            ),
        )
    return traces


def quality_pie(estimates: List[EstimateData]) -> Optional[go.Pie]:
    if not estimates:
        return None
    good = sum(1 for e in estimates if e.quality == "good")
    marginal = sum(1 for e in estimates if e.quality == "marginal")
    poor = sum(1 for e in estimates if e.quality == "poor")
    counts = {}
    if good:
        counts["Good"] = good
    if marginal:
        counts["Marginal"] = marginal
    if poor:
        counts["Poor"] = poor
    if not counts:
        return None
    return go.Pie(
        labels=list(counts.keys()),
        values=list(counts.values()),
        marker=dict(colors=["lime", "orange", "red"]),
        textinfo="label+percent",
        name="Качество",
    )

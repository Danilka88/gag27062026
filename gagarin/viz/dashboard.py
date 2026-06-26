from typing import Optional, List
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from gagarin.dem_loader import DEMLoader
from gagarin.estimator import NavigationEstimate
from gagarin.viz.utils import TEMPLATE, get_grid_or_fallback


def navigation_dashboard(
    dem: DEMLoader,
    trajectory_lats: np.ndarray,
    trajectory_lons: np.ndarray,
    estimates: List[NavigationEstimate],
    azimuths: np.ndarray,
    speeds: np.ndarray,
    corr_matrix: np.ndarray,
    observed_profile: Optional[np.ndarray] = None,
    reference_profile: Optional[np.ndarray] = None,
    dem_name: str = "DEM",
) -> go.Figure:
    fig = make_subplots(
        rows=2,
        cols=2,
        specs=[
            [{"type": "scene"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}],
        ],
        subplot_titles=(
            "Рельеф и траектория",
            "Карта корреляции (азимут × скорость)",
            "Профиль рельефа: измеренный vs эталон",
            "История оценок: корреляция и доверие",
        ),
        vertical_spacing=0.12,
        horizontal_spacing=0.1,
    )

    lons, lats, elevation = get_grid_or_fallback(dem)

    lon_grid, lat_grid = np.meshgrid(lons, lats)

    fig.add_trace(
        go.Surface(
            z=elevation,
            x=lon_grid if lon_grid.shape == elevation.shape else None,
            y=lat_grid if lat_grid.shape == elevation.shape else None,
            colorscale="Earth",
            name="Рельеф",
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
            name="Истинный путь",
        ),
        row=1,
        col=1,
    )

    if estimates:
        est_lons = [e.position_lon for e in estimates]
        est_lats = [e.position_lat for e in estimates]
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
                name="Оценка TERCOM",
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
            hovertemplate="Азимут: %{x:.1f}°<br>Скорость: %{y:.1f} м/с<br>Корреляция: %{z:.3f}<extra></extra>",
        ),
        row=1,
        col=2,
    )

    if observed_profile is not None and reference_profile is not None:
        fig.add_trace(
            go.Scatter(y=observed_profile, mode="lines", name="Измерено", line=dict(color="cyan")),
            row=2,
            col=1,
        )
        fig.add_trace(
            go.Scatter(y=reference_profile, mode="lines", name="Эталон", line=dict(color="orange", dash="dash")),
            row=2,
            col=1,
        )

    if estimates:
        est_idx = list(range(len(estimates)))
        est_corr = [e.correlation for e in estimates]
        fig.add_trace(
            go.Scatter(x=est_idx, y=est_corr, mode="lines+markers", name="Корреляция", line=dict(color="lime")),
            row=2,
            col=2,
        )
        est_conf = [e.confidence for e in estimates]
        fig.add_trace(
            go.Scatter(x=est_idx, y=est_conf, mode="lines+markers", name="Доверие", line=dict(color="orange", dash="dot")),
            row=2,
            col=2,
        )

    fig.update_layout(
        title=f"TERCOM Навигация — {dem_name}",
        height=900,
        template=TEMPLATE,
        showlegend=True,
    )

    fig.update_xaxes(title_text="Номер оценки", row=2, col=2)
    fig.update_yaxes(title_text="Значение", row=2, col=2)
    fig.update_xaxes(title_text="Отсчёт", row=2, col=1)
    fig.update_yaxes(title_text="Высота рельефа (м)", row=2, col=1)
    fig.update_xaxes(title_text="Азимут (°)", row=1, col=2)
    fig.update_yaxes(title_text="Скорость (м/с)", row=1, col=2)

    fig.update_scenes(
        aspectmode="data",
        xaxis_title="Долгота",
        yaxis_title="Широта",
        zaxis_title="Высота (м)",
        row=1,
        col=1,
    )

    return fig


def comparison_dashboard(
    dem_synthetic: DEMLoader,
    dem_dramatic: DEMLoader,
    traj_lats: np.ndarray,
    traj_lons: np.ndarray,
    estimates_syn: List[NavigationEstimate],
    estimates_dram: List[NavigationEstimate],
    corr_matrix_syn: np.ndarray,
    corr_matrix_dram: np.ndarray,
    obs_profile_syn: np.ndarray,
    ref_profile_syn: np.ndarray,
    obs_profile_dram: np.ndarray,
    ref_profile_dram: np.ndarray,
    azimuths: np.ndarray,
    speeds: np.ndarray,
) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=2,
        specs=[
            [{"type": "scene"}, {"type": "scene"}],
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}],
        ],
        subplot_titles=(
            "Synthetic DEM — ровный рельеф (σ=95 м)",
            "Dramatic DEM — горный рельеф (σ=687 м)",
            "Профили рельефа — Synthetic",
            "Профили рельефа — Dramatic",
            "Корреляция по времени — Synthetic (синий) vs Dramatic (красный)",
            "",
        ),
        vertical_spacing=0.1,
        horizontal_spacing=0.08,
    )

    for col_idx, (dem, name, color, estimates, obs_p, ref_p) in enumerate([
        (dem_synthetic, "Synthetic", "cyan", estimates_syn, obs_profile_syn, ref_profile_syn),
        (dem_dramatic, "Dramatic", "red", estimates_dram, obs_profile_dram, ref_profile_dram),
    ], start=1):
        lons, lats, elevation = get_grid_or_fallback(dem)
        lon_grid, lat_grid = np.meshgrid(lons, lats)

        fig.add_trace(
            go.Surface(
                z=elevation,
                x=lon_grid if lon_grid.shape == elevation.shape else None,
                y=lat_grid if lat_grid.shape == elevation.shape else None,
                colorscale="Earth",
                showscale=False,
                name=f"{name} рельеф",
            ),
            row=1, col=col_idx,
        )

        fig.add_trace(
            go.Scatter3d(
                x=traj_lons, y=traj_lats,
                z=dem.elevation_batch(np.array(traj_lats), np.array(traj_lons)),
                mode="lines+markers",
                line=dict(color="red", width=4),
                marker=dict(size=2, color="red"),
                name=f"{name} истинный путь",
            ),
            row=1, col=col_idx,
        )

        if estimates:
            elons = [e.position_lon for e in estimates]
            elats = [e.position_lat for e in estimates]
            try:
                ezs = dem.elevation_batch(np.array(elats), np.array(elons))
            except (IndexError, ValueError):
                ezs = [0] * len(elats)
            fig.add_trace(
                go.Scatter3d(
                    x=elons, y=elats, z=ezs,
                    mode="lines+markers",
                    line=dict(color="lime", width=2, dash="dash"),
                    marker=dict(size=3, color="lime"),
                    name=f"{name} оценка",
                ),
                row=1, col=col_idx,
            )

        fig.update_scenes(
            aspectmode="data",
            xaxis_title="Долгота",
            yaxis_title="Широта",
            zaxis_title="Высота (м)",
            row=1, col=col_idx,
        )

        if obs_p is not None and ref_p is not None:
            fig.add_trace(
                go.Scatter(y=obs_p, mode="lines", name=f"{name} измерено", line=dict(color="cyan")),
                row=2, col=col_idx,
            )
            fig.add_trace(
                go.Scatter(y=ref_p, mode="lines", name=f"{name} эталон", line=dict(color="orange", dash="dash")),
                row=2, col=col_idx,
            )

        fig.update_xaxes(title_text="Отсчёт", row=2, col=col_idx)
        fig.update_yaxes(title_text="Высота (м)", row=2, col=col_idx)

    est_idx_syn = list(range(len(estimates_syn))) if estimates_syn else []
    est_idx_dram = list(range(len(estimates_dram))) if estimates_dram else []

    if estimates_syn:
        fig.add_trace(
            go.Scatter(x=est_idx_syn, y=[e.correlation for e in estimates_syn],
                       mode="lines", name="Synthetic корреляция",
                       line=dict(color="cyan", width=2)),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(x=est_idx_syn, y=[e.confidence for e in estimates_syn],
                       mode="lines", name="Synthetic доверие",
                       line=dict(color="blue", width=1, dash="dot")),
            row=3, col=1,
        )
    if estimates_dram:
        fig.add_trace(
            go.Scatter(x=est_idx_dram, y=[e.correlation for e in estimates_dram],
                       mode="lines", name="Dramatic корреляция",
                       line=dict(color="red", width=2)),
            row=3, col=1,
        )
        fig.add_trace(
            go.Scatter(x=est_idx_dram, y=[e.confidence for e in estimates_dram],
                       mode="lines", name="Dramatic доверие",
                       line=dict(color="darkred", width=1, dash="dot")),
            row=3, col=1,
        )

    elev_syn = dem_synthetic._interp.get_raw_data()
    elev_dram = dem_dramatic._interp.get_raw_data()
    syn_std = float(np.std(elev_syn))
    dram_std = float(np.std(elev_dram))

    metrics_text = (
        f"<b>Synthetic DEM</b><br>"
        f"Перепад высот: {elev_syn.min():.0f}–{elev_syn.max():.0f} м, "
        f"σ = {syn_std:.0f} м<br>"
        f"Оценок: {len(estimates_syn)}, "
        f"первая корреляция: {estimates_syn[0].correlation:.3f}" if estimates_syn else ""
    )
    metrics_text += "<br><br>"
    metrics_text += (
        f"<b>Dramatic DEM</b><br>"
        f"Перепад высот: {elev_dram.min():.0f}–{elev_dram.max():.0f} м, "
        f"σ = {dram_std:.0f} м<br>"
        f"Оценок: {len(estimates_dram)}, "
        f"первая корреляция: {estimates_dram[0].correlation:.3f}" if estimates_dram else ""
    )

    fig.add_annotation(
        x=0.5, y=0.02, xref="paper", yref="paper",
        text=metrics_text,
        showarrow=False,
        font=dict(size=12),
        align="center",
        bgcolor="rgba(0,0,0,0.7)",
        bordercolor="gray",
        borderwidth=1,
    )

    fig.update_layout(
        title="TERCOM Навигация: сравнение Synthetic (ровный) vs Dramatic (горный) DEM",
        height=1200,
        template=TEMPLATE,
        showlegend=True,
        legend=dict(x=1.02, y=1, xanchor="left"),
    )

    fig.update_xaxes(title_text="Номер оценки", row=3, col=1)
    fig.update_yaxes(title_text="Значение", row=3, col=1)
    fig.add_annotation(
        x=0.25, y=0.38, xref="paper", yref="paper",
        text="Synthetic — плоский рельеф → низкое доверие, частые сбои",
        showarrow=False, font=dict(size=11, color="cyan"),
        bgcolor="rgba(0,0,0,0.5)",
    )
    fig.add_annotation(
        x=0.75, y=0.38, xref="paper", yref="paper",
        text="Dramatic — горный рельеф → выше корреляция, стабильнее",
        showarrow=False, font=dict(size=11, color="red"),
        bgcolor="rgba(0,0,0,0.5)",
    )
    fig.add_annotation(
        x=0.5, y=0.22, xref="paper", yref="paper",
        text="Чем выше σ рельефа — тем профиль уникальнее и корреляция точнее",
        showarrow=False, font=dict(size=13, color="white"),
        bgcolor="rgba(0,0,0,0.6)",
    )

    return fig

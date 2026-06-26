import plotly.graph_objects as go
from plotly.subplots import make_subplots

from gagarin.viz.utils import TEMPLATE
from gagarin.viz.data_model import DashboardData
from gagarin.viz.components import (
    terrain_traces,
    correlation_heatmap_trace,
    profile_traces,
    timeline_traces,
    error_traces,
)


def navigation_dashboard(data: DashboardData) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=2,
        specs=[
            [{"type": "scene", "colspan": 2}, None],
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}],
        ],
        subplot_titles=(
            "Рельеф и траектория",
            "Профиль рельефа: измеренный vs эталон",
            "История оценок: корреляция и доверие",
            "Ошибки: азимут и скорость",
            "Карта корреляции (азимут × скорость)",
        ),
        vertical_spacing=0.12,
        horizontal_spacing=0.1,
    )

    for trace in terrain_traces(data.terrain, data.trajectory, data.estimates):
        fig.add_trace(trace, row=1, col=1)

    for trace in profile_traces(data.profile):
        fig.add_trace(trace, row=2, col=1)

    for trace in timeline_traces(data.estimates):
        fig.add_trace(trace, row=2, col=2)

    corr_best_az = data.correlation.best_azimuth()
    corr_best_sp = data.correlation.best_speed()
    for trace in correlation_heatmap_trace(data.correlation, corr_best_az, corr_best_sp):
        fig.add_trace(trace, row=3, col=2)

    has_az_err = len(data.errors.azimuth_errors) > 0
    has_sp_err = len(data.errors.speed_errors) > 0
    if has_az_err or has_sp_err:
        for trace in error_traces(data.errors):
            fig.add_trace(trace, row=3, col=1)

    fig.update_scenes(
        aspectmode="data",
        xaxis_title="Долгота",
        yaxis_title="Широта",
        zaxis_title="Высота (м)",
        row=1, col=1,
    )

    fig.update_xaxes(title_text="Отсчёт", row=2, col=1)
    fig.update_yaxes(title_text="Высота рельефа (м)", row=2, col=1)
    fig.update_xaxes(title_text="Номер оценки", row=2, col=2)
    fig.update_yaxes(title_text="Значение", row=2, col=2)
    fig.update_xaxes(title_text="Номер оценки", row=3, col=1)
    fig.update_yaxes(title_text="Ошибка азимута (°)", row=3, col=1)
    if has_sp_err:
        fig.update_yaxes(
            title_text="Ошибка скорости (м/с)",
            overlaying="y",
            side="right",
            row=3, col=1,
        )
    fig.update_xaxes(title_text="Азимут (°)", row=3, col=2)
    fig.update_yaxes(title_text="Скорость (м/с)", row=3, col=2)

    quality_legend_items = []
    if data.estimates:
        good = sum(1 for e in data.estimates if e.quality == "good")
        marginal = sum(1 for e in data.estimates if e.quality == "marginal")
        poor = sum(1 for e in data.estimates if e.quality == "poor")
        total = len(data.estimates)
        quality_legend = (
            f"<b>Качество оценок:</b> good={good} ({100*good/total:.0f}%), "
            f"marginal={marginal} ({100*marginal/total:.0f}%), "
            f"poor={poor} ({100*poor/total:.0f}%)"
        )
        quality_legend_items.append(quality_legend)

    terrain_range = data.terrain.elevation_range
    summary_lines = [
        f"<b>{data.dem_name}</b> | "
        f"Рельеф: {terrain_range[0]:.0f}–{terrain_range[1]:.0f} м (σ={data.terrain.elevation_std:.0f} м) | "
        f"Оценок: {len(data.estimates)}",
    ]
    if has_az_err:
        summary_lines.append(
            f"Средняя |ошибка азимута|: {data.errors.mean_azimuth_error:.1f}° | "
            f"скорости: {data.errors.mean_speed_error:.1f} м/с"
        )
    if len(data.errors.position_errors_km) > 0:
        summary_lines.append(
            f"Финальный дрейф: {data.errors.final_drift_km:.2f} км | "
            f"Средний: {data.errors.mean_position_error_km:.2f} км"
        )
    summary_lines.extend(quality_legend_items)

    fig.add_annotation(
        x=0.5, y=1.0, xref="paper", yref="paper",
        text="<br>".join(summary_lines),
        showarrow=False,
        font=dict(size=11),
        align="center",
        bgcolor="rgba(0,0,0,0.7)",
        bordercolor="gray",
        borderwidth=1,
        yshift=10,
    )

    updatemenus = [
        dict(
            type="buttons",
            direction="right",
            x=0.5,
            y=1.08,
            xanchor="center",
            buttons=[
                dict(
                    label="Все оценки",
                    method="update",
                    args=[{"visible": [True] * len(fig.data)}],
                ),
                dict(
                    label="Только ESKF",
                    method="update",
                    args=[
                        {
                            "visible": [
                                not isinstance(t, go.Scatter3d) or "ESKF" not in (t.name or "")
                                for t in fig.data
                            ]
                        }
                    ],
                ),
            ],
        ),
    ]

    fig.update_layout(
        title=f"TERCOM Навигация — {data.dem_name}",
        height=1100,
        template=TEMPLATE,
        showlegend=True,
        legend=dict(x=1.02, y=1, xanchor="left"),
        updatemenus=updatemenus,
    )

    return fig


def comparison_dashboard(data_syn: DashboardData, data_dram: DashboardData) -> go.Figure:
    fig = make_subplots(
        rows=3,
        cols=2,
        specs=[
            [{"type": "scene"}, {"type": "scene"}],
            [{"type": "xy"}, {"type": "xy"}],
            [{"type": "xy"}, {"type": "xy"}],
        ],
        subplot_titles=(
            f"Synthetic — {data_syn.dem_name}",
            f"Dramatic — {data_dram.dem_name}",
            "Профили рельефа — Synthetic",
            "Профили рельефа — Dramatic",
            "Ошибки: Synthetic vs Dramatic",
            "Корреляция по времени: Synthetic vs Dramatic",
        ),
        vertical_spacing=0.12,
        horizontal_spacing=0.08,
    )

    for trace in terrain_traces(data_syn.terrain, data_syn.trajectory, data_syn.estimates):
        fig.add_trace(trace, row=1, col=1)
    for trace in terrain_traces(data_dram.terrain, data_dram.trajectory, data_dram.estimates):
        fig.add_trace(trace, row=1, col=2)

    for trace in profile_traces(data_syn.profile):
        fig.add_trace(trace, row=2, col=1)
    for trace in profile_traces(data_dram.profile):
        fig.add_trace(trace, row=2, col=2)

    for scene_row, scene_col in [(1, 1), (1, 2)]:
        fig.update_scenes(
            aspectmode="data",
            xaxis_title="Долгота",
            yaxis_title="Широта",
            zaxis_title="Высота (м)",
            row=scene_row, col=scene_col,
        )

    fig.update_xaxes(title_text="Отсчёт", row=2, col=1)
    fig.update_yaxes(title_text="Высота (м)", row=2, col=1)
    fig.update_xaxes(title_text="Отсчёт", row=2, col=2)
    fig.update_yaxes(title_text="Высота (м)", row=2, col=2)

    def _add_corr_overlay(estimates, name, color, row, col):
        if not estimates:
            return
        idx = [e.idx for e in estimates]
        fig.add_trace(
            go.Scatter(
                x=idx, y=[e.correlation for e in estimates],
                mode="lines", name=f"{name} корреляция",
                line=dict(color=color, width=2),
            ),
            row=row, col=col,
        )
        fig.add_trace(
            go.Scatter(
                x=idx, y=[e.confidence for e in estimates],
                mode="lines", name=f"{name} доверие",
                line=dict(color=color, width=1, dash="dot"),
            ),
            row=row, col=col,
        )
    _add_corr_overlay(data_syn.estimates, "Synthetic", "cyan", 3, 2)
    _add_corr_overlay(data_dram.estimates, "Dramatic", "red", 3, 2)

    fig.update_xaxes(title_text="Номер оценки", row=3, col=2)
    fig.update_yaxes(title_text="Значение", row=3, col=2)

    def _add_error_overlay(data: DashboardData, name: str, color: str, row: int, col: int):
        if len(data.errors.azimuth_errors) == 0:
            return
        idx = list(range(len(data.errors.azimuth_errors)))
        fig.add_trace(
            go.Scatter(
                x=idx, y=data.errors.azimuth_errors,
                mode="lines", name=f"{name} ошибка азимута",
                line=dict(color=color, width=2),
            ),
            row=row, col=col,
        )
    _add_error_overlay(data_syn, "Synthetic", "cyan", 3, 1)
    _add_error_overlay(data_dram, "Dramatic", "red", 3, 1)

    fig.update_xaxes(title_text="Номер оценки", row=3, col=1)
    fig.update_yaxes(title_text="Ошибка азимута (°)", row=3, col=1)

    metrics_lines = []
    for name, data, color in [("Synthetic", data_syn, "cyan"), ("Dramatic", data_dram, "red")]:
        mae_az = data.errors.mean_azimuth_error
        mae_sp = data.errors.mean_speed_error
        drift = data.errors.final_drift_km
        metrics_lines.append(
            f"<span style='color:{color}'><b>{name}</b></span> | "
            f"σ={data.terrain.elevation_std:.0f} м | "
            f"|az|={mae_az:.1f}° | |sp|={mae_sp:.1f} м/с | "
            f"дрейф={drift:.2f} км | оценок={len(data.estimates)}"
        )

    fig.add_annotation(
        x=0.5, y=1.0, xref="paper", yref="paper",
        text="<br>".join(metrics_lines),
        showarrow=False,
        font=dict(size=12),
        align="center",
        bgcolor="rgba(0,0,0,0.7)",
        bordercolor="gray",
        borderwidth=1,
        yshift=10,
    )

    fig.add_annotation(
        x=0.5, y=0.38, xref="paper", yref="paper",
        text="Synthetic — ровный рельеф → низкая корреляция, большой дрейф.<br>"
             "Dramatic — горный рельеф → выше корреляция, меньше ошибка.",
        showarrow=False,
        font=dict(size=11),
        align="center",
        bgcolor="rgba(0,0,0,0.5)",
    )

    fig.update_layout(
        title="TERCOM: сравнение Synthetic (ровный) vs Dramatic (горный) DEM",
        height=1200,
        template=TEMPLATE,
        showlegend=True,
        legend=dict(x=1.02, y=1, xanchor="left"),
    )

    return fig

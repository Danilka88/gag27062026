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
        aspectmode="manual",
        aspectratio=dict(x=1, y=1, z=0.4),
        camera=dict(eye=dict(x=1.5, y=1.5, z=0.8)),
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


def unified_dashboard(syn: DashboardData, dram: DashboardData) -> go.Figure:
    fig = make_subplots(
        rows=5, cols=1,
        specs=[
            [{"type": "scene"}],
            [{"type": "xy"}],
            [{"type": "xy"}],
            [{"type": "xy"}],
            [{"type": "xy"}],
        ],
        subplot_titles=(
            "Рельеф и траектория<br>"
            "<sup style='font-size:10px;color:gray'>"
            "Красный — истинный трек; Зелёный — TERCOM; Жёлтый — ESKF</sup>",
            "Профиль рельефа<br>"
            "<sup style='font-size:10px;color:gray'>"
            "Голубой — измеренный радаром; Оранжевый — эталон из DEM</sup>",
            "Корреляция и доверие<br>"
            "<sup style='font-size:10px;color:gray'>"
            "Зелёный — корреляция (NCC); Оранжевый — доверие</sup>",
            "Ошибки азимута и скорости<br>"
            "<sup style='font-size:10px;color:gray'>"
            "Розовый — азимут (°); Голубой — скорость (м/с)</sup>",
            "Карта корреляции<br>"
            "<sup style='font-size:10px;color:gray'>"
            "NCC для азимут×скорость; ☆ — лучшее совпадение</sup>",
        ),
        vertical_spacing=0.08,
    )

    idx_groups = {k: [] for k in (
        'syn_terrain', 'dram_terrain',
        'syn_profile', 'dram_profile',
        'syn_timeline', 'dram_timeline',
        'syn_error', 'dram_error',
        'syn_heatmap', 'dram_heatmap',
    )}

    def _add(prefix: str, traces: list, group: str, **kwargs):
        for t in traces:
            if t.name and prefix not in t.name:
                t.name = f"{prefix} {t.name}"
            fig.add_trace(t, **kwargs)
            idx_groups[group].append(len(fig.data) - 1)

    _add("Synthetic", terrain_traces(syn.terrain, syn.trajectory, syn.estimates), 'syn_terrain', row=1, col=1)
    _add("Dramatic", terrain_traces(dram.terrain, dram.trajectory, dram.estimates), 'dram_terrain', row=1, col=1)

    _add("Synthetic", profile_traces(syn.profile), 'syn_profile', row=2, col=1)
    _add("Dramatic", profile_traces(dram.profile), 'dram_profile', row=2, col=1)

    _add("Synthetic", timeline_traces(syn.estimates), 'syn_timeline', row=3, col=1)
    _add("Dramatic", timeline_traces(dram.estimates), 'dram_timeline', row=3, col=1)

    _add("Synthetic", error_traces(syn.errors), 'syn_error', row=4, col=1)
    _add("Dramatic", error_traces(dram.errors), 'dram_error', row=4, col=1)

    corr_best_az_syn = syn.correlation.best_azimuth()
    corr_best_sp_syn = syn.correlation.best_speed()
    _add("Synthetic", correlation_heatmap_trace(syn.correlation, corr_best_az_syn, corr_best_sp_syn), 'syn_heatmap', row=5, col=1)

    corr_best_az_dram = dram.correlation.best_azimuth()
    corr_best_sp_dram = dram.correlation.best_speed()
    _add("Dramatic", correlation_heatmap_trace(dram.correlation, corr_best_az_dram, corr_best_sp_dram), 'dram_heatmap', row=5, col=1)

    fig.update_scenes(
        aspectmode="manual",
        aspectratio=dict(x=1, y=1, z=0.4),
        camera=dict(eye=dict(x=1.5, y=1.5, z=0.8)),
        xaxis_title="Долгота",
        yaxis_title="Широта",
        zaxis_title="Высота (м)",
        row=1, col=1,
    )

    fig.update_xaxes(title_text="Отсчёт", row=2, col=1)
    fig.update_yaxes(title_text="Высота (м)", row=2, col=1)
    fig.update_xaxes(title_text="Номер оценки", row=3, col=1)
    fig.update_yaxes(title_text="Значение", row=3, col=1)
    fig.update_xaxes(title_text="Номер оценки", row=4, col=1)
    fig.update_yaxes(title_text="Ошибка азимута (°)", row=4, col=1)
    fig.update_yaxes(
        title_text="Ошибка скорости (м/с)",
        overlaying="y",
        side="right",
        row=4, col=1,
    )
    fig.update_xaxes(title_text="Азимут (°)", row=5, col=1)
    fig.update_yaxes(title_text="Скорость (м/с)", row=5, col=1)

    n = len(fig.data)

    def _vis(*groups):
        v = [False] * n
        for g in groups:
            for i in idx_groups[g]:
                v[i] = True
        return v

    syn_vis = _vis('syn_terrain', 'syn_profile', 'syn_timeline', 'syn_error', 'syn_heatmap')
    dram_vis = _vis('dram_terrain', 'dram_profile', 'dram_timeline', 'dram_error', 'dram_heatmap')

    updatemenus = [
        dict(
            type="buttons",
            direction="right",
            x=0.5, y=1.08, xanchor="center",
            buttons=[
                dict(label="Synthetic", method="update",
                     args=[{"visible": syn_vis},
                           {"title": "TERCOM Навигация — Synthetic DEM"}]),
                dict(label="Dramatic", method="update",
                     args=[{"visible": dram_vis},
                           {"title": "TERCOM Навигация — Dramatic DEM"}]),
            ],
        ),
    ]

    def _summary_line(name: str, d: DashboardData) -> str:
        tr = d.terrain
        total = len(d.estimates)
        good = sum(1 for e in d.estimates if e.quality == "good")
        q_str = f"good={good} ({100*good/total:.0f}%)" if total else "—"
        return (
            f"<b>{name}</b> | "
            f"Рельеф: {tr.elevation_range[0]:.0f}–{tr.elevation_range[1]:.0f} м "
            f"(σ={tr.elevation_std:.0f} м) | "
            f"Оценок: {total} | "
            f"|az|: {d.errors.mean_azimuth_error:.1f}° | "
            f"|sp|: {d.errors.mean_speed_error:.1f} м/с | "
            f"Дрейф: {d.errors.final_drift_km:.2f} км | "
            f"{q_str}"
        )

    fig.add_annotation(
        x=0.5, y=0.02, xref="paper", yref="paper",
        text="<br>".join([
            _summary_line("Synthetic", syn),
            _summary_line("Dramatic", dram),
        ]),
        showarrow=False,
        font=dict(size=10),
        align="center",
        bgcolor="rgba(0,0,0,0.7)",
        bordercolor="gray",
        borderwidth=1,
    )

    scene_caption = (
        "Это 3D-карта местности, по которой летит дрон. "
        "<b>Красная линия</b> — реальный путь (по GPS). "
        "<b>Зелёная</b> — где алгоритм думает, что дрон находится. "
        "<b>Жёлтая</b> — уточнённая оценка после фильтра. "
        "Если линии совпадают — навигация точная."
    )
    fig.add_annotation(
        xref="paper", yref="paper",
        x=0.5, y=0.74,
        text=scene_caption,
        showarrow=False,
        font=dict(size=10, color="gray"),
        align="center",
    )

    xy_captions = [
        (2, "Срез высот под дроном за один проход. "
            "<b>Голубая линия</b> — что измерил радар. "
            "<b>Оранжевая</b> — что ожидалось по карте высот (DEM). "
            "Чем ближе линии друг к другу — тем точнее алгоритм определил место."),
        (3, "Как менялась уверенность алгоритма со временем. "
            "<b>Зелёная линия</b> — корреляция (1 = профили идеально совпадают). "
            "<b>Оранжевая</b> — доверие к оценке. "
            "Если обе линии высоко — ответу можно верить."),
        (4, "Насколько алгоритм ошибается в своих оценках. "
            "<b>Розовая линия</b> — ошибка по направлению (градусы от истины). "
            "<b>Голубая</b> — ошибка по скорости. "
            "Чем ближе к нулю — тем точнее навигация."),
        (5, "Результат сканирования — алгоритм перебирает все варианты "
            "направления и скорости. <b>Яркие участки</b> — хорошие совпадения. "
            "<b>Звезда (★)</b> — лучшее совпадение. "
            "Чем ярче и компактнее пятно — тем увереннее ответ."),
    ]
    for row, text in xy_captions:
        fig.add_annotation(
            xref="paper", yref="paper",
            x=0.5, y=-0.35,
            text=text,
            showarrow=False,
            font=dict(size=10, color="gray"),
            align="center",
            row=row, col=1,
        )

    fig.update_layout(
        title="TERCOM Навигация — Synthetic vs Dramatic",
        height=2800,
        template=TEMPLATE,
        showlegend=True,
        legend=dict(x=1.02, y=0.98, xanchor="left"),
        updatemenus=updatemenus,
    )

    return fig

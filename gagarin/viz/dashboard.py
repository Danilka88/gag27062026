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


def _add_with_prefix(fig: go.Figure, prefix: str, traces: list, indices: list):
    for t in traces:
        if t.name and not t.name.startswith(prefix):
            t.name = f"{prefix} {t.name}"
        fig.add_trace(t)
        indices.append(len(fig.data) - 1)


def _vis_list(n: int, *indices_groups) -> list:
    v = [False] * n
    for grp in indices_groups:
        for i in grp:
            v[i] = True
    return v


def _chart(fig: go.Figure, chart_id: str, title: str, caption: str,
           syn_indices: list, dram_indices: list) -> dict:
    n = len(fig.data)
    return {
        "id": chart_id,
        "title": title,
        "caption": caption,
        "fig": fig,
        "syn_vis": _vis_list(n, syn_indices),
        "dram_vis": _vis_list(n, dram_indices),
    }


def unified_dashboard(syn: DashboardData, dram: DashboardData) -> list:
    charts = []

    fig_terrain = go.Figure()
    syn_idx = []
    dram_idx = []
    _add_with_prefix(fig_terrain, "Synthetic", terrain_traces(syn.terrain, syn.trajectory, syn.estimates), syn_idx)
    _add_with_prefix(fig_terrain, "Dramatic", terrain_traces(dram.terrain, dram.trajectory, dram.estimates), dram_idx)
    fig_terrain.update_layout(
        scene=dict(
            aspectmode="manual", aspectratio=dict(x=1, y=1, z=0.4),
            camera=dict(eye=dict(x=1.5, y=1.5, z=0.8)),
            xaxis_title="Долгота", yaxis_title="Широта", zaxis_title="Высота (м)",
        ),
        template=TEMPLATE, height=500, showlegend=True,
        legend=dict(x=1.02, y=1, xanchor="left"),
        margin=dict(l=40, r=40, t=10, b=10),
    )
    charts.append(_chart(fig_terrain, "terrain",
        "Рельеф и траектория",
        "Показывает карту местности и путь дрона. <b>Красная линия</b> — где дрон "
        "был на самом деле (GPS). <b>Зелёная</b> — где его определил TERCOM. "
        "<b>Жёлтая</b> — уточнённое положение (ESKF). Если линии сливаются — "
        "навигация точная. Разрывы означают, что алгоритм ошибся."
        "<div class='ex'>"
        "✅ Линии красная и зелёная почти совпадают — точность <b>отличная</b>, ошибка <1 км.<br>"
        "⚠️ Расстояние между линиями 2–5 км — точность <b>средняя</b>, стоит проверить настройки.<br>"
        "❌ Зелёная линия уходит в сторону — алгоритм <b>потерял</b> положение, нужна перезагрузка."
        "</div>",
        syn_idx, dram_idx))

    fig_profile = go.Figure()
    syn_idx = []
    dram_idx = []
    _add_with_prefix(fig_profile, "Synthetic", profile_traces(syn.profile), syn_idx)
    _add_with_prefix(fig_profile, "Dramatic", profile_traces(dram.profile), dram_idx)
    fig_profile.update_layout(
        template=TEMPLATE, height=300, showlegend=True,
        margin=dict(l=50, r=20, t=10, b=40),
        xaxis_title="Отсчёт", yaxis_title="Высота (м)",
    )
    charts.append(_chart(fig_profile, "profile",
        "Профиль рельефа",
        "Сравнивает то, что дрон «увидел» радаром (<b>голубой</b>), с тем, что "
        "ожидается по карте (<b>оранжевый</b>). Чем ближе линии друг к другу — "
        "тем правильнее TERCOM определил положение. Если линии сильно расходятся — "
        "дрон, скорее всего, не там, где мы думаем. Этот график — главный "
        "показатель качества одной оценки."
        "<div class='ex'>"
        "✅ Линии идут рядом, высоты совпадают с точностью <b>±20 м</b> — положение найдено <b>верно</b>.<br>"
        "⚠️ Расхождение <b>50–100 м</b> по высоте — вероятна ошибка <b>200–500 м</b> по координатам.<br>"
        "❌ Линии расходятся более чем на <b>200 м</b> — дрон <b>не там</b>, оценку нельзя использовать."
        "</div>",
        syn_idx, dram_idx))

    fig_timeline = go.Figure()
    syn_idx = []
    dram_idx = []
    _add_with_prefix(fig_timeline, "Synthetic", timeline_traces(syn.estimates), syn_idx)
    _add_with_prefix(fig_timeline, "Dramatic", timeline_traces(dram.estimates), dram_idx)
    fig_timeline.update_layout(
        template=TEMPLATE, height=300, showlegend=True,
        margin=dict(l=50, r=20, t=10, b=40),
        xaxis_title="Номер оценки", yaxis_title="Значение",
    )
    charts.append(_chart(fig_timeline, "timeline",
        "Корреляция и доверие",
        "Показывает, как уверенность алгоритма менялась со временем. "
        "<b>Зелёная линия</b> — корреляция (насколько профили совпали, "
        "1 = идеально). <b>Оранжевая</b> — доверие (0–1). Если обе линии "
        "высокие — ответу можно верить. Падения означают, что в этом месте "
        "рельеф плоский или однообразный, и TERCOM временно «потерялся»."
        "<div class='ex'>"
        "✅ Корреляция <b>>0.95</b>, доверие <b>>0.15</b> — оценка <b>надёжная</b>, можно полагаться.<br>"
        "⚠️ Корреляция <b>0.8–0.95</b>, доверие <b>0.08–0.15</b> — <b>средняя</b> уверенность, "
        "лучше перепроверить.<br>"
        "❌ Корреляция <b><0.8</b> или доверие <b><0.08</b> — оценка <b>ненадёжная</b>, "
        "игнорировать или ждать следующей."
        "</div>",
        syn_idx, dram_idx))

    fig_error = go.Figure()
    syn_idx = []
    dram_idx = []
    _add_with_prefix(fig_error, "Synthetic", error_traces(syn.errors), syn_idx)
    _add_with_prefix(fig_error, "Dramatic", error_traces(dram.errors), dram_idx)
    has_sp = any("скорости" in (fig_error.data[i].name or "") for i in range(len(fig_error.data)))
    fig_error.update_layout(
        template=TEMPLATE, height=300, showlegend=True,
        margin=dict(l=50, r=20, t=10, b=40),
        xaxis_title="Номер оценки", yaxis_title="Ошибка азимута (°)",
    )
    if has_sp:
        fig_error.update_layout(
            yaxis2=dict(title="Ошибка скорости (м/с)", overlaying="y", side="right"),
        )
    charts.append(_chart(fig_error, "error",
        "Ошибки азимута и скорости",
        "Показывает, насколько TERCOM ошибся в направлении и скорости. "
        "<b>Розовая линия</b> — ошибка по курсу (°). <b>Голубая</b> — ошибка "
        "по скорости (м/с). Чем ближе к нулю — тем точнее оценка. Если линии "
        "прыгают — алгоритм нестабилен. Если держатся около нуля — всё "
        "хорошо. Большие выбросы — сбой в конкретной точке маршрута."
        "<div class='ex'>"
        "✅ Ошибка азимута <b><10°</b>, ошибка скорости <b><10 м/с</b> — навигация <b>точная</b>.<br>"
        "⚠️ Азимут <b>10–30°</b> или скорость <b>10–30 м/с</b> — заметное отклонение, "
        "но допустимо для сложного рельефа.<br>"
        "❌ Азимут <b>>30°</b> или скорость <b>>30 м/с</b> — <b>серьёзная ошибка</b>, "
        "алгоритм сбился с курса."
        "</div>",
        syn_idx, dram_idx))

    fig_heatmap = go.Figure()
    syn_idx = []
    dram_idx = []
    corr_best_az_syn = syn.correlation.best_azimuth()
    corr_best_sp_syn = syn.correlation.best_speed()
    _add_with_prefix(fig_heatmap, "Synthetic",
        correlation_heatmap_trace(syn.correlation, corr_best_az_syn, corr_best_sp_syn), syn_idx)
    corr_best_az_dram = dram.correlation.best_azimuth()
    corr_best_sp_dram = dram.correlation.best_speed()
    _add_with_prefix(fig_heatmap, "Dramatic",
        correlation_heatmap_trace(dram.correlation, corr_best_az_dram, corr_best_sp_dram), dram_idx)
    fig_heatmap.update_layout(
        template=TEMPLATE, height=300, showlegend=True,
        margin=dict(l=50, r=20, t=10, b=40),
        xaxis_title="Азимут (°)", yaxis_title="Скорость (м/с)",
    )
    charts.append(_chart(fig_heatmap, "heatmap",
        "Карта корреляции",
        "TERCOM перебирает все возможные направления и скорости, подбирая "
        "наилучшее совпадение. <b>Яркие (красные) участки</b> — хорошие "
        "совпадения, тёмные (синие) — плохие. <b>★</b> — лучшее совпадение, "
        "которое выбрал алгоритм. Если пятно яркое и компактное — ответ "
        "уверенный. Если всё размыто — рельеф неинформативный, и доверять "
        "оценке не стоит."
        "<div class='ex'>"
        "✅ Одно яркое красное пятно с корреляцией <b>>0.95</b> — положение <b>найдено однозначно</b>.<br>"
        "⚠️ Несколько красных пятен с корреляцией <b>0.5–0.9</b> — есть <b>неоднозначность</b>, "
        "требуется больше данных.<br>"
        "❌ Вся карта синяя, корреляция <b><0.5</b> — рельеф плоский, TERCOM <b>не может</b> "
        "определить положение."
        "</div>",
        syn_idx, dram_idx))

    return charts

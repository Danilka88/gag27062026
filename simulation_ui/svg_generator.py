import math
from typing import List, Optional
import numpy as np


DEM_COLORS = ["#006837", "#1a9850", "#66bd63", "#a6d96a", "#d9ef8b", "#fee08b", "#fdae61", "#f46d43", "#d73027", "#a50026"]
TURBO = ["#30123b", "#4464ad", "#3f94bf", "#39bda3", "#67d2a2", "#a8e0a4", "#d7e39c", "#f5d56a", "#f9b539", "#f08c25", "#e25c1d", "#cc3318", "#a80e0e"]
QUAL_COLORS = {"good": "#75b798", "marginal": "#ffda6a", "poor": "#ea868f"}
W = 500


def _val_color(val, vmin, vmax, palette):
    if vmax <= vmin:
        return palette[0]
    t = (val - vmin) / (vmax - vmin)
    t = max(0, min(0.999, t))
    idx = int(t * len(palette))
    return palette[idx]


def _tag(tag, close=False):
    return f"</{tag}>" if close else f"<{tag}>"


def _svg_wrap(content, h):
    return f'<svg viewBox="0 0 {W} {h}" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto"><rect width="{W}" height="{h}" fill="#212529"/>' + content + '</svg>'


def svg_dem(elevation_data: np.ndarray) -> str:
    data = elevation_data[::max(1, elevation_data.shape[0]//40), ::max(1, elevation_data.shape[1]//40)]
    h, w = data.shape
    cell_w = 440 / w
    cell_h = 200 / h
    vmin, vmax = float(np.min(data)), float(np.max(data))
    parts = []
    parts.append('<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">DEM — карта высот</text>')
    parts.append('<text x="16" y="120" fill="#adb5bd" font-size="10" text-anchor="middle" transform="rotate(-90,16,120)" font-family="monospace">lat</text>')
    parts.append('<text x="250" y="250" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">lon</text>')
    for r in range(h):
        for c in range(w):
            color = _val_color(data[r, c], vmin, vmax, DEM_COLORS)
            parts.append(f'<rect x="{30 + c*cell_w:.1f}" y="{20 + r*cell_h:.1f}" width="{cell_w:.2f}" height="{cell_h:.2f}" fill="{color}" stroke="none"/>')
    parts.append('<rect x="480" y="20" width="14" height="200" fill="none" stroke="#495057" stroke-width="1"/>')
    for i in range(10):
        c = _val_color(vmin + (vmax - vmin) * (1 - i/10), vmin, vmax, DEM_COLORS)
        parts.append(f'<rect x="480" y="{20 + i*20}" width="14" height="20" fill="{c}" stroke="none"/>')
    parts.append(f'<text x="494" y="18" fill="#dee2e6" font-size="8" text-anchor="middle" font-family="monospace">{vmax:.0f}m</text>')
    parts.append(f'<text x="494" y="238" fill="#dee2e6" font-size="8" text-anchor="middle" font-family="monospace">{vmin:.0f}m</text>')
    return _svg_wrap("".join(parts), 280)


def svg_nmea(readings_alt: List[float]) -> str:
    if not readings_alt:
        return ""
    vals = np.array(readings_alt)
    n = len(vals)
    pw, ph = 440, 200
    vmin, vmax = float(np.min(vals)) - 5, float(np.max(vals)) + 5
    if vmax <= vmin:
        vmax = vmin + 10
    pts = []
    for i in range(n):
        x = 30 + i * pw / max(n - 1, 1)
        y = 20 + ph - (vals[i] - vmin) / (vmax - vmin) * ph
        pts.append(f"{x:.1f},{y:.1f}")
    parts = []
    parts.append(f'<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">NMEA — радиовысотомер (первые {n} отсчётов)</text>')
    for i in range(5):
        y = 20 + ph * i / 4
        val = vmax - (vmax - vmin) * i / 4
        parts.append(f'<line x1="28" y1="{y:.1f}" x2="470" y2="{y:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="26" y="{y+3:.1f}" fill="#adb5bd" font-size="9" text-anchor="end" font-family="monospace">{val:.0f}</text>')
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')
    parts.append('<text x="250" y="250" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">отсчёт</text>')
    return _svg_wrap("".join(parts), 260)


def svg_buffer(window_size: int, fill: int) -> str:
    parts = []
    parts.append(f'<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Буфер — скользящее окно ({fill}/{window_size})</text>')
    parts.append(f'<text x="250" y="50" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">заполнено {fill / window_size * 100:.0f}%</text>')
    if window_size > 50:
        cell_w = 440 / 50
        seg = max(1, window_size // 44)
        for i in range(min(50, window_size)):
            start = i * seg
            end = min(start + seg, window_size)
            filled = sum(1 for _ in range(int(start), int(end)) if _ < fill)
            ratio = filled / (end - start) if end > start else 0
            if ratio >= 0.9:
                color = "#6ea8fe"
            elif ratio > 0:
                color = "#4d6b8a"
            else:
                color = "#2b3035"
            is_new = start <= fill < end
            if is_new:
                color = "#75b798"
            parts.append(f'<rect x="{30 + i*cell_w:.2f}" y="80" width="{cell_w:.2f}" height="80" fill="{color}" stroke="#495057" stroke-width="0.3" rx="1"/>')
        parts.append(f'<text x="250" y="180" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">показаны {50} групп (окно {window_size})</text>')
    else:
        cell_w = 440 / window_size if window_size else 1
        for i in range(window_size):
            if i < fill:
                color = "#6ea8fe"
            elif i == fill:
                color = "#75b798"
            else:
                color = "#2b3035"
            parts.append(f'<rect x="{30 + i*cell_w:.2f}" y="80" width="{cell_w:.2f}" height="80" fill="{color}" stroke="#495057" stroke-width="0.5"/>')
        parts.append('<rect x="28" y="78" width="444" height="84" fill="none" stroke="#6ea8fe" stroke-width="1"/>')
    parts.append('<text x="28" y="180" fill="#6ea8fe" font-size="9" font-family="monospace">заполнено</text>')
    parts.append('<rect x="90" y="173" width="12" height="8" fill="#75b798" rx="2"/>')
    parts.append('<text x="106" y="181" fill="#75b798" font-size="9" font-family="monospace">новый</text>')
    parts.append('<rect x="145" y="173" width="12" height="8" fill="#2b3035" stroke="#495057" stroke-width="0.5" rx="2"/>')
    parts.append('<text x="161" y="181" fill="#adb5bd" font-size="9" font-family="monospace">пусто</text>')
    return _svg_wrap("".join(parts), 200)


def svg_profile(observed: np.ndarray, reference: Optional[np.ndarray]) -> str:
    n = len(observed)
    if n < 2:
        return ""
    pw, ph = 440, 200
    ref_min = float(np.min(reference)) if reference is not None else float(np.min(observed))
    ref_max = float(np.max(reference)) if reference is not None else float(np.max(observed))
    vmin = min(float(np.min(observed)), ref_min) - 10
    vmax = max(float(np.max(observed)), ref_max) + 10
    if vmax <= vmin:
        vmax = vmin + 100
    parts = []
    parts.append('<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Профиль рельефа: измеренный vs эталонный</text>')
    for i in range(5):
        y = 20 + ph * i / 4
        val = vmax - (vmax - vmin) * i / 4
        parts.append(f'<line x1="28" y1="{y:.1f}" x2="470" y2="{y:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="26" y="{y+3:.1f}" fill="#adb5bd" font-size="9" text-anchor="end" font-family="monospace">{val:.0f}</text>')

    def _pts(vals):
        pts = []
        for i in range(len(vals)):
            x = 30 + i * pw / max(len(vals) - 1, 1)
            y = 20 + ph - (vals[i] - vmin) / (vmax - vmin) * ph
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts)

    parts.append(f'<polyline points="{_pts(observed)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')
    if reference is not None:
        parts.append(f'<polyline points="{_pts(reference)}" fill="none" stroke="#75b798" stroke-width="1.5" stroke-linejoin="round" stroke-dasharray="4,3"/>')
        parts.append('<text x="380" y="130" fill="#75b798" font-size="9" font-family="monospace">эталонный (DEM)</text>')
        if len(observed) > 1 and len(reference) > 1:
            mn = min(len(observed), len(reference))
            cc = float(np.corrcoef(observed[:mn], reference[:mn])[0, 1])
            parts.append(f'<text x="380" y="160" fill="#dee2e6" font-size="9" font-family="monospace">NCC: {cc:.3f}</text>')
    parts.append('<text x="380" y="145" fill="#6ea8fe" font-size="9" font-family="monospace">измеренный (радар)</text>')
    parts.append('<text x="250" y="250" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">отсчёт вдоль траектории</text>')
    return _svg_wrap("".join(parts), 260)


def svg_heatmap(matrix: np.ndarray, az_labels: List[str], sp_labels: List[str], title: str,
                highlight_az: Optional[float] = None, highlight_sp: Optional[float] = None,
                highlight_ri: Optional[int] = None, highlight_ci: Optional[int] = None,
                palette: Optional[List[str]] = None) -> str:
    nz, ns = matrix.shape
    cell_h = 180 / nz if nz else 1
    cell_w = 380 / ns if ns else 1
    vmin, vmax = float(np.min(matrix)), float(np.max(matrix))
    if vmax <= vmin:
        vmax = vmin + 1
    pal = palette or TURBO
    parts = []
    parts.append(f'<text x="250" y="14" fill="#dee2e6" font-size="11" text-anchor="middle" font-family="monospace">{title}</text>')
    parts.append('<text x="10" y="115" fill="#adb5bd" font-size="8" text-anchor="middle" transform="rotate(-90,10,115)" font-family="monospace">азимут (°)</text>')

    hl_ri, hl_ci = highlight_ri, highlight_ci
    for r in range(nz):
        for c in range(ns):
            color = _val_color(matrix[r, c], vmin, vmax, pal)
            parts.append(f'<rect x="{90 + c*cell_w:.2f}" y="{20 + r*cell_h:.2f}" width="{cell_w:.2f}" height="{cell_h:.2f}" fill="{color}"/>')

    if hl_ri is not None and hl_ci is not None and hl_ri >= 0 and hl_ci >= 0 and hl_ri < nz and hl_ci < ns:
        cx = 90 + hl_ci * cell_w + cell_w / 2
        cy = 20 + hl_ri * cell_h + cell_h / 2
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{max(cell_w, cell_h) * 0.7:.1f}" fill="none" stroke="#fff" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#fff"/>')
    ticks_n = min(nz, 10)
    for i in range(ticks_n):
        r = int(i * nz / ticks_n)
        if r < len(az_labels):
            parts.append(f'<text x="86" y="{22 + r*cell_h + cell_h/2:.1f}" fill="#adb5bd" font-size="7" text-anchor="end" font-family="monospace">{az_labels[r]}</text>')
    for i in range(min(ns, 6)):
        c = int(i * ns / 6)
        if c < len(sp_labels):
            parts.append(f'<text x="{90 + c*cell_w + cell_w/2:.1f}" y="212" fill="#adb5bd" font-size="7" text-anchor="middle" font-family="monospace">{sp_labels[c]}</text>')
    parts.append('<text x="280" y="232" fill="#adb5bd" font-size="8" text-anchor="middle" font-family="monospace">скорость (м/с)</text>')
    return _svg_wrap("".join(parts), 240)


def svg_ncc_bar(correlation: float) -> str:
    bar_w = 300
    bar_h = 30
    fill_w = max(bar_w * (correlation + 1) / 2, 0)
    if correlation > 0.8:
        color = "#75b798"
    elif correlation > 0.5:
        color = "#ffda6a"
    else:
        color = "#ea868f"
    parts = []
    parts.append('<text x="250" y="20" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">NCC — нормализованная кросс-корреляция</text>')
    parts.append(f'<rect x="100" y="60" width="{bar_w}" height="{bar_h}" fill="#2b3035" rx="4" stroke="#495057" stroke-width="1"/>')
    parts.append(f'<rect x="100" y="60" width="{fill_w:.1f}" height="{bar_h}" fill="{color}" rx="4"/>')
    parts.append(f'<text x="250" y="79" fill="#fff" font-size="14" text-anchor="middle" font-weight="bold" font-family="monospace">{correlation:.4f}</text>')
    parts.append('<text x="100" y="110" fill="#ea868f" font-size="9" font-family="monospace">-1.0</text>')
    parts.append('<text x="250" y="110" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">0.0</text>')
    parts.append('<text x="400" y="110" fill="#75b798" font-size="9" text-anchor="end" font-family="monospace">+1.0</text>')
    parts.append('<line x1="100" y1="106" x2="400" y2="106" stroke="#495057" stroke-width="1"/>')
    parts.append('<polygon points="400,100 400,112 408,106" fill="#adb5bd"/>')
    parts.append('<polygon points="100,100 100,112 92,106" fill="#adb5bd"/>')
    parts.append('<line x1="250" y1="106" x2="250" y2="112" stroke="#495057" stroke-width="1"/>')
    return _svg_wrap("".join(parts), 160)


def svg_lag(corr_full: np.ndarray, best_lag: int) -> str:
    n = len(corr_full)
    pw, ph = 440, 180
    vmin, vmax = float(np.min(corr_full)), float(np.max(corr_full))
    if vmax <= vmin:
        vmax = vmin + 1
    pts = []
    for i in range(n):
        x = 30 + i * pw / max(n - 1, 1)
        y = 15 + ph - (corr_full[i] - vmin) / (vmax - vmin) * ph
        pts.append(f"{x:.1f},{y:.1f}")
    lag_x = 30 + (best_lag + n // 2) * pw / max(n - 1, 1) if n > 1 else 30
    parts = []
    parts.append('<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Lag — кросс-корреляция профилей</text>')
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')
    parts.append(f'<line x1="{lag_x:.1f}" y1="15" x2="{lag_x:.1f}" y2="{15+ph}" stroke="#ea868f" stroke-width="1.5" stroke-dasharray="4,3"/>')
    parts.append(f'<text x="{lag_x:.1f}" y="212" fill="#ea868f" font-size="10" text-anchor="middle" font-family="monospace">lag = {best_lag} отсчётов</text>')
    return _svg_wrap("".join(parts), 240)


def svg_trajectory(true_lats: List[float], true_lons: List[float],
                   est_lats: List[float], est_lons: List[float],
                   filtered_lats: Optional[List[float]] = None,
                   filtered_lons: Optional[List[float]] = None) -> str:
    if not true_lats or not true_lons:
        return ""
    pw, ph = 440, 220
    margin = 0.0002
    all_lats = true_lats + est_lats + (filtered_lats or [])
    all_lons = true_lons + est_lons + (filtered_lons or [])
    lat_min, lat_max = min(all_lats) - margin, max(all_lats) + margin
    lon_min, lon_max = min(all_lons) - margin, max(all_lons) + margin
    if lat_max <= lat_min:
        lat_max = lat_min + 0.001
    if lon_max <= lon_min:
        lon_max = lon_min + 0.001

    def _pts(lats, lons):
        pts = []
        for lat, lon in zip(lats, lons):
            x = 30 + (lon - lon_min) / (lon_max - lon_min) * pw
            y = 15 + ph - (lat - lat_min) / (lat_max - lat_min) * ph
            pts.append(f"{x:.1f},{y:.1f}")
        return " ".join(pts)

    parts = []
    parts.append('<text x="250" y="14" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Траектория: истинная vs восстановленная</text>')
    parts.append(f'<polyline points="{_pts(true_lats, true_lons)}" fill="none" stroke="#75b798" stroke-width="2" stroke-linejoin="round" stroke-dasharray="4,3"/>')
    parts.append(f'<polyline points="{_pts(est_lats, est_lons)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')
    parts.append('<text x="350" y="30" fill="#75b798" font-size="9" font-family="monospace">истинная</text>')
    parts.append('<text x="350" y="42" fill="#6ea8fe" font-size="9" font-family="monospace">TERCOM</text>')
    if filtered_lats and filtered_lons:
        parts.append(f'<polyline points="{_pts(filtered_lats, filtered_lons)}" fill="none" stroke="#d2b8ff" stroke-width="1.5" stroke-linejoin="round"/>')
        parts.append('<text x="350" y="54" fill="#d2b8ff" font-size="9" font-family="monospace">ESKF</text>')
    if true_lats and true_lons:
        sx, sy = 30 + (true_lons[0] - lon_min) / (lon_max - lon_min) * pw, 15 + ph - (true_lats[0] - lat_min) / (lat_max - lat_min) * ph
        parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4" fill="#75b798" stroke="#212529" stroke-width="1.5"/>')
        parts.append(f'<text x="{sx:.1f}" y="{sy - 6:.1f}" fill="#75b798" font-size="8" text-anchor="middle" font-family="monospace">старт</text>')
        ex, ey = 30 + (true_lons[-1] - lon_min) / (lon_max - lon_min) * pw, 15 + ph - (true_lats[-1] - lat_min) / (lat_max - lat_min) * ph
        parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="#ea868f" stroke="#212529" stroke-width="1.5"/>')
        parts.append(f'<text x="{ex:.1f}" y="{ey - 6:.1f}" fill="#ea868f" font-size="8" text-anchor="middle" font-family="monospace">конец</text>')
    parts.append('<text x="250" y="252" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">долгота</text>')
    parts.append('<text x="12" y="130" fill="#adb5bd" font-size="9" text-anchor="middle" transform="rotate(-90,12,130)" font-family="monospace">широта</text>')
    return _svg_wrap("".join(parts), 260)


def svg_eskf_error(errors: List[float], title: str, color: str = "#6ea8fe") -> str:
    n = len(errors)
    if n < 2:
        return ""
    pw, ph = 440, 180
    vmin, vmax = float(min(errors)), float(max(errors))
    if vmax <= vmin:
        vmax = vmin + 1
    margin_v = (vmax - vmin) * 0.1
    vmin -= margin_v
    vmax += margin_v
    pts = []
    for i in range(n):
        x = 30 + i * pw / max(n - 1, 1)
        y = 15 + ph - (errors[i] - vmin) / (vmax - vmin) * ph
        pts.append(f"{x:.1f},{y:.1f}")
    parts = []
    parts.append(f'<text x="250" y="14" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">{title}</text>')
    for i in range(5):
        y = 15 + ph * i / 4
        val = vmax - (vmax - vmin) * i / 4
        parts.append(f'<text x="26" y="{y+3:.1f}" fill="#adb5bd" font-size="8" text-anchor="end" font-family="monospace">{val:.0f}</text>')
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>')
    parts.append('<text x="250" y="232" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">шаг</text>')
    parts.append('<text x="26" y="15" fill="#adb5bd" font-size="7" text-anchor="end" font-family="monospace">м</text>')
    return _svg_wrap("".join(parts), 240)


def svg_quality(quality: dict) -> str:
    q = quality.get("quality", "poor")
    conf = quality.get("confidence", 0.0)
    color = QUAL_COLORS.get(q, "#ea868f")
    labels = {"good": "Хорошо", "marginal": "Погранично", "poor": "Плохо"}
    label = labels.get(q, q)
    sharpness = quality.get("peak_sharpness", 0.0)
    disc_ratio = quality.get("discrimination_ratio", 0.0)
    parts = []
    parts.append('<text x="250" y="20" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Качество оценки</text>')
    parts.append('<circle cx="250" cy="100" r="55" fill="none" stroke="#2b3035" stroke-width="10"/>')
    arc = conf * 345
    parts.append(f'<circle cx="250" cy="100" r="55" fill="none" stroke="{color}" stroke-width="10" stroke-dasharray="{arc:.1f} 345" transform="rotate(-90,250,100)"/>')
    parts.append(f'<text x="250" y="95" fill="#dee2e6" font-size="22" text-anchor="middle" font-weight="bold" font-family="monospace">{conf:.0%}</text>')
    parts.append(f'<text x="250" y="115" fill="{color}" font-size="11" text-anchor="middle" font-family="monospace">{label}</text>')
    for pct in range(0, 101, 25):
        ang = (pct / 100) * 345 - 90
        rad = math.radians(ang)
        r_outer, r_inner = 68, 63
        x1 = 250 + r_inner * math.cos(rad)
        y1 = 100 + r_inner * math.sin(rad)
        x2 = 250 + r_outer * math.cos(rad)
        y2 = 100 + r_outer * math.sin(rad)
        parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#495057" stroke-width="1"/>')
        tx = 250 + 75 * math.cos(rad)
        ty = 100 + 75 * math.sin(rad)
        parts.append(f'<text x="{tx:.1f}" y="{ty + 3:.1f}" fill="#adb5bd" font-size="8" text-anchor="middle" font-family="monospace">{pct}%</text>')
    parts.append(f'<text x="100" y="175" fill="#adb5bd" font-size="9" font-family="monospace">peak_sharpness: {sharpness:.2f}</text>')
    parts.append(f'<text x="280" y="175" fill="#adb5bd" font-size="9" font-family="monospace">disc_ratio: {disc_ratio:.2f}</text>')
    return _svg_wrap("".join(parts), 200)


def svg_result_card(metric, value, x, y, color="#6ea8fe"):
    return (
        f'<rect x="{x}" y="{y}" width="110" height="50" rx="6" fill="#2b3035" stroke="#495057" stroke-width="1"/>'
        f'<text x="{x+55}" y="{y+22}" fill="{color}" font-size="16" text-anchor="middle" font-weight="bold" font-family="monospace">{value}</text>'
        f'<text x="{x+55}" y="{y+40}" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">{metric}</text>'
    )


def svg_result(estimates: list, true_az: float, true_sp: float) -> str:
    n = len(estimates)
    if n == 0:
        return _svg_wrap('<text x="250" y="105" fill="#adb5bd" font-size="14" text-anchor="middle" font-family="monospace">Нет данных</text>', 200)
    avg_az = float(np.mean([e.azimuth_deg for e in estimates]))
    avg_sp = float(np.mean([e.speed_ms for e in estimates]))
    avg_corr = float(np.mean([e.correlation for e in estimates]))
    az_err = abs(avg_az - true_az)
    sp_err = abs(avg_sp - true_sp)
    good = sum(1 for e in estimates if e.quality and isinstance(e.quality, dict) and e.quality.get("quality") == "good")
    marginal = sum(1 for e in estimates if e.quality and isinstance(e.quality, dict) and e.quality.get("quality") == "marginal")
    poor = sum(1 for e in estimates if e.quality and isinstance(e.quality, dict) and e.quality.get("quality") == "poor")
    az_color = "#ea868f" if az_err > 20 else "#ffda6a"
    sp_color = "#ea868f" if sp_err > 15 else "#ffda6a"
    parts = []
    parts.append(f'<text x="250" y="18" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Итоговые метрики ({n} оценок)</text>')
    parts.append(svg_result_card("Азимут (°)", f"{avg_az:.1f}", 25, 40, "#6ea8fe"))
    parts.append(svg_result_card("Скорость (м/с)", f"{avg_sp:.1f}", 145, 40, "#75b798"))
    parts.append(svg_result_card("NCC", f"{avg_corr:.3f}", 265, 40, "#ffda6a"))
    parts.append(svg_result_card("Ошибка азимута (°)", f"{az_err:.1f}", 25, 100, az_color))
    parts.append(svg_result_card("Ошибка скорости (м/с)", f"{sp_err:.1f}", 145, 100, sp_color))
    parts.append('<rect x="265" y="100" width="110" height="50" rx="6" fill="#2b3035" stroke="#495057" stroke-width="1"/>')
    parts.append(f'<text x="320" y="122" fill="#75b798" font-size="16" text-anchor="middle" font-weight="bold" font-family="monospace">{good}</text>')
    parts.append('<text x="320" y="140" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">Good</text>')
    parts.append('<rect x="25" y="165" width="12" height="12" fill="#75b798" rx="2"/>')
    parts.append(f'<text x="42" y="175" fill="#75b798" font-size="10" font-family="monospace">{good} good</text>')
    parts.append('<rect x="125" y="165" width="12" height="12" fill="#ffda6a" rx="2"/>')
    parts.append(f'<text x="142" y="175" fill="#ffda6a" font-size="10" font-family="monospace">{marginal} marginal</text>')
    parts.append('<rect x="250" y="165" width="12" height="12" fill="#ea868f" rx="2"/>')
    parts.append(f'<text x="267" y="175" fill="#ea868f" font-size="10" font-family="monospace">{poor} poor</text>')
    parts.append(f'<text x="250" y="215" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">Азимут={avg_az:.0f}° | Скорость={avg_sp:.0f} м/с</text>')
    return _svg_wrap("".join(parts), 240)


def svg_corridor(corridor_w: float) -> str:
    half_w = min(corridor_w / 2, 200)
    norm = half_w / 200 * 440 / 2
    parts = []
    parts.append(f'<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Адаптивный коридор: {corridor_w:.0f} м</text>')
    parts.append('<line x1="30" y1="90" x2="470" y2="90" stroke="#495057" stroke-width="1" stroke-dasharray="4,4"/>')
    parts.append(f'<rect x="{250 - norm:.1f}" y="70" width="{2 * norm:.1f}" height="40" fill="none" stroke="#6ea8fe" stroke-width="2" rx="4"/>')
    parts.append('<line x1="250" y1="70" x2="250" y2="110" stroke="#6ea8fe" stroke-width="1" stroke-dasharray="2,2"/>')
    parts.append('<text x="250" y="100" fill="#6ea8fe" font-size="10" text-anchor="middle" font-family="monospace">INS счисление</text>')
    parts.append(f'<text x="{250 - norm - 5:.1f}" y="95" fill="#ea868f" font-size="9" text-anchor="end" font-family="monospace">граница</text>')
    parts.append(f'<text x="{250 + norm + 5:.1f}" y="95" fill="#ea868f" font-size="9" text-anchor="start" font-family="monospace">граница</text>')
    parts.append(f'<text x="250" y="180" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">Поиск TERCOM ведётся внутри коридора ±{corridor_w/2:.0f}м от счисленной позиции</text>')
    return _svg_wrap("".join(parts), 200)


def svg_fingerprints(std_values: List[float], grad_values: List[float]) -> str:
    n = len(std_values)
    if n == 0:
        return _svg_wrap('<text x="250" y="105" fill="#adb5bd" font-size="14" text-anchor="middle" font-family="monospace">Нет данных</text>', 200)
    pw, ph = 440, 180
    bar_w = pw / max(n, 1)
    std_min, std_max = min(std_values), max(std_values)
    std_rng = max(std_max - std_min, 1)
    grad_min, grad_max = min(grad_values), max(grad_values)
    grad_rng = max(grad_max - grad_min, 1)
    parts = []
    parts.append('<text x="250" y="14" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Fingerprint-ы вдоль маршрута</text>')
    for i in range(n):
        sh = max((std_values[i] - std_min) / std_rng * ph * 0.8, 2)
        parts.append(f'<rect x="{30 + i*bar_w:.1f}" y="{20 + ph - sh:.1f}" width="{bar_w*0.4:.2f}" height="{sh:.1f}" fill="#6ea8fe" rx="1"/>')
        gh = max((grad_values[i] - grad_min) / grad_rng * ph * 0.8, 2)
        parts.append(f'<rect x="{30 + i*bar_w + bar_w*0.45:.1f}" y="{20 + ph - gh:.1f}" width="{bar_w*0.4:.2f}" height="{gh:.1f}" fill="#75b798" rx="1"/>')
    parts.append('<text x="30" y="216" fill="#6ea8fe" font-size="9" font-family="monospace">■ std_elevation</text>')
    parts.append('<text x="160" y="216" fill="#75b798" font-size="9" font-family="monospace">■ gradient</text>')
    parts.append('<text x="250" y="235" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">точки маршрута</text>')
    return _svg_wrap("".join(parts), 240)


def svg_empty(msg: str = "Нет данных") -> str:
    return _svg_wrap(f'<text x="240" y="105" fill="#adb5bd" font-size="14" text-anchor="middle" font-family="monospace">{msg}</text>', 200)

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
    parts.append(f'<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">NMEA — радиовысотомер ({n} отсчётов)</text>')
    for i in range(5):
        y = 20 + ph * i / 4
        val = vmax - (vmax - vmin) * i / 4
        parts.append(f'<line x1="28" y1="{y:.1f}" x2="470" y2="{y:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="26" y="{y+3:.1f}" fill="#adb5bd" font-size="9" text-anchor="end" font-family="monospace">{val:.0f}</text>')
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')
    parts.append('<text x="250" y="250" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">отсчёт</text>')
    return _svg_wrap("".join(parts), 260)


def svg_buffer(window_size: int, fill: int) -> str:
    disp_n = min(window_size, 50) if window_size > 50 else window_size
    cell_w = 440 / max(disp_n, 1)
    seg = max(1, window_size // disp_n) if window_size > 50 else 1
    parts = []
    parts.append(f'<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Буфер — скользящее окно ({fill}/{window_size})</text>')
    parts.append(f'<text x="250" y="36" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">заполнено {fill / window_size * 100:.0f}%</text>')

    sim_vals = []
    for i in range(disp_n):
        idx = i * seg
        progress = idx / max(window_size, 1)
        v = 50 + 40 * math.sin(progress * math.tau * 3) + 20 * math.cos(progress * math.tau * 0.7)
        is_filled = idx < fill
        sim_vals.append(v if is_filled else None)
        x1 = 30 + i * cell_w
        if is_filled:
            brightness = 0.3 + 0.7 * (idx / max(fill, 1))
            r = int(66 + (117 - 66) * brightness)
            g = int(142 + (183 - 142) * brightness)
            b = int(254 + (152 - 254) * brightness)
            color = f"#{r:02x}{g:02x}{b:02x}"
            is_new = (idx <= fill < idx + seg)
            if is_new:
                parts.append(f'<rect x="{x1:.1f}" y="72" width="{cell_w - 0.5:.1f}" height="22" fill="#75b798" stroke="#495057" stroke-width="0.3" rx="1"/>')
            else:
                parts.append(f'<rect x="{x1:.1f}" y="72" width="{cell_w - 0.5:.1f}" height="22" fill="{color}" stroke="#495057" stroke-width="0.3" rx="1"/>')
        else:
            parts.append(f'<rect x="{x1:.1f}" y="72" width="{cell_w - 0.5:.1f}" height="22" fill="#2b3035" stroke="#495057" stroke-width="0.3" rx="1"/>')

    profile_top = 50
    profile_h = 50
    vmin, vmax = 0, 100
    prof_pts = []
    for i in range(disp_n):
        if sim_vals[i] is not None:
            x = 30 + i * cell_w + cell_w / 2
            y = profile_top + profile_h - (sim_vals[i] - vmin) / (vmax - vmin) * profile_h
            prof_pts.append(f"{x:.1f},{y:.1f}")
    if prof_pts:
        parts.append(f'<polyline points="{" ".join(prof_pts)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')

    parts.append('<polygon points="30,105 38,110 30,115" fill="#495057"/>')
    parts.append('<text x="42" y="113" fill="#495057" font-size="8" font-family="monospace">старые →</text>')
    parts.append(f'<polygon points="{470:.1f},105 {462:.1f},110 {470:.1f},115" fill="#6ea8fe"/>')
    parts.append('<text x="430" y="113" fill="#6ea8fe" font-size="8" font-family="monospace">→ новые</text>')

    legend_y = 130
    parts.append(f'<text x="30" y="{legend_y + 10}" fill="#6ea8fe" font-size="8" font-family="monospace">профиль рельефа в буфере</text>')
    parts.append(f'<rect x="200" y="{legend_y}" width="10" height="8" fill="#75b798" rx="1"/>')
    parts.append(f'<text x="214" y="{legend_y + 8}" fill="#75b798" font-size="8" font-family="monospace">новый отсчёт</text>')
    parts.append(f'<rect x="290" y="{legend_y}" width="10" height="8" fill="#2b3035" stroke="#495057" stroke-width="0.5" rx="1"/>')
    parts.append(f'<text x="304" y="{legend_y + 8}" fill="#adb5bd" font-size="8" font-family="monospace">пусто</text>')
    return _svg_wrap("".join(parts), 160)


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
        parts.append('<text x="380" y="135" fill="#75b798" font-size="9" font-family="monospace">эталонный (DEM)</text>')
        if len(observed) > 1 and len(reference) > 1:
            mn = min(len(observed), len(reference))
            cc = float(np.corrcoef(observed[:mn], reference[:mn])[0, 1])
            parts.append(f'<text x="380" y="175" fill="#dee2e6" font-size="9" font-family="monospace">NCC: {cc:.3f}</text>')
    parts.append('<text x="380" y="155" fill="#6ea8fe" font-size="9" font-family="monospace">измеренный (радар)</text>')
    parts.append('<text x="250" y="250" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">отсчёт вдоль траектории</text>')
    return _svg_wrap("".join(parts), 260)


def svg_heatmap(matrix: np.ndarray, az_labels: List[str], sp_labels: List[str], title: str,
                highlight_az: Optional[float] = None, highlight_sp: Optional[float] = None,
                highlight_ri: Optional[int] = None, highlight_ci: Optional[int] = None,
                palette: Optional[List[str]] = None) -> str:
    nz, ns = matrix.shape
    cell_h = 180 / nz if nz else 1
    cell_w = 350 / ns if ns else 1
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
            parts.append(f'<rect x="{80 + c*cell_w:.2f}" y="{20 + r*cell_h:.2f}" width="{cell_w:.2f}" height="{cell_h:.2f}" fill="{color}"/>')

    if hl_ri is not None and hl_ci is not None and hl_ri >= 0 and hl_ci >= 0 and hl_ri < nz and hl_ci < ns:
        cx = 80 + hl_ci * cell_w + cell_w / 2
        cy = 20 + hl_ri * cell_h + cell_h / 2
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{max(cell_w, cell_h) * 0.7:.1f}" fill="none" stroke="#fff" stroke-width="2"/>')
        parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3" fill="#fff"/>')
    ticks_n = min(nz, 10)
    for i in range(ticks_n):
        r = int(i * nz / ticks_n)
        if r < len(az_labels):
            parts.append(f'<text x="76" y="{22 + r*cell_h + cell_h/2:.1f}" fill="#adb5bd" font-size="7" text-anchor="end" font-family="monospace">{az_labels[r]}</text>')
    for i in range(min(ns, 6)):
        c = int(i * ns / 6)
        if c < len(sp_labels):
            parts.append(f'<text x="{80 + c*cell_w + cell_w/2:.1f}" y="212" fill="#adb5bd" font-size="7" text-anchor="middle" font-family="monospace">{sp_labels[c]}</text>')
    cb_x = 440
    cb_w = 12
    cb_h = 180
    for i in range(10):
        c = _val_color(vmin + (vmax - vmin) * (1 - i / 9), vmin, vmax, pal)
        parts.append(f'<rect x="{cb_x}" y="{20 + i * cb_h // 10}" width="{cb_w}" height="{cb_h // 10 + 1}" fill="{c}" stroke="none"/>')
    parts.append(f'<text x="{cb_x + cb_w // 2}" y="18" fill="#dee2e6" font-size="7" text-anchor="middle" font-family="monospace">{vmax:.2f}</text>')
    parts.append(f'<text x="{cb_x + cb_w // 2}" y="214" fill="#dee2e6" font-size="7" text-anchor="middle" font-family="monospace">{vmin:.2f}</text>')
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
    if len(corr_full) == 0:
        return _svg_wrap('<text x="240" y="105" fill="#adb5bd" font-size="14" text-anchor="middle" font-family="monospace">Нет данных</text>', 200)
    n = len(corr_full)
    pw, ph = 440, 180
    vmin, vmax = float(np.min(corr_full)), float(np.max(corr_full))
    if vmax <= vmin:
        vmax = vmin + 1
    zero_y = 15 + ph * vmax / (vmax - vmin) if vmax != vmin else 15 + ph / 2
    pts = []
    for i in range(n):
        x = 30 + i * pw / max(n - 1, 1)
        y = 15 + ph - (corr_full[i] - vmin) / (vmax - vmin) * ph
        pts.append(f"{x:.1f},{y:.1f}")
    fill = " ".join(pts) + f" 30,{zero_y:.1f} 470,{zero_y:.1f}"
    lag_idx = best_lag + n // 2
    lag_x = 30 + lag_idx * pw / max(n - 1, 1) if n > 1 else 30
    zero_x = 30 + (n // 2) * pw / max(n - 1, 1) if n > 1 else 30

    parts = []
    parts.append('<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Lag — временной сдвиг профилей</text>')
    parts.append('<text x="14" y="105" fill="#adb5bd" font-size="9" text-anchor="middle" transform="rotate(-90,14,105)" font-family="monospace">NCC</text>')
    for i in range(5):
        y = 15 + ph * (1 - i / 4)
        val = vmin + (vmax - vmin) * i / 4
        parts.append(f'<line x1="28" y1="{y:.1f}" x2="470" y2="{y:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="24" y="{y+3:.1f}" fill="#adb5bd" font-size="8" text-anchor="end" font-family="monospace">{val:.2f}</text>')

    baseline_cc = 0.0
    base_y = 15 + ph - (baseline_cc - vmin) / (vmax - vmin) * ph
    if base_y < 15:
        base_y = 15 + ph * 0.6
    elif base_y > 15 + ph:
        base_y = 15 + ph * 0.4

    parts.append(f'<line x1="30" y1="{base_y:.1f}" x2="470" y2="{base_y:.1f}" stroke="#6c757d" stroke-width="0.5" stroke-dasharray="3,3"/>')
    parts.append(f'<text x="36" y="{base_y - 3:.1f}" fill="#6c757d" font-size="7" font-family="monospace">нет совпадения (NCC=0)</text>')

    grad_id = "lag-grad"
    parts.append(f'<defs><linearGradient id="{grad_id}" x1="0" x2="0" y1="0" y2="1">'
                 f'<stop offset="0%" stop-color="#6ea8fe" stop-opacity="0.35"/>'
                 f'<stop offset="100%" stop-color="#6ea8fe" stop-opacity="0.05"/>'
                 f'</linearGradient></defs>')
    parts.append(f'<polygon points="{fill}" fill="url(#{grad_id})" stroke="none"/>')
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#6ea8fe" stroke-width="2" stroke-linejoin="round"/>')

    parts.append(f'<line x1="{lag_x:.1f}" y1="15" x2="{lag_x:.1f}" y2="{15+ph}" stroke="#ea868f" stroke-width="1.5" stroke-dasharray="4,3"/>')
    lag_arrow_y = 15 + ph - (corr_full[lag_idx] - vmin) / (vmax - vmin) * ph if 0 <= lag_idx < n else 15
    parts.append(f'<text x="{lag_x:.1f}" y="{lag_arrow_y - 6:.1f}" fill="#ea868f" font-size="8" text-anchor="middle" font-family="monospace">▲</text>')
    parts.append(f'<text x="{lag_x:.1f}" y="216" fill="#ea868f" font-size="10" text-anchor="middle" font-weight="bold" font-family="monospace">пик: lag = {best_lag} отсчётов</text>')
    parts.append(f'<text x="{lag_x:.1f}" y="230" fill="#ea868f" font-size="8" text-anchor="middle" font-family="monospace">← наилучшее совмещение профилей</text>')

    parts.append('<text x="34" y="226" fill="#adb5bd" font-size="8" text-anchor="start" font-family="monospace">запаздывание ←</text>')
    parts.append(f'<text x="{zero_x:.1f}" y="226" fill="#dee2e6" font-size="8" text-anchor="middle" font-family="monospace">сдвиг=0</text>')
    parts.append('<text x="466" y="226" fill="#adb5bd" font-size="8" text-anchor="end" font-family="monospace">→ опережение</text>')
    return _svg_wrap("".join(parts), 250)


def svg_trajectory(true_lats: List[float], true_lons: List[float],
                   est_lats: List[float], est_lons: List[float],
                   filtered_lats: Optional[List[float]] = None,
                   filtered_lons: Optional[List[float]] = None) -> str:
    if not true_lats or not true_lons:
        return ""
    pw, ph = 440, 220
    all_lats = true_lats + est_lats + (filtered_lats or [])
    all_lons = true_lons + est_lons + (filtered_lons or [])
    lat_min, lat_max = min(all_lats), max(all_lats)
    lon_min, lon_max = min(all_lons), max(all_lons)
    lat_rng = max(lat_max - lat_min, 1e-6)
    lon_rng = max(lon_max - lon_min, 1e-6)
    margin = max(lat_rng * 0.1, lon_rng * 0.1, 0.0002)
    lat_min -= margin
    lat_max += margin
    lon_min -= margin
    lon_max += margin
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

    def _tick_label(val):
        if abs(val) < 1:
            return f"{val:.4f}"
        if abs(val) < 10:
            return f"{val:.3f}"
        return f"{val:.2f}"

    parts = []
    parts.append('<text x="250" y="14" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Траектория: истинная vs восстановленная</text>')
    parts.append(f'<polyline points="{_pts(true_lats, true_lons)}" fill="none" stroke="#75b798" stroke-width="2" stroke-linejoin="round" stroke-dasharray="4,3"/>')
    parts.append(f'<polyline points="{_pts(est_lats, est_lons)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')
    if filtered_lats and filtered_lons:
        parts.append(f'<polyline points="{_pts(filtered_lats, filtered_lons)}" fill="none" stroke="#d2b8ff" stroke-width="1.5" stroke-linejoin="round"/>')

    if true_lats and true_lons and est_lats and est_lons:
        n_err_arrows = min(4, len(true_lats) - 1)
        for i in range(n_err_arrows):
            idx = int((i + 1) * (len(true_lats) - 1) / max(n_err_arrows, 1))
            idx = min(idx, len(true_lats) - 1, len(est_lats) - 1)
            tx = 30 + (true_lons[idx] - lon_min) / (lon_max - lon_min) * pw
            ty = 15 + ph - (true_lats[idx] - lat_min) / (lat_max - lat_min) * ph
            ex = 30 + (est_lons[idx] - lon_min) / (lon_max - lon_min) * pw
            ey = 15 + ph - (est_lats[idx] - lat_min) / (lat_max - lat_min) * ph
            parts.append(f'<line x1="{tx:.1f}" y1="{ty:.1f}" x2="{ex:.1f}" y2="{ey:.1f}" stroke="#ea868f" stroke-width="0.8" stroke-dasharray="2,2" stroke-opacity="0.6"/>')

    if true_lats and true_lons:
        sx, sy = 30 + (true_lons[0] - lon_min) / (lon_max - lon_min) * pw, 15 + ph - (true_lats[0] - lat_min) / (lat_max - lat_min) * ph
        parts.append(f'<circle cx="{sx:.1f}" cy="{sy:.1f}" r="4" fill="#75b798" stroke="#212529" stroke-width="1.5"/>')
        parts.append(f'<text x="{sx:.1f}" y="{sy - 6:.1f}" fill="#75b798" font-size="8" text-anchor="middle" font-family="monospace">старт</text>')
        ex, ey = 30 + (true_lons[-1] - lon_min) / (lon_max - lon_min) * pw, 15 + ph - (true_lats[-1] - lat_min) / (lat_max - lat_min) * ph
        parts.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4" fill="#ea868f" stroke="#212529" stroke-width="1.5"/>')
        if est_lats and est_lons and len(est_lats) > 1:
            ex_e, ey_e = 30 + (est_lons[-1] - lon_min) / (lon_max - lon_min) * pw, 15 + ph - (est_lats[-1] - lat_min) / (lat_max - lat_min) * ph
            lat_err = (est_lats[-1] - true_lats[-1]) * 111320
            lon_err = (est_lons[-1] - true_lons[-1]) * 111320 * math.cos(math.radians(true_lats[-1]))
            err_m = math.sqrt(lat_err**2 + lon_err**2)
            parts.append(f'<text x="{ex_e:.1f}" y="{ey_e - 6:.1f}" fill="#ea868f" font-size="8" text-anchor="middle" font-family="monospace">ош:{err_m:.0f}м</text>')
        else:
            parts.append(f'<text x="{ex:.1f}" y="{ey - 6:.1f}" fill="#ea868f" font-size="8" text-anchor="middle" font-family="monospace">конец</text>')

    for i in range(4):
        frac = i / 3
        lat_v = lat_min + frac * (lat_max - lat_min)
        lon_v = lon_min + frac * (lon_max - lon_min)
        y_t = 15 + ph * (1 - frac)
        x_t = 30 + pw * frac
        parts.append(f'<line x1="26" y1="{y_t:.1f}" x2="30" y2="{y_t:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="24" y="{y_t + 3:.1f}" fill="#adb5bd" font-size="7" text-anchor="end" font-family="monospace">{_tick_label(lat_v)}</text>')
        parts.append(f'<line x1="{x_t:.1f}" y1="{15 + ph:.1f}" x2="{x_t:.1f}" y2="{15 + ph + 4:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="{x_t:.1f}" y="{15 + ph + 14:.1f}" fill="#adb5bd" font-size="7" text-anchor="middle" font-family="monospace">{_tick_label(lon_v)}</text>')

    parts.append('<rect x="28" y="22" width="90" height="44" fill="#212529" fill-opacity="0.85" rx="4"/>')
    parts.append('<line x1="34" y1="32" x2="50" y2="32" stroke="#75b798" stroke-width="2" stroke-dasharray="4,3"/>')
    parts.append('<text x="55" y="35" fill="#75b798" font-size="8" font-family="monospace">истинная</text>')
    parts.append('<line x1="34" y1="44" x2="50" y2="44" stroke="#6ea8fe" stroke-width="1.5"/>')
    parts.append('<text x="55" y="47" fill="#6ea8fe" font-size="8" font-family="monospace">TERCOM</text>')
    if filtered_lats and filtered_lons:
        parts.append('<line x1="34" y1="56" x2="50" y2="56" stroke="#d2b8ff" stroke-width="1.5"/>')
        parts.append('<text x="55" y="59" fill="#d2b8ff" font-size="8" font-family="monospace">ESKF</text>')
    parts.append('<text x="250" y="265" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">долгота</text>')
    parts.append('<text x="12" y="130" fill="#adb5bd" font-size="9" text-anchor="middle" transform="rotate(-90,12,130)" font-family="monospace">широта</text>')
    return _svg_wrap("".join(parts), 274)


def svg_eskf_error(errors: List[float], title: str, color: str = "#6ea8fe") -> str:
    n = len(errors)
    if n < 2:
        return ""
    pw, ph = 440, 155
    vmin, vmax = float(min(errors)), float(max(errors))
    if vmax <= vmin:
        vmax = vmin + 1
    margin_v = (vmax - vmin) * 0.1
    vmin -= margin_v
    vmax += margin_v
    pts = []
    for i in range(n):
        x = 30 + i * pw / max(n - 1, 1)
        y = 20 + ph - (errors[i] - vmin) / (vmax - vmin) * ph
        pts.append(f"{x:.1f},{y:.1f}")
    area_pts = ["30," + str(20 + ph)] + pts + [f"470,{20 + ph}"]
    parts = []
    parts.append(f'<text x="250" y="14" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">{title}</text>')
    for i in range(5):
        y = 20 + ph * i / 4
        val = vmax - (vmax - vmin) * i / 4
        parts.append(f'<line x1="28" y1="{y:.1f}" x2="470" y2="{y:.1f}" stroke="#2b3035" stroke-width="0.5"/>')
        parts.append(f'<text x="26" y="{y+3:.1f}" fill="#adb5bd" font-size="8" text-anchor="end" font-family="monospace">{val:.0f}</text>')
    parts.append(f'<polygon points="{" ".join(area_pts)}" fill="{color}" fill-opacity="0.1"/>')
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" stroke-width="1.5" stroke-linejoin="round"/>')
    window = max(3, n // 5)
    trend = []
    for i in range(n):
        s = max(0, i - window // 2)
        e = min(n, i + window // 2 + 1)
        trend.append(sum(errors[s:e]) / (e - s))
    trend_pts = []
    for i in range(n):
        x = 30 + i * pw / max(n - 1, 1)
        y = 20 + ph - (trend[i] - vmin) / (vmax - vmin) * ph
        trend_pts.append(f"{x:.1f},{y:.1f}")
    parts.append(f'<polyline points="{" ".join(trend_pts)}" fill="none" stroke="#dee2e6" stroke-width="2" stroke-dasharray="4,3" stroke-linejoin="round"/>')
    start_v, end_v = errors[0], errors[-1]
    if end_v < start_v:
        parts.append(f'<text x="360" y="36" fill="#75b798" font-size="9" font-family="monospace">✓ схождение: {start_v:.0f} → {end_v:.0f}м</text>')
    else:
        parts.append(f'<text x="360" y="36" fill="#ea868f" font-size="9" font-family="monospace">✗ расхождение: {start_v:.0f} → {end_v:.0f}м</text>')
    parts.append('<text x="250" y="208" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">шаг</text>')
    parts.append('<text x="26" y="14" fill="#adb5bd" font-size="7" text-anchor="end" font-family="monospace">м</text>')
    return _svg_wrap("".join(parts), 220)


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
    parts.append(f'<text x="100" y="175" fill="#adb5bd" font-size="9" font-family="monospace">острота пика: {sharpness:.2f}</text>')
    parts.append(f'<text x="280" y="175" fill="#adb5bd" font-size="9" font-family="monospace">коэф. дискриминации: {disc_ratio:.2f}</text>')
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
    has_quality = any(e.quality for e in estimates)
    if has_quality:
        good = sum(1 for e in estimates if e.quality and isinstance(e.quality, dict) and e.quality.get("quality") == "good")
        marginal = sum(1 for e in estimates if e.quality and isinstance(e.quality, dict) and e.quality.get("quality") == "marginal")
        poor = sum(1 for e in estimates if e.quality and isinstance(e.quality, dict) and e.quality.get("quality") == "poor")
    else:
        if avg_corr > 0.9:
            good = n
            marginal = 0
            poor = 0
        elif avg_corr > 0.7:
            good = 0
            marginal = n
            poor = 0
        else:
            good = 0
            marginal = 0
            poor = n
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
    parts.append('<text x="320" y="140" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">Хорошо</text>')
    parts.append('<rect x="25" y="165" width="12" height="12" fill="#75b798" rx="2"/>')
    parts.append(f'<text x="42" y="175" fill="#75b798" font-size="10" font-family="monospace">{good} хороших</text>')
    parts.append('<rect x="125" y="165" width="12" height="12" fill="#ffda6a" rx="2"/>')
    parts.append(f'<text x="142" y="175" fill="#ffda6a" font-size="10" font-family="monospace">{marginal} пограничных</text>')
    parts.append('<rect x="250" y="165" width="12" height="12" fill="#ea868f" rx="2"/>')
    parts.append(f'<text x="267" y="175" fill="#ea868f" font-size="10" font-family="monospace">{poor} плохих</text>')
    if avg_corr > 0.9:
        expl = "Корреляция > 0.9 — оценка надёжна"
    elif avg_corr > 0.7:
        expl = "Корреляция 0.7–0.9 — требуется подтверждение"
    else:
        expl = "Корреляция < 0.7 — возможен сбой"
    parts.append(f'<text x="250" y="218" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">{expl}</text>')
    parts.append(f'<text x="250" y="240" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">Азимут={avg_az:.0f}° | Скорость={avg_sp:.0f} м/с | NCC={avg_corr:.3f}</text>')
    return _svg_wrap("".join(parts), 260)


def svg_corridor(corridor_w: float) -> str:
    half_w = min(corridor_w / 20, 100)
    cone_l = max(half_w * 0.2, 4)
    cone_r = max(half_w, 10)
    cy = 75
    parts = []
    parts.append(f'<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Адаптивный коридор: {corridor_w:.0f} м</text>')
    parts.append(f'<polygon points="30,{cy-cone_l} 470,{cy-cone_r} 470,{cy+cone_r} 30,{cy+cone_l}" fill="rgba(110,168,254,0.08)" stroke="#6ea8fe" stroke-width="1"/>')
    parts.append(f'<line x1="30" y1="{cy}" x2="470" y2="{cy}" stroke="#6ea8fe" stroke-width="1.5" stroke-dasharray="6,4"/>')
    parts.append(f'<polygon points="242,{cy-8} 258,{cy-8} 250,{cy+4}" fill="#dee2e6"/>')
    for i in range(7):
        tx = 30 + i * 440 / 6
        th = 10 + 6 * math.sin(i * 1.7 + 0.3)
        parts.append(f'<path d="M{tx:.0f},130 Q{tx+25:.0f},{130-th:.0f} {tx+55:.0f},130" fill="none" stroke="#495057" stroke-width="1" stroke-opacity="0.7"/>')
    parts.append(f'<text x="{250-cone_r-4:.0f}" y="{cy-cone_r-4:.0f}" fill="#ea868f" font-size="8" text-anchor="end" font-family="monospace">±{corridor_w/2:.0f}м</text>')
    parts.append(f'<text x="{250+cone_r+4:.0f}" y="{cy-cone_r-4:.0f}" fill="#ea868f" font-size="8" text-anchor="start" font-family="monospace">±{corridor_w/2:.0f}м</text>')
    parts.append('<text x="30" y="130" fill="#adb5bd" font-size="8" font-family="monospace">рельеф</text>')
    parts.append('<text x="250" y="175" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">Дрейф INS растёт → коридор расширяется</text>')
    return _svg_wrap("".join(parts), 190)


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
    for i in range(5):
        y = 20 + ph * (1 - i / 4)
        val = std_min + std_rng * i / 4
        parts.append(f'<line x1="28" y1="{y:.1f}" x2="470" y2="{y:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="24" y="{y+3:.1f}" fill="#adb5bd" font-size="7" text-anchor="end" font-family="monospace">{val:.0f}</text>')
    for i in range(n):
        sh = max((std_values[i] - std_min) / std_rng * ph * 0.8, 2)
        parts.append(f'<rect x="{30 + i*bar_w:.1f}" y="{20 + ph - sh:.1f}" width="{bar_w*0.4:.2f}" height="{sh:.1f}" fill="#6ea8fe" rx="1"/>')
        gh = max((grad_values[i] - grad_min) / grad_rng * ph * 0.8, 2)
        parts.append(f'<rect x="{30 + i*bar_w + bar_w*0.45:.1f}" y="{20 + ph - gh:.1f}" width="{bar_w*0.4:.2f}" height="{gh:.1f}" fill="#75b798" rx="1"/>')
    parts.append('<text x="30" y="216" fill="#6ea8fe" font-size="9" font-family="monospace">■ СКО высот (м)</text>')
    parts.append('<text x="175" y="216" fill="#75b798" font-size="9" font-family="monospace">■ градиент</text>')
    parts.append('<text x="250" y="235" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">точки маршрута</text>')
    return _svg_wrap("".join(parts), 240)


def svg_aggregated_profile(profiles: List[np.ndarray], aggregated: np.ndarray) -> str:
    n_profiles = len(profiles)
    if n_profiles < 2 or len(aggregated) < 2:
        return svg_empty("Недостаточно профилей для агрегирования")
    pw, ph = 440, 180
    vmin = min(float(np.min(aggregated)), min(float(np.min(p)) for p in profiles)) - 10
    vmax = max(float(np.max(aggregated)), max(float(np.max(p)) for p in profiles)) + 10
    if vmax <= vmin:
        vmax = vmin + 100
    parts = []
    parts.append('<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Агрегирование профилей — стабилизация шума</text>')
    for i in range(5):
        y = 20 + ph * i / 4
        val = vmax - (vmax - vmin) * i / 4
        parts.append(f'<line x1="28" y1="{y:.1f}" x2="470" y2="{y:.1f}" stroke="#495057" stroke-width="0.5"/>')
        parts.append(f'<text x="26" y="{y+3:.1f}" fill="#adb5bd" font-size="8" text-anchor="end" font-family="monospace">{val:.0f}</text>')
    for p in profiles[:min(5, n_profiles)]:
        pts = []
        for i in range(len(p)):
            x = 30 + i * pw / max(len(p) - 1, 1)
            y = 20 + ph - (p[i] - vmin) / (vmax - vmin) * ph
            pts.append(f"{x:.1f},{y:.1f}")
        parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#4d6b8a" stroke-width="1" stroke-opacity="0.5" stroke-linejoin="round"/>')
    pts = []
    for i in range(len(aggregated)):
        x = 30 + i * pw / max(len(aggregated) - 1, 1)
        y = 20 + ph - (aggregated[i] - vmin) / (vmax - vmin) * ph
        pts.append(f"{x:.1f},{y:.1f}")
    parts.append(f'<polyline points="{" ".join(pts)}" fill="none" stroke="#6ea8fe" stroke-width="2" stroke-linejoin="round"/>')
    parts.append('<rect x="310" y="148" width="18" height="9" fill="#4d6b8a" rx="1" opacity="0.5"/>')
    parts.append('<text x="332" y="156" fill="#adb5bd" font-size="9" font-family="monospace">сырые окна</text>')
    parts.append('<line x1="310" y1="170" x2="328" y2="170" stroke="#6ea8fe" stroke-width="2"/>')
    parts.append('<text x="332" y="174" fill="#6ea8fe" font-size="9" font-family="monospace">агрегированный</text>')
    parts.append('<text x="250" y="230" fill="#adb5bd" font-size="9" text-anchor="middle" font-family="monospace">отсчёт вдоль траектории</text>')
    return _svg_wrap("".join(parts), 260)


def svg_rolling_discrimination(current: np.ndarray, previous: np.ndarray, corr: float) -> str:
    if len(current) < 2 or len(previous) < 2:
        return svg_empty("Недостаточно данных для скользящей дискриминации")
    pw, ph = 440, 150
    mn = min(len(current), len(previous))
    vmin = min(float(np.min(current[:mn])), float(np.min(previous[:mn]))) - 10
    vmax = max(float(np.max(current[:mn])), float(np.max(previous[:mn]))) + 10
    if vmax <= vmin:
        vmax = vmin + 100
    parts = []
    parts.append('<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Скользящая дискриминация — сравнение профилей</text>')
    parts.append(f'<text x="250" y="32" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">correlation: {corr:.3f}</text>')
    pts_c, pts_p = [], []
    for i in range(mn):
        x = 30 + i * pw / max(mn - 1, 1)
        y_c = 35 + ph - (current[i] - vmin) / (vmax - vmin) * ph
        y_p = 35 + ph - (previous[i] - vmin) / (vmax - vmin) * ph
        pts_c.append(f"{x:.1f},{y_c:.1f}")
        pts_p.append(f"{x:.1f},{y_p:.1f}")
    parts.append(f'<polyline points="{" ".join(pts_c)}" fill="none" stroke="#6ea8fe" stroke-width="1.5" stroke-linejoin="round"/>')
    parts.append(f'<polyline points="{" ".join(pts_p)}" fill="none" stroke="#75b798" stroke-width="1.5" stroke-dasharray="4,3"/>')
    parts.append('<line x1="310" y1="160" x2="330" y2="160" stroke="#6ea8fe" stroke-width="1.5"/>')
    parts.append('<text x="335" y="164" fill="#6ea8fe" font-size="9" font-family="monospace">текущий</text>')
    parts.append('<line x1="310" y1="174" x2="330" y2="174" stroke="#75b798" stroke-width="1.5" stroke-dasharray="4,3"/>')
    parts.append('<text x="335" y="178" fill="#75b798" font-size="9" font-family="monospace">предыдущий</text>')
    status = "good" if corr > 0.95 else "marginal" if corr > 0.8 else "poor"
    parts.append(f'<text x="250" y="230" fill="#adb5bd" font-size="10" text-anchor="middle" font-family="monospace">статус: {status}</text>')
    return _svg_wrap("".join(parts), 250)


def svg_r_matrix(base_r: float, scale: float, color: str = "#ffda6a") -> str:
    parts = []
    parts.append('<text x="250" y="16" fill="#dee2e6" font-size="12" text-anchor="middle" font-family="monospace">Адаптивная R-матрица — доверие к измерению</text>')
    parts.append('<rect x="150" y="60" width="200" height="60" rx="6" fill="#2b3035" stroke="#495057" stroke-width="1"/>')
    parts.append(f'<text x="250" y="85" fill="#dee2e6" font-size="14" text-anchor="middle" font-family="monospace">R_scale: {scale:.1f}x</text>')
    parts.append(f'<text x="250" y="105" fill="{color}" font-size="10" text-anchor="middle" font-family="monospace">base_R: {base_r:.1f} м²</text>')
    if scale > 5:
        parts.append('<text x="250" y="140" fill="#ea868f" font-size="10" text-anchor="middle" font-family="monospace">⚠️ Низкое доверие — фильтр Калмана игнорирует коррекцию</text>')
    else:
        parts.append('<text x="250" y="140" fill="#75b798" font-size="10" text-anchor="middle" font-family="monospace">✓ Нормальное доверие — коррекция применяется</text>')
    return _svg_wrap("".join(parts), 180)


def svg_empty(msg: str = "Нет данных") -> str:
    return _svg_wrap(f'<text x="240" y="105" fill="#adb5bd" font-size="14" text-anchor="middle" font-family="monospace">{msg}</text>', 200)

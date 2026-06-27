const state = {
    steps: [],
    placeholders: 19,
    currentIndex: -1,
    isPlaying: false,
    isComplete: false,
    speed: 1,
    timer: null,
    scenarioId: null,
    eventSource: null,
};

const mapState = {
    instance: null,
    data: null,
    animTimer: null,
    animPos: 0,
    animPlaying: false,
    droneMarker: null,
    activeTrail: null,
    errorLines: null,
    layers: {},
};

const SPEEDS = [1, 2, 5, 10];
const BASE_DELAY = 2000;
const STEP_NAMES = [
    "Загрузка DEM", "Fingerprint-ы", "Коридор", "NMEA",
    "Буфер", "Профиль", "Coarse", "Fine",
    "NCC", "Lag", "Агрегирование", "Discrimination",
    "R-матрица", "Траектория", "ESKF",
    "Качество", "Итог", "Анализ ИИ", "Карта маршрута",
];

async function loadScenarios() {
    try {
        const res = await fetch('/api/scenarios');
        return await res.json();
    } catch (e) {
        console.error('Failed to load scenarios:', e);
        return {};
    }
}

function renderLanding(scenarios) {
    const sel = document.getElementById('scenario-select');
    const desc = document.getElementById('scenario-description');
    const startBtn = document.getElementById('start-btn');
    sel.innerHTML = '<option value="">— Выберите симуляцию —</option>';
    for (const [id, info] of Object.entries(scenarios)) {
        if (!info.exists) continue;
        const opt = document.createElement('option');
        opt.value = id;
        opt.textContent = info.name;
        sel.appendChild(opt);
    }
    sel.onchange = () => {
        const id = sel.value;
        if (id && scenarios[id]) {
            const info = scenarios[id];
            desc.innerHTML = `
                <div class="fw-semibold text-light mb-1">${info.name}</div>
                <div class="mb-2">${info.description}</div>
                <div class="text-secondary-emphasis small">
                    DEM: ${info.dem_size} · σ=${info.dem_std} · ${info.dem_name}
                </div>`;
            startBtn.disabled = false;
        } else {
            desc.textContent = 'Выберите сценарий для просмотра информации';
            startBtn.disabled = true;
        }
    };
    startBtn.onclick = () => {
        const id = sel.value;
        if (id) startSimulation(id);
    };
}

function startSimulation(scenarioId) {
    state.scenarioId = scenarioId;
    state.steps = [];
    state.currentIndex = -1;
    state.isPlaying = false;
    state.isComplete = false;
    state.speed = 1;

    document.getElementById('landing-screen').style.display = 'none';
    document.getElementById('sim-screen').style.display = 'flex';

    prefetchPlaceholders();
    updateProgress();
    updateStepList();
    setStatus('loading', 'Загрузка...');

    const url = `/api/simulate/${encodeURIComponent(scenarioId)}`;
    state.eventSource = new EventSource(url);
    state.eventSource.addEventListener('step', (e) => {
        const step = JSON.parse(e.data);
        state.steps.push(step);
        if (state.currentIndex === -1) {
            state.currentIndex = 0;
            renderCurrentStep();
            setStatus('running', 'Выполняется');
        }
        updateProgress();
        updateStepList();
    });
    state.eventSource.addEventListener('complete', () => {
        state.isComplete = true;
        setStatus('done', 'Завершено');
        state.eventSource.close();
        document.getElementById('ai-section').style.display = 'block';
        if (!state.isPlaying && state.steps.length > 0) {
            state.currentIndex = state.steps.length - 1;
            renderCurrentStep();
        }
        updateProgress();
        updateStepList();
    });
    state.eventSource.onerror = () => {
        console.error('SSE error');
        if (state.steps.length === 0) {
            const display = document.getElementById('step-display');
            display.innerHTML = `
                <div class="text-center py-5">
                    <div class="spinner mb-3"></div>
                    <div class="text-secondary-emphasis mb-2">Ожидание данных...</div>
                    <button class="btn btn-outline-secondary btn-sm" onclick="returnToLanding()">Назад</button>
                </div>`;
        }
    };
}

function returnToLanding() {
    cleanupMap();
    if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    state.isPlaying = false;
    document.getElementById('sim-screen').style.display = 'none';
    document.getElementById('landing-screen').style.display = 'flex';
}

function setStatus(type, text) {
    const badge = document.getElementById('status-badge');
    badge.className = 'status-badge ' + type;
    badge.textContent = text;
}

function prefetchPlaceholders() {
    const total = state.placeholders;
    const pct = 0;
    document.getElementById('progress-fill').style.width = pct + '%';
    document.getElementById('step-counter').textContent = `Шаг 0/${total}`;
}

function updateProgress() {
    const total = Math.max(state.steps.length, state.placeholders);
    const current = state.isComplete ? state.steps.length : Math.max(0, state.currentIndex + 1);
    const pct = Math.min(100, (current / total) * 100);
    document.getElementById('progress-fill').style.width = pct + '%';
    document.getElementById('step-counter').textContent =
        `Шаг ${current}/${total}` + (state.isComplete ? ' ✓' : '');
}

function updateStepList() {
    const container = document.getElementById('step-list');
    const displaySteps = state.steps.length > 0 ? state.steps : [];
    const totalSlots = Math.max(displaySteps.length, state.placeholders);
    let html = '';
    let currentPhase = '';
    for (let i = 0; i < totalSlots; i++) {
        if (i < displaySteps.length) {
            const step = displaySteps[i];
            if (step.phase_label !== currentPhase) {
                currentPhase = step.phase_label;
                const loc = step.location || '';
                html += `<div class="phase-label">${currentPhase}${loc ? ' <span class="location-badge">' + loc + '</span>' : ''}</div>`;
            }
            let cls = 'step-entry pending';
            if (i === state.currentIndex) cls = 'step-entry active';
            else if (i < state.currentIndex) cls = 'step-entry done';
            html += `<div class="${cls}" data-idx="${i}" onclick="goToStep(${i})">
                <span class="step-num">${step.number}</span>
                <div class="step-title">${step.title.split(' — ')[0]}</div>
                <div class="step-desc">${step.short_desc || ''}</div>
            </div>`;
        } else {
            html += `<div class="step-entry pending disabled" style="opacity:0.5">
                <span class="step-num">${i + 1}</span>${STEP_NAMES[i] || '...'}
            </div>`;
        }
    }
    container.innerHTML = html;
    container.scrollTop = 0;
}

function renderCurrentStep() {
    const step = state.steps[state.currentIndex];
    if (!step) return;
    const display = document.getElementById('step-display');
    const traj = step.metrics && step.metrics.trajectory;

    display.innerHTML = `
        <div class="step-header phase-${step.phase}">
            <span class="step-phase-badge">${step.phase_label} · Шаг ${step.number}</span>
            <h2>${step.title}</h2>
            <div class="step-subtitle">${step.subtitle}</div>
        </div>
        <div class="step-tags">
            ${step.tags.map(t => `<span class="tag ${t.includes('интерполя') || t.includes('CRS') || t.includes('scipy') ? 'tag-purple' : ''}">${t}</span>`).join('')}
        </div>
        <div class="step-task">
            <div class="label">🎯 Задача</div>
            ${step.task}
        </div>
        ${traj ? `
        <div id="trajectory-map" class="map-container"></div>
        <div class="map-bottom-bar">
            <input type="range" id="timeline-slider" min="0" max="100" value="0" class="timeline-slider">
            <div class="map-info-row">
                <button id="map-play-btn" class="btn-icon" style="width:auto;padding:0.25rem 0.75rem">▶ Играть</button>
                <span id="map-pos-info" class="text-secondary-emphasis small ms-2">Точка 0/0</span>
                <span id="map-params-info" class="text-light small ms-auto">—</span>
            </div>
        </div>` : `
        <div class="svg-container" id="svg-container">
            ${step.svg}
        </div>`}
        <div class="step-explanation">${step.explanation}</div>
        <div class="why-grid">
            ${step.why.map(([icon, title, text]) => `
                <div class="why-card">
                    <div class="why-icon">${icon}</div>
                    <div class="why-title">${title}</div>
                    <div class="why-text">${text}</div>
                </div>
            `).join('')}
        </div>
        ${step.metrics && !step.metrics.trajectory ? `
        <div class="metrics-grid">
            ${Object.entries(step.metrics).filter(([k]) => k !== 'trajectory').map(([k, v]) => `
                <div class="metric-card">
                    <div class="metric-value">${v}</div>
                    <div class="metric-label">${k.replace(/_/g, ' ')}</div>
                </div>
            `).join('')}
        </div>` : ''}`;

    if (traj) {
        if (traj && traj.true_path && traj.true_path.length > 0) {
            initTrajectoryMap(traj);
        } else {
            document.getElementById('trajectory-map').innerHTML = '<div class="text-center py-5 text-secondary-emphasis">Нет данных траектории</div>';
        }
        const svgEl = document.getElementById('trajectory-map');
        if (svgEl) svgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    } else {
        const svgEl = document.getElementById('svg-container');
        if (svgEl) svgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    updateStepList();
    updateProgress();
    updateControls();
}

function updateControls() {
    const prevBtn = document.getElementById('prev-btn');
    const nextBtn = document.getElementById('next-btn');
    const playBtn = document.getElementById('play-btn');
    prevBtn.disabled = state.currentIndex <= 0;
    const atEnd = state.isComplete && state.currentIndex >= state.steps.length - 1;
    nextBtn.disabled = atEnd || (!state.isComplete && state.currentIndex >= state.steps.length - 1);
    playBtn.textContent = state.isPlaying ? '⏸' : '▶';
    playBtn.className = 'btn-icon' + (state.isPlaying ? ' playing' : '');
}

function previousStep() {
    if (state.currentIndex > 0) {
        state.currentIndex--;
        renderCurrentStep();
        updateControls();
    }
}

function nextStep() {
    if (state.currentIndex < state.steps.length - 1) {
        state.currentIndex++;
        renderCurrentStep();
        updateControls();
    }
}

function goToStep(idx) {
    if (idx >= 0 && idx < state.steps.length) {
        state.currentIndex = idx;
        renderCurrentStep();
        updateControls();
    }
}

function togglePlay() {
    if (state.isPlaying) pause(); else play();
}

function play() {
    if (state.isComplete && state.currentIndex >= state.steps.length - 1) {
        state.currentIndex = 0;
        renderCurrentStep();
    }
    state.isPlaying = true;
    updateControls();
    scheduleNext();
}

function pause() {
    state.isPlaying = false;
    if (state.timer) { clearTimeout(state.timer); state.timer = null; }
    updateControls();
}

function scheduleNext() {
    if (!state.isPlaying) return;
    if (state.currentIndex < state.steps.length - 1) {
        state.timer = setTimeout(() => {
            state.currentIndex++;
            renderCurrentStep();
            scheduleNext();
        }, BASE_DELAY / state.speed);
    } else if (state.isComplete) {
        state.isPlaying = false;
        updateControls();
    } else {
        state.timer = setTimeout(scheduleNext, 500);
    }
}

function setSpeed(mult) {
    state.speed = mult;
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.speed) === mult);
    });
    if (state.isPlaying) {
        if (state.timer) { clearTimeout(state.timer); state.timer = null; }
        scheduleNext();
    }
}

async function runAiAnalysis() {
    const btn = document.getElementById('ai-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Анализ...';

    try {
        const res = await fetch(`/api/analyze/${state.scenarioId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({steps: state.steps}),
        });
        const result = await res.json();

        if (result.error) {
            alert('Ошибка анализа: ' + result.error);
            btn.disabled = false;
            btn.textContent = '🤖 Анализ ИИ агентов';
            return;
        }

        const svg = `
<svg viewBox="0 0 500 320" xmlns="http://www.w3.org/2000/svg" style="max-width:100%;height:auto">
<rect width="500" height="320" fill="#212529"/>
<text x="250" y="24" fill="#dee2e6" font-size="13" text-anchor="middle" font-family="monospace" font-weight="bold">📋 Саммари</text>
<text x="30" y="50" fill="#adb5bd" font-size="10" font-family="monospace">${result.summary || '—'}</text>
<text x="250" y="90" fill="#dee2e6" font-size="13" text-anchor="middle" font-family="monospace" font-weight="bold">🔍 Аномалии (${(result.anomalies || []).length})</text>
${(result.anomalies || []).slice(0, 4).map((a, i) =>
    `<text x="30" y="${115 + i * 20}" fill="${a.severity === 'high' ? '#ea868f' : a.severity === 'medium' ? '#ffda6a' : '#6ea8fe'}" font-size="9" font-family="monospace">${a.severity === 'high' ? '🔴' : a.severity === 'medium' ? '🟡' : '🟢'} ${a.text.length > 80 ? a.text.slice(0, 80) + '…' : a.text}</text>`
).join('')}
<text x="250" y="210" fill="#dee2e6" font-size="13" text-anchor="middle" font-family="monospace" font-weight="bold">💡 Предложения (${(result.suggestions || []).length})</text>
${(result.suggestions || []).slice(0, 4).map((s, i) =>
    `<text x="30" y="${235 + i * 20}" fill="#75b798" font-size="9" font-family="monospace">${i + 1}. ${s.text.length > 80 ? s.text.slice(0, 80) + '…' : s.text}</text>`
).join('')}
<text x="250" y="310" fill="#495057" font-size="8" text-anchor="middle" font-family="monospace">Модель: ${result.model || 'gemma4:e4b'}</text>
</svg>`;

        const aiStep = {
            id: 'ai-analysis',
            number: 18,
            phase: 'analysis',
            phase_label: 'Анализ ИИ',
            location: '🧠 Локально (Ollama)',
            title: '🤖 Анализ ИИ — аномалии и предложения',
            subtitle: 'Оценка качества прогона алгоритмом gemma4:e4b',
            explanation: result.summary || 'Анализ завершён.',
            task: 'Проверить аномалии и применить предложенные улучшения.',
            short_desc: 'Анализ аномалий и предложения по улучшению',
            tags: ['ai', 'ollama', 'gemma4', 'анализ'],
            why: [
                ['🔍', 'Аномалии', (result.anomalies || []).slice(0, 3).map(a => `[${a.severity}] ${a.text}`).join('; ') || 'Нет'],
                ['💡', 'Предложения', (result.suggestions || []).slice(0, 3).map(s => s.text).join('; ') || 'Нет'],
            ],
            metrics: {
                'аномалий': (result.anomalies || []).length,
                'предложений': (result.suggestions || []).length,
                'модель': result.model || 'gemma4:e4b',
            },
            svg: svg,
        };

        state.steps.push(aiStep);
        state.currentIndex = state.steps.length - 1;
        state.placeholders = Math.max(state.placeholders, state.steps.length);
        renderCurrentStep();
        updateProgress();
        updateStepList();
        updateControls();
    } catch (e) {
        alert('Ошибка соединения: ' + e.message);
    }

    btn.disabled = false;
    btn.textContent = '🤖 Анализ ИИ агентов';
    document.getElementById('ai-section').style.display = 'none';
}

/* --- Trajectory Map (Leaflet) --- */

function initTrajectoryMap(data) {
    cleanupMap();
    mapState.data = data;
    mapState.animPos = 0;
    mapState.animPlaying = false;

    const center = data.true_path[Math.floor(data.true_path.length / 2)];
    const map = L.map('trajectory-map', {
        center: [center[0], center[1]],
        zoom: 12,
        zoomControl: true,
        attributionControl: false,
    });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        maxZoom: 19,
    }).addTo(map);
    mapState.instance = map;

    const trueLatLngs = data.true_path.map(p => [p[0], p[1]]);
    const estLatLngs = data.estimates.map(e => [e.lat, e.lon]);
    const filtLatLngs = data.filtered_path.map(p => [p[0], p[1]]);

    const fullTrail = L.polyline(trueLatLngs, {
        color: '#75b798', weight: 2, opacity: 0.4, dashArray: '8 4',
    }).addTo(map);
    mapState.layers.fullTrail = fullTrail;

    const activeLayer = L.layerGroup().addTo(map);
    mapState.layers.activeLayer = activeLayer;

    const estLayer = L.layerGroup().addTo(map);
    mapState.layers.estLayer = estLayer;

    data.estimates.forEach((e, i) => {
        const color = e.quality === 'good' ? '#6ea8fe'
            : e.quality === 'marginal' ? '#ffda6a' : '#ea868f';
        const radius = Math.max(3, Math.min(10, e.correlation * 10));
        const marker = L.circleMarker([e.lat, e.lon], {
            radius, color, fillColor: color, fillOpacity: 0.7, weight: 1,
        });
        marker.bindPopup(`
            <div class="popup-content">
                <div class="popup-row"><span class="popup-label">Корреляция</span> <span class="popup-value">${e.correlation.toFixed(4)}</span></div>
                <div class="popup-row"><span class="popup-label">Высота</span> <span class="popup-value">${e.elevation.toFixed(0)} м</span></div>
                <div class="popup-row"><span class="popup-label">Скорость</span> <span class="popup-value">${e.speed_ms.toFixed(1)} м/с</span></div>
                <div class="popup-row"><span class="popup-label">Азимут</span> <span class="popup-value">${e.azimuth_deg.toFixed(1)}°</span></div>
                <div class="popup-row"><span class="popup-label">Качество</span> <span class="popup-value">${e.quality}</span></div>
                <div class="popup-row"><span class="popup-label">NMEA #</span> <span class="popup-value">${e.nmea_index}</span></div>
            </div>
        `, { className: 'leaflet-popup-dark' });
        marker.addTo(estLayer);
    });

    if (filtLatLngs.length > 1) {
        const filtLine = L.polyline(filtLatLngs, {
            color: '#b580d1', weight: 3, opacity: 0.8,
        }).addTo(map);
        mapState.layers.filtLine = filtLine;
    }

    const errorLines = L.layerGroup().addTo(map);
    mapState.layers.errorLines = errorLines;

    if (data.start) {
        L.circleMarker([data.start.lat, data.start.lon], {
            radius: 8, color: '#75b798', fillColor: '#75b798', fillOpacity: 0.9, weight: 2,
        }).bindPopup('<div class="popup-content"><b>Старт</b></div>', { className: 'leaflet-popup-dark' }).addTo(map);
    }
    if (data.end) {
        L.circleMarker([data.end.lat, data.end.lon], {
            radius: 8, color: '#ea868f', fillColor: '#ea868f', fillOpacity: 0.9, weight: 2,
        }).bindPopup('<div class="popup-content"><b>Финиш</b></div>', { className: 'leaflet-popup-dark' }).addTo(map);
    }

    const legend = L.control({ position: 'bottomleft' });
    legend.onAdd = () => {
        const div = L.DomUtil.create('div', 'map-legend');
        div.innerHTML = `
            <div class="legend-row"><span class="legend-line" style="border-color:#75b798"></span> Истинный путь</div>
            <div class="legend-row"><span class="legend-dot" style="background:#6ea8fe"></span> Оценки TERCOM</div>
            <div class="legend-row"><span class="legend-line" style="border-color:#b580d1"></span> ESKF filtered</div>
            <div class="legend-row"><span class="legend-dot" style="background:#ffda6a"></span> Marginal</div>
            <div class="legend-row"><span class="legend-dot" style="background:#ea868f"></span> Poor</div>`;
        return div;
    };
    legend.addTo(map);

    const slider = document.getElementById('timeline-slider');
    slider.max = data.true_path.length - 1;
    slider.value = 0;
    slider.oninput = function () {
        updateTrajectoryFrame(parseInt(this.value));
    };

    document.getElementById('map-play-btn').onclick = toggleMapAnimation;

    map.fitBounds(fullTrail.getBounds().pad(0.15));
    updateTrajectoryFrame(0);
}

function updateTrajectoryFrame(pos) {
    const data = mapState.data;
    if (!data) return;
    const active = mapState.layers.activeLayer;
    const errorLines = mapState.layers.errorLines;
    active.clearLayers();
    errorLines.clearLayers();

    const trail = data.true_path.slice(0, pos + 1).map(p => [p[0], p[1]]);
    if (trail.length > 1) {
        L.polyline(trail, { color: '#75b798', weight: 3, opacity: 0.9 }).addTo(active);
    }

    const visibleEst = data.estimates.filter(e => e.nmea_index <= pos);
    visibleEst.forEach(e => {
        const color = e.quality === 'good' ? '#6ea8fe'
            : e.quality === 'marginal' ? '#ffda6a' : '#ea868f';
        const radius = Math.max(3, Math.min(10, e.correlation * 10));
        L.circleMarker([e.lat, e.lon], {
            radius, color, fillColor: color, fillOpacity: 0.9, weight: 1,
        }).addTo(active);
    });

    data.estimates.forEach(e => {
        if (e.nmea_index <= pos && pos < data.true_path.length) {
            const truePt = data.true_path[e.nmea_index];
            if (truePt) {
                L.polyline([[truePt[0], truePt[1]], [e.lat, e.lon]], {
                    color: '#ea868f', weight: 1, opacity: 0.4, dashArray: '4 4',
                }).addTo(errorLines);
            }
        }
    });

    if (pos < data.true_path.length) {
        const pt = data.true_path[pos];
        if (pt) {
            if (mapState.droneMarker) mapState.droneMarker.remove();
            mapState.droneMarker = L.circleMarker([pt[0], pt[1]], {
                radius: 6, color: '#fff', fillColor: '#6ea8fe', fillOpacity: 1, weight: 2,
            }).addTo(active);
        }
    }

    const nearEst = data.estimates.filter(e => e.nmea_index <= pos);
    const lastEst = nearEst.length > 0 ? nearEst[nearEst.length - 1] : null;
    const infoEl = document.getElementById('map-params-info');
    if (lastEst) {
        infoEl.innerHTML = `Корр: ${lastEst.correlation.toFixed(3)} | Ск: ${lastEst.speed_ms.toFixed(0)} м/с | Аз: ${lastEst.azimuth_deg.toFixed(0)}° | Выс: ${lastEst.elevation.toFixed(0)} м | Кач: ${lastEst.quality}`;
    } else {
        infoEl.textContent = '—';
    }

    const slider = document.getElementById('timeline-slider');
    if (slider) slider.value = pos;

    document.getElementById('map-pos-info').textContent = `Точка ${pos}/${data.true_path.length - 1}`;
}

function toggleMapAnimation() {
    if (mapState.animPlaying) pauseMapAnimation();
    else playMapAnimation();
}

function playMapAnimation() {
    const data = mapState.data;
    if (!data || data.true_path.length < 2) return;
    if (mapState.animPos >= data.true_path.length - 1) {
        mapState.animPos = 0;
    }
    mapState.animPlaying = true;
    document.getElementById('map-play-btn').textContent = '⏸ Пауза';
    stepMapAnimation();
}

function pauseMapAnimation() {
    mapState.animPlaying = false;
    if (mapState.animTimer) {
        clearTimeout(mapState.animTimer);
        mapState.animTimer = null;
    }
    document.getElementById('map-play-btn').textContent = '▶ Играть';
}

function stepMapAnimation() {
    if (!mapState.animPlaying) return;
    const data = mapState.data;
    if (mapState.animPos >= data.true_path.length - 1) {
        pauseMapAnimation();
        document.getElementById('map-play-btn').textContent = '▶ Играть';
        return;
    }
    mapState.animPos++;
    updateTrajectoryFrame(mapState.animPos);
    const speed = state.speed;
    mapState.animTimer = setTimeout(stepMapAnimation, 200 / speed);
}

function cleanupMap() {
    pauseMapAnimation();
    if (mapState.instance) {
        mapState.instance.remove();
        mapState.instance = null;
    }
    if (mapState.droneMarker) {
        mapState.droneMarker.remove();
        mapState.droneMarker = null;
    }
    mapState.layers = {};
    mapState.data = null;
}

document.addEventListener('DOMContentLoaded', async () => {
    const scenarios = await loadScenarios();
    renderLanding(scenarios);
    document.getElementById('prev-btn').onclick = previousStep;
    document.getElementById('next-btn').onclick = nextStep;
    document.getElementById('play-btn').onclick = togglePlay;
    document.getElementById('return-btn').onclick = returnToLanding;
    document.getElementById('ai-btn').onclick = runAiAnalysis;
    document.querySelectorAll('.speed-btn').forEach(btn => {
        btn.onclick = () => setSpeed(parseInt(btn.dataset.speed));
    });
    document.addEventListener('keydown', (e) => {
        if (document.getElementById('sim-screen').style.display === 'flex') {
            if (e.key === 'ArrowLeft') previousStep();
            else if (e.key === 'ArrowRight') nextStep();
            else if (e.key === ' ') { e.preventDefault(); togglePlay(); }
        }
    });
});

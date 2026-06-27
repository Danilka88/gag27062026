const state = {
    steps: [],
    placeholders: 17,
    currentIndex: -1,
    isPlaying: false,
    isComplete: false,
    speed: 1,
    timer: null,
    scenarioId: null,
    eventSource: null,
};

const SPEEDS = [1, 2, 5, 10];
const BASE_DELAY = 2000;
const STEP_NAMES = [
    "Загрузка DEM", "Fingerprint-ы", "Коридор", "NMEA",
    "Буфер", "Профиль", "Coarse", "Fine",
    "NCC", "Lag", "Агрегирование", "Discrimination",
    "R-матрица", "Траектория", "ESKF",
    "Качество", "Итог",
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
                html += `<div class="phase-label">${currentPhase}</div>`;
            }
            let cls = 'step-entry pending';
            if (i === state.currentIndex) cls = 'step-entry active';
            else if (i < state.currentIndex) cls = 'step-entry done';
            html += `<div class="${cls}" data-idx="${i}" onclick="goToStep(${i})">
                <span class="step-num">${step.number}</span>${step.title.split(' — ')[0]}
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
        <div class="svg-container" id="svg-container">
            ${step.svg}
        </div>
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
        <div class="metrics-grid">
            ${Object.entries(step.metrics || {}).map(([k, v]) => `
                <div class="metric-card">
                    <div class="metric-value">${v}</div>
                    <div class="metric-label">${k.replace(/_/g, ' ')}</div>
                </div>
            `).join('')}
        </div>`;
    const svgEl = document.getElementById('svg-container');
    if (svgEl) svgEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

document.addEventListener('DOMContentLoaded', async () => {
    const scenarios = await loadScenarios();
    renderLanding(scenarios);
    document.getElementById('prev-btn').onclick = previousStep;
    document.getElementById('next-btn').onclick = nextStep;
    document.getElementById('play-btn').onclick = togglePlay;
    document.getElementById('return-btn').onclick = returnToLanding;
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

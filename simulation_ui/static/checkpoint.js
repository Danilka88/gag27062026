let resultData = null;
let cpMap = null;

function enableRunBtn() {
  const dem = document.getElementById('dem-input').files.length;
  const alt = document.getElementById('alt-input').files.length;
  document.getElementById('run-btn').disabled = !(dem && alt);
}

document.getElementById('dem-input').onchange = enableRunBtn;
document.getElementById('alt-input').onchange = enableRunBtn;

async function runCheckpoint() {
  const btn = document.getElementById('run-btn');
  const status = document.getElementById('cp-status');
  btn.disabled = true;
  status.textContent = 'Загрузка и обработка...';

  const fd = new FormData();
  fd.append('dem_file', document.getElementById('dem-input').files[0]);
  fd.append('altitudes_file', document.getElementById('alt-input').files[0]);
  fd.append('start_x', document.getElementById('start-x').value);
  fd.append('start_y', document.getElementById('start-y').value);
  const ct = document.querySelector('input[name="coord-type"]:checked');
  fd.append('coord_type', ct ? ct.value : 'pixel');
  fd.append('freq', document.getElementById('freq').value);
  fd.append('baro_altitude', document.getElementById('baro-altitude').value);
  fd.append('ref_azimuth', document.getElementById('ref-azimuth').value);
  fd.append('ref_speed', document.getElementById('ref-speed').value);

  try {
    const res = await fetch('/api/checkpoint/run', { method: 'POST', body: fd });
    if (!res.ok) {
      const err = await res.json();
      status.textContent = 'Ошибка: ' + (err.detail || res.statusText);
      btn.disabled = false;
      return;
    }
    resultData = await res.json();
    status.textContent = 'Готово';
    showResults(resultData);
  } catch (e) {
    status.textContent = 'Ошибка соединения: ' + e.message;
    btn.disabled = false;
  }
}

function showResults(data) {
  document.getElementById('checkpoint-form').style.display = 'none';
  const results = document.getElementById('checkpoint-results');
  results.style.display = 'block';

  const stats = data.stats || {};
  document.getElementById('cp-stats').textContent =
    `${data.n_estimates} оценок · ø ошибка ${stats.mean_error_m || '—'} м · ` +
    `макс ${stats.max_error_m || '—'} м · ø NCC ${stats.mean_correlation || '—'}`;

  showInformativity(data);
  showAmbiguity(data);
  renderVector(data);
  renderHeatmap(data);
  renderMap(data);
  renderProfileChart(data);
  renderTable(data);
}

function showInformativity(data) {
  const hm = data.heatmap || {};
  const info = hm.informativity_ratio;
  const ts = hm.terrain_std;
  const el = document.getElementById('cp-informativity');
  if (info != null && info < 5) {
    el.innerHTML = `⚠️ Рельеф слабый (SNR ${info.toFixed(1)}×, σ=${ts.toFixed(1)}м) — результаты могут быть ненадёжными`;
    el.className = 'small text-warning-emphasis';
  } else if (info != null) {
    el.innerHTML = `✅ Рельеф достаточен (SNR ${info.toFixed(1)}×, σ=${ts.toFixed(1)}м)`;
    el.className = 'small text-success-emphasis';
  } else {
    el.innerHTML = '';
  }
}

function showAmbiguity(data) {
  const hm = data.heatmap || {};
  const el = document.getElementById('cp-ambiguity');
  if (!el) return;
  if (hm.ambiguous) {
    el.innerHTML = '⚠️ Рельеф неоднозначен — два сильно различающихся азимута имеют близкий NCC';
    el.style.display = 'block';
  } else {
    el.style.display = 'none';
  }
}

function renderVector(data) {
  const az = data.best_azimuth;
  const sp = data.best_speed;
  const hm = data.heatmap || {};
  const ncc = hm.best_correlation;
  const el = document.getElementById('cp-vector-result');
  if (az != null && sp != null) {
    document.getElementById('cp-azimuth-value').textContent = `${az.toFixed(1)}°`;
    document.getElementById('cp-speed-value').textContent = `${sp.toFixed(1)} м/с`;
    document.getElementById('cp-ncc-value').textContent = ncc != null ? ncc.toFixed(4) : '—';
    el.style.display = 'block';
  } else {
    el.style.display = 'none';
  }
}

function renderHeatmap(data) {
  const container = document.getElementById('cp-heatmap');
  const svg = data.heatmap_svg;
  if (svg) {
    container.innerHTML = svg;
  } else {
    container.innerHTML = '';
  }
}

function renderMap(data) {
  const container = document.getElementById('cp-map');
  container.innerHTML = '';

  const segments = data.segments || [];
  const estimates = data.estimates || [];
  if (segments.length === 0) {
    container.innerHTML = '<div class="text-center py-5 text-secondary-emphasis">Нет данных траектории</div>';
    return;
  }

  const truePath = segments.map(s => [s.true_lat, s.true_lon]);
  const center = truePath[Math.floor(truePath.length / 2)];

  cpMap = L.map('cp-map', {
    center: center,
    zoom: 12,
    zoomControl: true,
    attributionControl: false,
  });
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
  }).addTo(cpMap);

  const trueLine = L.polyline(truePath, {
    color: '#dee2e6', weight: 2, opacity: 0.5, dashArray: '8 4',
  }).addTo(cpMap);

  const estLayer = L.layerGroup().addTo(cpMap);

  function getColor(q) {
    if (q === 'good') return '#75b798';
    if (q === 'marginal') return '#ffda6a';
    return '#ea868f';
  }

  estimates.forEach(est => {
    const color = getColor(est.quality);
    const radius = Math.max(3, Math.min(10, (est.correlation || 0) * 10));
    const marker = L.circleMarker([est.est_lat, est.est_lon], {
      radius, color, fillColor: color, fillOpacity: 0.8, weight: 1,
    });
    const p2v = est.peak_to_valley != null ? `${est.peak_to_valley} м` : '—';
    const discr = est.discrimination_ratio != null ? est.discrimination_ratio.toFixed(2) : '—';
    const tstd = est.terrain_std != null ? `${est.terrain_std.toFixed(1)} м` : '—';
    marker.bindPopup(`
      <div style="font-family:monospace;font-size:12px">
        <div>Шаг ${est.step}</div>
        <div>Ошибка: ${est.error_m} м</div>
        <div>NCC: ${est.correlation} · P2V: ${p2v} · σ: ${tstd}</div>
        <div>Discr: ${discr} · Качество: ${est.quality}</div>
        <div>true: ${est.true_lat}, ${est.true_lon}</div>
        <div>est:  ${est.est_lat}, ${est.est_lon}</div>
      </div>
    `, { className: 'leaflet-popup-dark' });
    marker.addTo(estLayer);
  });

  L.circleMarker([data.start_lat, data.start_lon], {
    radius: 8, color: '#75b798', fillColor: '#75b798', fillOpacity: 0.9, weight: 2,
  }).bindPopup('<b>Старт</b>', { className: 'leaflet-popup-dark' }).addTo(cpMap);

  if (segments.length > 0) {
    const last = segments[segments.length - 1];
    L.circleMarker([last.true_lat, last.true_lon], {
      radius: 8, color: '#ea868f', fillColor: '#ea868f', fillOpacity: 0.9, weight: 2,
    }).bindPopup('<b>Финиш</b>', { className: 'leaflet-popup-dark' }).addTo(cpMap);
  }

  cpMap.fitBounds(trueLine.getBounds().pad(0.15));
}

function renderProfileChart(data) {
  const container = document.getElementById('cp-profile-chart');
  const svg = data.profile_svg;
  if (svg) {
    container.innerHTML = svg;
  } else {
    container.innerHTML = '';
  }
}

function renderTable(data) {
  const estimates = data.estimates || [];
  const thead = document.getElementById('cp-table-head');
  const tbody = document.getElementById('cp-table-body');

  const cols = ['step', 'error_m', 'correlation', 'quality', 'discrimination_ratio',
                'peak_to_valley', 'terrain_std', 'confidence',
                'true_lat', 'true_lon', 'est_lat', 'est_lon',
                'true_row', 'true_col', 'est_row', 'est_col'];
  const labels = ['Шаг', 'Ошибка (м)', 'NCC', 'Качество', 'Discr',
                  'P2V (м)', 'σ terrain', 'Conf',
                  'true lat', 'true lon', 'est lat', 'est lon',
                  'true row', 'true col', 'est row', 'est col'];

  thead.innerHTML = labels.map(l => `<th>${l}</th>`).join('');

  function fmt(val, decimals) {
    if (val == null) return '—';
    return typeof val === 'number' ? val.toFixed(decimals) : val;
  }

  function qualHtml(q) {
    if (q === 'good') return '<span class="text-success-emphasis fw-bold">🟢 good</span>';
    if (q === 'marginal') return '<span class="text-warning-emphasis fw-bold">🟡 marginal</span>';
    return '<span class="text-danger-emphasis fw-bold">🔴 poor</span>';
  }

  tbody.innerHTML = estimates.map(est =>
    '<tr>' + [
      est.step,
      fmt(est.error_m, 2),
      fmt(est.correlation, 4),
      qualHtml(est.quality),
      fmt(est.discrimination_ratio, 2),
      fmt(est.peak_to_valley, 1),
      fmt(est.terrain_std, 2),
      fmt(est.confidence, 3),
      fmt(est.true_lat, 6),
      fmt(est.true_lon, 6),
      fmt(est.est_lat, 6),
      fmt(est.est_lon, 6),
      fmt(est.true_row, 2),
      fmt(est.true_col, 2),
      fmt(est.est_row, 2),
      fmt(est.est_col, 2),
    ].map(v => `<td>${v}</td>`).join('') + '</tr>'
  ).join('');
}

function downloadCSV() {
  if (!resultData || !resultData.estimates) return;
  const estimates = resultData.estimates;
  const cols = ['step', 'error_m', 'correlation', 'quality', 'discrimination_ratio',
                'peak_to_valley', 'terrain_std', 'confidence',
                'true_lat', 'true_lon', 'est_lat', 'est_lon',
                'true_row', 'true_col', 'est_row', 'est_col'];
  let csv = cols.join(',') + '\n';
  estimates.forEach(est => {
    csv += cols.map(c => est[c] != null ? est[c] : '').join(',') + '\n';
  });
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'trajectory.csv';
  a.click();
  URL.revokeObjectURL(url);
}

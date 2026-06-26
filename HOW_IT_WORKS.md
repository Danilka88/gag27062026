# How It Works — Gagarin

> Краткое объяснение каждого компонента: почему работает,
> физический/математический принцип, поведение при запуске.

---

## 0. Pre-processing — подготовка до полёта (preprocess.py)

**Что это:** Наземная (ground station) система оценки маршрута до вылета.
Загружает waypoints, DEM и ожидаемые курс/скорость → fingerprint-база данных
в SQLite с R-Tree spatial index + GeoTIFF информационной карты.

**Компоненты:**
- `TerrainAnalyzer` — gradient magnitude, std_window (7×7), Laplacian, `info_map()`
- `MissionPreprocessor` — строит reference profiles вдоль интерполированного
  маршрута, для каждой точки считает NCC при смещении ±1..15 grid cells,
  Minima Ratio (Akinci 2026), roughness difference
- `FINGERPRINT_OFFSETS_CELLS = [1, 2, 3, 5, 10, 15]` — набор смещений для оценки
  уникальности профиля

**Адаптивный коридор:**
```
width = max(2 × ins_drift_rate × segment_length + 2 × dem_resolution, 500 м)
```
На 10 км сегменте с consumer INS → ~2 км (в 5× уже фиксированного 10–15 км).

**Почему работает:** TERCOM на плоском рельефе даёт false fixes. Если знать
заранее, какие участки маршрута информативны (Minima Ratio > 0.8), можно
адаптировать доверие к оценкам в полёте.

**CLI:** `gagarin prepare-route --waypoints file.csv -d dem.tif -o mission_pkg`
→ `gagarin viz-mission mission_pkg` (3-панельный HTML viewer).

---

## 1. DEM — Цифровая Модель Рельефа

**Что это:** Карта высот (широта, долгота → высота над уровнем моря). Хранится как
GeoTIFF-растр 400×400. Два типа:
- **Synthetic** (σ=95 м, перепад 101–600 м) — для разработки
- **Dramatic** (σ=687 м, перепад 10–3489 м) — горный рельеф, нагляднее

Загрузкой управляет `DEMLoader`, внутри:
- `CoordinateTransformer` — пересчёт (lat,lon) → (row,col) через pyproj
- `DEMInterpolator` — билинейная интерполяция по 4 ближайшим пикселям

**Почему работает:** Рельеф — уникальный «отпечаток пальца» местности. Если пролететь
над одним и тем же участком, профиль высот будет одинаковым. Terra incognita → нет
опорной карты → TERCOM не работает.

**При запуске:** Загружается в память целиком (1.3 MB synthetic, ~1.3 MB dramatic).
Билинейная интерполяция читает высоту в любой точке (не только в узлах сетки).

---

## 2. NMEA — Протокол Радиовысотомера

**Что это:** Текстовые строки `$GPGGA` с полями `timestamp` и `altitude` (высота
над эллипсоидом). Генерируются симулированным полётом (`DataGenerator`) или
поступают от реального датчика.

**Почему работает:** Радиовысотомер измеряет расстояние до земли. Разница между
барометрической высотой (опора) и радиовысотой = высота рельефа под БПЛА.
```
terrain_height = baro_altitude - radar_altitude
```

**При запуске:** Парсятся через `NMEAParser` (обёртка над pynmea2), фильтруются
только `$GPGGA`. Каждое сообщение → `NMEAReading(timestamp, altitude)`.
Складываются в `NMEABuffer` — скользящее окно (deque) на 200 отсчётов.

---

## 3. Извлечение Профиля (profile.py + buffer.py)

**Что это:** Преобразование барометрической и радиовысоты в профиль рельефа.
`profile.py` содержит валидацию профиля (std, качество, проверка на NaN).
`NMEABuffer` управляет накоплением 200 отсчётов в скользящем окне (deque):
- `add(reading)` — добавить отсчёт, вытеснить старый при переполнении
- `is_full()` — набрано ли 200 точек
- `get_profile()` — baro_altitude − altitudes → terrain profile (использует `config.baro_altitude`, без дублирования константы)
- `advance_distance(speed)` — адаптивная дистанция (пропуск, если мало пролетели)

**Почему работает:** 20 секунд полёта × 10 Hz = 200 точек. Этого достаточно,
чтобы профиль стал уникальным (пересечь 2-3 холма/оврага). Слишком мало (<50) —
шум доминирует. Слишком много (1000+) — рельеф меняется, окно устаревает.

**При запуске:** Первые 20 секунд — накопление (нет оценок). После заполнения —
скользящее окно (FIFO). Каждый новый отсчёт вытесняет самый старый.

---

## 4. TERCOM — Terrain Contour Matching (correlator.py)

**Что это:** Поиск азимута и скорости, при которых эталонный профиль из DEM
максимально похож на измеренный.

Компоненты:
- `CorrelationMetrics` — статические методы: `ncc()`, `cross_correlation()`, `compute_confidence()`
- `HypothesisSearch` — coarse-to-fine поиск по сетке азимутов и скоростей
- `TERCOMCorrelator` — оркестратор: проверка roughness → coarse → fine → MatchResult

**Почему работает:** Если БПЛА летит с азимутом A и скоростью V, то его
траектория за 20 секунд — это последовательность точек `start + step×dt`
в направлении A. Из DEM читаются высоты в этих точках → эталонный профиль.
Чем ближе A и V к истинным, тем больше эталон похож на измерение.

**Математика:** Normalized Cross-Correlation
```
NCC = Σ((x - μx)(y - μy)) / √(Σ(x - μx)² · Σ(y - μy)²)
```
Результат в [-1, 1]. 1 = идеальное совпадение, 0 = случайный шум, < 0 = антикорреляция.

**При запуске:**
1. **Roughness check:** если std профиля < 3 м — рельеф слишком плоский, пропуск
2. **Coarse:** 36 азимутов × 10 скоростей = 360 гипотез (~0.3 с)
3. **Top-5:** берём 5 лучших по NCC
4. **Fine:** вокруг каждой — локальный поиск ±6°, ±`fine_speed_margin` (дефолт 15 м/с, из `config.py`) с шагом 0.5° → ~1500
5. **Lag:** `np.correlate()` даёт сдвиг (лаг) между профилями — поправка позиции.
   **Anti-correlation fix:** `np.abs()` убран из `np.argmax` — отрицательная корреляция (анти-совпадение) больше не считается валидным лагом

**Сложность:** ~360 гипотез coarse + ~1500 fine ≈ 60 ms на MacBook M4.
На Raspberry Pi ожидается ~0.5–1 с (нужна оптимизация через numba JIT).

---

## 5. Velocity Estimation + Dead Reckoning (estimator.py + pipeline.py)

**Что это:** Преобразование `MatchResult` в `NavigationEstimate` (dataclass с полями
`azimuth_deg`, `speed_ms`, `position_lat`, `position_lon`, `correlation`, `confidence`
и др.) + перемещение центра поиска для следующего окна.

**VelocityEstimator.estimate(match, center):**
- Берёт `match.azimuth_deg`, `match.speed_ms`
- Вычисляет lag_distance = lag_samples × speed × dt
- Применяет lag как поправку к координатам через `offset_coords`
- Возвращает `NavigationEstimate`

**Dead reckoning:** Если не двигать центр, каждое новое окно будет искать в одной
точке → бессмысленно. Центр двигается на `speed × dt` + lag поправка:
```
center_new = center_old + speed·dt·[cos(α), sin(α)]/R + lag·[cos(α), sin(α)]/R
  └─ dead reckoning ─┘         └─ lag correction ──┘
```

**При запуске:** Условно правильные первые 5–10 оценок → центр смещается в сторону
истины. Ошибка в оценке → центр смещается не туда → следующая оценка ищет в
неверном месте → ошибка растёт. Это **главная причина дрейфа**.

**Fallback при сбое:** Если TERCOM вернул `match = None` (плоский рельеф,
шум датчика), pipeline больше не «зависает» — ESKF делает predict,
а `_dead_reckon_forward()` сдвигает центр поиска по последней оценке
(или `config.default_azimuth/speed`). Это предотвращает каскадный сбой
при пролёте над озером или равниной.

**geo_utils.py** — формулы движения по сфере: `offset_coords` и `offset_coords_batch`
(векторизованная версия). Используют `EARTH_RADIUS = 6371 км`.

---

## 6. ESKF — Error-State Kalman Filter (eskf.py)

**Что это:** Сглаживатель оценок. 6D-фильтр ошибок: `[δlat, δlon, δvx, δvy, bx, by]`.

**Почему работает:** TERCOM — шумный датчик. Одиночная оценка может быть выбросом.
ESKF усредняет историю: если TERCOM резко прыгнул — фильтр сглаживает, если
систематически уходит — фильтр отслеживает.

```
predict:  δ ← F·δ + Q        (ошибка растёт, covariance увеличивается)
update:   δ ← δ + K·(z - H·δ) (TERCOM-измерение корректирует ошибку)
reset:    x ← x + δ           (инжектируем ошибку в состояние, δ → 0)
```

Важно: `np.linalg.solve` вместо `np.linalg.inv` для численной устойчивости.
Degree bug fix: входные lat/lon уже в градусах — `np.degrees()` убран.

**При запуске:** `predict` → `update_position` → `update_velocity` → `reset`.
Результат TERCOM → отфильтрованное состояние. Если `kalman_enabled=True`,
позиция из фильтра замещает `center_lat/lon`.

---

## 7. Оценка Качества (quality.py)

**Что это:** Классификация каждого match: good / marginal / poor.

**Почему работает:** Три эвристики:
- `peak_sharpness` — насколько пик NCC выше среднего шума
- `discrimination_ratio` — насколько aligned < misaligned
- Пороговый confidence → good (>0.6) / marginal (0.3-0.6) / poor (<0.3)

**При запуске:** `assess_match(match)` → dict с quality/confidence/пиками.
Записывается в `estimate.quality` (dataclass).
На synthetic DEM confidence ≈ 0.11 (все poor). На dramatic DEM confidence выше
(σ рельефа больше → профиль уникальнее).

---

## 8. Визуализация (viz/)

**Графики после полёта (dashboard):**
- **correlation_heatmap** — матрица 36×10, яркая точка = best match
- **trajectory_map** — красный трек (true) на DEM contours, зелёный (estimated)
- **profile_comparison** — синяя линия (измерено) vs оранжевая (эталон)
- **navigation_dashboard** — 5 карточек: 3D terrain + profile + timeline + error + heatmap (русские подписи)
- **unified_dashboard** (`--compare`) — Synthetic vs Dramatic на одном экране, табы переключают трейсы

**Pre-flight viewer (mission_viewer):**
- **Карта маршрута** — info heatmap (gradient + std) + scatter по Minima Ratio
- **Профиль информативности** — std высот + gradient + Minima Ratio вдоль трека
- **Fingerprint-матрица** — NCC при смещении от трека (риск false fix)

Навигация: на dashboard есть ссылка на mission viewer и обратно (nav-links в шапке).
Общие константы (цвета, template) в `viz/utils.py`. Конкретные графики — в `viz/components.py` (фабрики trace-ов).

**При запуске:** Генерируются после завершения обработки всех NMEA строк.
HTML-файлы 1-5 MB каждый — открываются в любом браузере, zoom/pan/hover.

---

## Полный цикл "одной итерации"

```
NMEA строка
    ↓
NMEAParser.parse() → NMEAReading(t, alt)
    ↓
NMEABuffer.add(reading) ← 200 точек? (is_full)
    ↓ (да)
NMEABuffer.get_profile() → terrain profile [h₀, ..., h₁₉₉]
    ↓
TERCOMCorrelator.search(profile, center_lat, center_lon)
    ├── terrain_std < threshold? → None (пропуск)
    ├── HypothesisSearch.coarse_search() → 360 гипотез
    ├── HypothesisSearch.fine_search() → top-5 → ~1500 гипотез
    ├── CorrelationMetrics.cross_correlation() → lag
    └── MatchResult(az, sp, corr, lag, confidence, profiles)
    ↓
VelocityEstimator.estimate(match, center)
    → NavigationEstimate(azimuth, speed, position, correlation, confidence, ...)
    ↓
_update_center(): dead reckoning + lag correction
    ↓
_apply_kalman(): predict → update → reset → filtered state
    ↓
assess_match(match) → quality dict
    ↓
estimate.quality = quality
estimate.timestamp = t
    ↓
возвращаем NavigationEstimate → main.py печатает строку
```

**До полёта (ground station):**
```
Waypoints CSV → MissionPreprocessor → fingerprints + info_map → SQLite + GeoTIFF package
    → gagarin viz-mission → mission_viewer.html (3 панели: карта, профиль, fingerprint-матрица)
```

**После полёта (post-flight analysis):**
```
gagarin run --compare → unified dashboard.html (Synthetic vs Dramatic, 5 карточек, табы, nav-link на mission_viewer.html)
```

Всё повторяется каждые 0.1 секунды (10 Hz), пока не кончатся NMEA строки.
На MacBook M4: ~60 ms на одну корреляцию, 231 estimate за 300 с полёта за 14 с обработки.

# План развития Gagarin — TERCOM Navigation

На основе анализа кода и исследований 2024–2026.

---

## 1. Слабые места текущего алгоритма

### Критические

| Проблема | Где | Что происходит |
|----------|-----|----------------|
| Нет dead reckoning при сбое корреляции | `pipeline.py:75-77` | Если TERCOM вернул None, позиция не обновляется вовсе. Дрон «зависает» в координатах, пока летит дальше. |
| Одиночная плохая оценка убивает все следующие | `pipeline.py:106-126` | Центр поиска смещается на основе ошибочной оценки → все следующие reference profile строятся от wrong места → каскадный сбой. |
| Anti-correlation считается валидным совпадением | `correlator.py:188` | `np.argmax(np.abs(corr))` выбирает и сильную отрицательную корреляцию — физически бессмысленно. |
| Fine search margin может не покрыть coarse grid | `correlator.py:129-137` | При coarse шаге 10° margin=6° едва перекрывает 5° полушаг. Для скорости margin ±15 м/с меньше coarse шага ~15.6 м/с. |
| Векторизация не используется | `correlator.py:94-100` | ~960 profile builds на оценку, каждый через Python loop. Нет batch-построения reference profiles. |

### Высокие

- **Нет multi-hypothesis tracking** — используется только best match, без particle filter или ветвления
- **Скорость измерения не независима от позиции** (`pipeline.py:112-115`) — velocity measurement берётся из того же correlation, что и позиция → ESKF covariance занижена
- **Null Island при старте вне DEM** (`pipeline.py:48-52`) — нет валидации начальных координат
- **Flat terrain → no estimates** (`correlator.py:160-162`) — порог 3м std отсекает все гипотезы на равнине
- **Константа _DEFAULT_BARO продублирована** в `config.py` и `profile.py`
- **confidence_threshold задан, но нигде не используется**
- **NCC для визуализации пересчитывается заново** (`main.py:279-318`) — дублирование pipeline расчётов

### Средние

- Нет Covariance clamping в ESKF — P может расти бесконечно
- Lag-коррекция зависит от оценённой скорости (циклическая зависимость)
- NMEA симуляция не содержит lat/lon (нельзя тестировать real pipeline)
- Нет INS drift simulation в data_generator
- DEM граница — клиппинг координат даёт ложные плоские профили
- NaN в DEM не обрабатывается
- Нет пересечения международной линии смены дат

---

## 2. Pre-processing до полёта (если маршрут известен)

Текущий алгоритм ничего не знает о маршруте до старта. Исследования 2024–2026 показывают, что **предварительная подготовка данных** — один из самых эффективных способов улучшить TERCOM без увеличения бортовых вычислений.

### 2.1 Информационная карта местности (Terrain Information Map)

**Идея:** До полёта рассчитать для каждого участка DEM метрику «насколько здесь хорошо работать TERCOMу». Загрузить на дрон как GeoTIFF + быстрый lookup.

**Что считается:**
- Вариативность рельефа (std elevation в окне)
- Gradient magnitude (крутизна склонов)
- Градиент градиента (вторые производные — гребни, каньоны)
- Ожидаемая Cramér–Rao lower bound (CRLB) — теоретическая минимальная ошибка позиционирования

**Источник:** Martin Gelin, «Terrain Referenced Navigation with Path Optimization» (2022) — gradient magnitude как мера информативности. Также SPRIN-D Funke Challenge (2025) — фильтрация слабых градиентов (<5 м) для template matching.

**Как поможет:** Дрон в полёте знает: «сейчас я над информативным рельефом — можно доверять TERCOMу» или «сейчас равнина — лучше полагаться на INS и не обновлять позицию». Это решает проблему false fixes на flat terrain.

### 2.2 Предрасчёт correlation fingerprint для маршрута

**Идея:** Зная приблизительный маршрут (lat/lon + истинный курс), до полёта построить вдоль трека ожидаемые reference profiles + пороговые correlation значения.

**Что делается:**
- Пройти по всем точкам маршрута, для каждой построить reference profile
- Рассчитать expected NCC при правильном положении (сам с собой) и при смещениях ±1, ±2, ±3 grid cells
- Сохранить как компактный fingerprint (SQLite с spatial index)

**Источник:** Istanbul Technical University / Akinci (2026) — «A Statistical Framework for False-Fix Elimination in TERCOM». 780 trajectory fingerprints, 45 features, Minima Ratio как лучший детектор false fix. github.com/hstm/terrain-nav-preprocessing — SQLite tiles с ORB features + NetVLAD descriptors.

### 2.3 Траекторная оптимизация (Path Planning for TRN)

**Идея:** Если маршрут задан коридором (not fixed waypoints), можно выбрать путь через наиболее информативный рельеф.

**Метод:**
- Построить cost map: `gradient_magnitude DEM`
- A* на hidden layer поверх cost map
- Выбрать путь, максимизирующий cumulative information gain

**Источник:** Martin Gelin (2022) — A* поверх gradient map даёт измеримое улучшение accuracy TRN. Актуально для AUV (Wang et al., 2023) и UAV (SPRIN-D, 2025).

### 2.4 Multi-resolution DEM pyramid

**Идея:** Загрузить DEM в нескольких разрешениях. На этапе coarse search использовать low-res (быстро), на fine — high-res (точно).

**Дополнительно:** Сжатие DEM через DCT (SITAN, Fellerhoff 1987) или tile-based SQLite (hstm/terrain-nav-preprocessing).

### 2.5 Precomputed coarse NCC matrix вдоль маршрута

**Идея:** До полёта рассчитать для каждой точки ожидаемый coarse correlation landscape. В полёте делать только fine search вокруг предрасчитанного best estimate.

**Ограничения:** Чувствителен к отклонению от планового маршрута. Можно использовать как fallback — если onboard coarse search даёт подозрительный результат, сравнить с precomputed fingerprint.

---

## 3. Новые научные направления (2025–2026)

### 3.1 Deep Learning Feature Matching вместо NCC

**TERCOM с neural network:** 2026, Beijing University — wavelet transform + CNN для contour feature matching. Matching success rate >30% выше NCC, время сокращено на 97%.

**Autoencoder + Contrastive Learning:** 2026, GL-DualNet (CNN + Swin Transformer) — self-supervised terrain features, устойчивые к шуму и поворотам. Mean localization error 1.09 grid cells vs TERCOM ~3-5.

**Как применить в Gagarin:** Заменить NCC на lightweight CNN. Сохранить coarse-to-fine архитектуру, но вместо NCC использовать deep feature distance. Проверить на Raspberry Pi — цель <100 ms/search.

### 3.2 Particle Filter вместо single hypothesis

**Fuzzy Particle Filter (FPF):** Yousuf & Kadri, 2025 — двухстадийный FPF + ESKF. Адаптивное число частиц через fuzzy logic. Выше точность, меньше compute чем классический PF.

**Тренд 2025–2026:** Particle filter доминирует в современных TRN системах:
- BCPS-PF (2025): batch cyclic posterior selection PF — >10% improvement
- SWA-PF (2025): semantic-weighted adaptive PF — 10× efficiency, <10m error
- BEV-Patch-PF (2025): particle filter + aerial feature matching — 7× lower ATE

**Как применить:** Заменить single hypothesis search на particle filter (50–200 частиц). Каждая частица = гипотеза (lat, lon, heading, speed). Вес = NCC. Resampling по weights. Многочастичный подход решает проблему каскадного сбоя.

### 3.3 AI Supervisor для переключения режимов

**AI-enhanced TAN:** Hürjet (Turkish Aerospace, 2026) — AI supervisor переключает между EKF/UKF/PF в зависимости от terrain roughness. Accuracy ~82% выбора правильного фильтра.

**Применение:** Добавить supervisor (lightweight decision tree или MLP) на входе в pipeline. По terrain roughness и confidence выбирает: TERCOM batch vs SITAN recursive vs pure dead reckoning.

### 3.4 Vision-based cross-view localization

**NaviLoc (2026):** Траекторный VPR + VIO — 19.5 m MLE на Raspberry Pi 5 (9 FPS). Украинский benchmark.

**CVPR 2026 — Bearing-UAV:** Pure vision navigation — joint prediction location + heading. Lower localization error than retrieval paradigms.

**Применение:** Добавить optical camera как secondary sensor. Image → feature → cross-view matching → position estimate. Fusion с TERCOM через ESKF.

### 3.5 Multi-sensor fusion framework

**SAR altimeter + DDM:** Remote Sensing 2026 — XGBoost + Bayesian particle filter для SAR altimeter. 3D localization under wide beam.

**VLM-Nav (2026):** DepthAnything-V2 + GPT-4o/Gemini — obstacle avoidance без карт. Task completion 0.98.

**Применение:** Добавить IMU (6 DOF + biases) в ESKF. 15-state ESKF как в mzahana/tercom_nav (ROS 2). Это даст полноценную INS+TERCOM интеграцию.

---

## 4. План развития (Roadmap)

### Фаза 1 — Фиксация критических багов ✅

- [x] anti-correlation fix: `np.abs()` → `np.max(corr)` в lag detection (`correlator.py:188`)
- [x] Dead reckoning fallback при `correlation = None` (ESKF predict + `_dead_reckon_forward()`) (`pipeline.py`)
- [x] Валидация начальных координат (ValueError если lat/lon вне DEM) (`pipeline.py:initialize()`)
- [x] `_DEFAULT_BARO` — удалён дубль из `profile.py`, значение из `config`
- [x] Fine speed margin (15.0) вынесен в config (`fine_speed_margin: float = 15.0` + валидация >0)

### Фаза 2 — Pre-processing система ✅ (основной функционал)

- [x] Модуль pre-flight подготовки (`gagarin/preprocess.py`):
  - [x] Terrain Information Map (std, gradient, Laplacian, info_map)
  - [x] SQLite database с R-Tree spatial index + GeoTIFF info_map упаковка
  - [x] CLI команда `gagarin prepare-route --waypoints file.csv`
- [x] Интеграция: Mission viewer (`gagarin viz-mission`) — 3-панельный HTML (карта + профиль + fingerprint матрица) с nav-link на dashboard
- [ ] Multi-resolution DEM pyramid (low-res coarse, high-res fine)
- [ ] Onboard adaptive search resolution (lookup mission package в полёте)

### Фаза 3 — Particle Filter (3–4 недели)

- [ ] ParticleFilter class:
  - [ ] 100–200 particles (lat, lon, heading, speed)
  - [ ] Weight = NCC(observed, reference for particle)
  - [ ] Systematic resampling
  - [ ] Adaptive particle count (по terrain roughness)
- [ ] Замена single hypothesis search на PF
- [ ] В качестве fallback — TERCOM batch acquisition

### Фаза 4 — Performance (2–3 недели)

- [ ] Numba JIT на hot path:
  - [ ] `build_reference_profile` — @jit(nopython=True)
  - [ ] `CorrelationMetrics.ncc` — @jit
  - [ ] Batch elevation interpolation
- [ ] Векторизованное построение reference profiles (3D array: hypotheses × window_size)
- [ ] Цель: <50 ms/search на RPi 5

### Фаза 5 — Deep Learning (4–6 недель)

- [ ] Lightweight terrain feature extractor (CNN или small ViT)
- [ ] Self-supervised pre-training (DEM patches → contrastive learning)
- [ ] Замена NCC на feature distance в fine search
- [ ] Offline: train на synthetic + real DEM patches
- [ ] ONNX export → inference on RPi

### Фаза 6 — Multi-sensor ESKF (2–3 недели)

- [ ] Расширение ESKF до 15-state:
  - [ ] position (3), velocity (3), attitude (3), accel bias (3), gyro bias (3)
  - [ ] IMU-driven prediction
  - [ ] Joseph-form update
- [ ] INS drift simulation в data_generator
- [ ] Sensor fusion: TERCOM + baro + IMU + (opt) camera

### Фаза 7 — Опционально (по необходимости)

- [ ] AI Supervisor для выбора режима (TERCOM / PF / SITAN)
- [ ] Vision-based cross-view localization (downward camera → satellite)
- [ ] SAR altimeter support (DDM + XGBoost)
- [ ] Copernicus GLO-30 реальный DEM download fix

---

## 5. Источники и доказательная база

| Направление | Источник | Год |
|------------|----------|-----|
| False fix elimination (Minima Ratio, DTW, MAD) | Akinci, Istanbul Technical Univ. | 2026 |
| Deep learning TERCOM (CNN + wavelet) | Li et al., Beijing Univ. | 2026 |
| Autoencoder + contrastive learning for TAN | Drones journal | 2026 |
| AI supervisor (EKF/UKF/PF switching) | Hürjet, Turkish Aerospace | 2026 |
| Fuzzy Particle Filter + ESKF for TAN | Yousuf & Kadri | 2025 |
| Particle filter variants (BCPS-PF, SWA-PF) | MDPI Electronics | 2025 |
| Path planning for TRN (A* + gradient map) | Gelin, Linköping Univ. | 2022 |
| SPRIN-D Challenge (heightmap gradient matching) | arXiv 2510.01348 | 2025 |
| NaviLoc (trajectory VPR + VIO on RPi 5) | MDPI Drones | 2026 |
| Bearing-UAV (CVPR 2026 cross-view nav) | Liu et al., CVPR | 2026 |
| ROS 2 TERCOM + ESKF (reference impl) | mzahana/tercom_nav | 2026 |
| Terrain nav preprocessing toolkit | hstm/terrain-nav-preprocessing | 2025 |
| SITAN + TERCOM hybrid (CSITAN+WRIT) | Li et al., NAVIGATION journal | 2017 |

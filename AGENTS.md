# AGENTS.md — Gagarin

Технический контекст для будущих агентов / сессий.

## Архитектура

```
                    ┌──────────────┐
                    │ simulation_ui│ ← FastAPI SSE (14-step TERCOM demo)
                    │ /main.py     │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │pipeline  │ │ DataGen  │ │ SVG Gen  │
        │.py       │ │ .py     │ │ .py      │
        └────┬─────┘ └──────────┘ └──────────┘
             │
    ┌───────┼──────┬──────┬──────┬────┐
    ▼       ▼      ▼      ▼      ▼    ▼
┌──────┐ ┌────┐ ┌────┐ ┌────┐ ┌──┐ ┌──┐
│buffer│ │cor-│ │est-│ │dem │ │geo│ │qu│
│.py   │ │rel-│ │ima-│ │loa-│ │_u-│ │al│
│NMEABu│ │ator│ │tor │ │der │ │til│ │it│
│ffer  │ │.py │ │.py │ │.py │ │s  │ │y.│
│deque  │ │TER-│ │Velo│ │DEM │ │.py│ │py│
│adapt. │ │COM │ │cit │ │Lo- │ │   │ │  │
│dist.  │ │Cor-│ │yEs│ │ader│ │   │ │  │
│       │ │r-  │ │tim-│ │Co- │ │   │ │  │
│       │ │ela-│ │ator│ │ord │ │   │ │  │
│       │ │tor │ │Nav-│ │Tra-│ │   │ │  │
│       │ │Hyp-│ │iga-│ │nsf │ │   │ │  │
│       │ │oth-│ │tion│ │DEM-│ │   │ │  │
│       │ │esis│ │Est-│ │Int-│ │   │ │  │
│       │ │Sea-│ │ima-│ │erp-│ │   │ │  │
│       │ │rch │ │te  │ │ola-│ │   │ │  │
│       │ │Cor-│ │   │ │tor │ │   │ │  │
│       │ │rel-│ │   │ │    │ │   │ │  │
│       │ │atio│ │   │ │    │ │   │ │  │
│       │ │n Me│ │   │ │    │ │   │ │  │
│       │ │tric│ │   │ │    │ │   │ │  │
│       │ │s   │ │   │ │    │ │   │ │  │
└───────┘ └────┘ └───┘ └────┘ └───┘ └──┘
    ┌───────┐ ┌────────┐ ┌──────────┐
    │eskf  │ │config  │ │nmea_    │
    │.py   │ │ validate│ │parser   │
    │State │ │+ merger│ │.py      │
    │Error │ │        │ │pynmea2  │
    │Kalman│ │        │ │wrapper  │
    │Filter│ │        │ │         │
    └──────┘ └────────┘ └─────────┘
```

CLI (`cli.py`: `prepare-route`, `viz-mission`, `generate-dem`, `download-dem`, `analyze`) is a separate entry point — utilities that don't need the simulation UI.
```

## Модули

| Модуль | Файл | Ключевые классы/функции | Назначение |
|--------|------|--------------------------|------------|
| **config** | `config.py` | `Config`, `merge()`, `validate()`, `_DEFAULT_BARO` | Все тюнябельные параметры в одном месте. `validate()`: assert→ValueError. `merge()`: warns on unknown keys. |
| **nmea_parser** | `nmea_parser.py` | `NMEAParser`, `NMEAReading` | Обёртка над pynmea2. Парсит `$GPGGA`. Возвращает dataclass. |
| **buffer** | `buffer.py` | `NMEABuffer` | Скользящее окно (deque maxlen=window_size). `add()`, `is_full()`, `get_profile()`, `advance_distance()`. Адаптивная дистанция. |
| **dem_loader** | `dem_loader.py` | `DEMLoader`, `CoordinateTransformer`, `DEMInterpolator` | Загрузка GeoTIFF. Трансформация CRS. Билинейная интерполяция. |
| **correlator** | `correlator.py` | `TERCOMCorrelator`, `HypothesisSearch`, `CorrelationMetrics`, `MatchResult` | Поиск азимута/скорости. NCC. Coarse→fine. Cross-correlation lag. |
| **estimator** | `estimator.py` | `VelocityEstimator`, `NavigationEstimate` | Преобразование Match→NavigationEstimate. Dead reckoning central shift. |
| **geo_utils** | `geo_utils.py` | `offset_coords()`, `offset_coords_batch()` | Формулы движения по сфере. Batch-версия для векторизации. |
| **quality** | `quality.py` | `_assess()` (private) | Классификация good/marginal/poor + confidence. |
| **eskf** | `eskf.py` | `ErrorStateKalmanFilter` | 6D-фильтр. solve vs inv. Degree bug fixed. |
| **pipeline** | `pipeline.py` | `NavigationPipeline` | Оркестратор: буфер→корреляция→оценка→dead reckoning→ESKF. |
| **viz/mission** | `viz/mission.py` | `mission_viewer()` | 3-панельный HTML-вьювер для pre-flight mission package: карта, профиль информативности, fingerprint-матрица. |
| **checkpoint** | `checkpoint.py` | `CheckpointResult`, `WindowEstimate`, `run_tercom()`, `_mad()` (mean‑sub), `_search_position_grid()` (5-tuple), `_search_speed()`, `_process_windows()` (4 gates), `_azimuth_consensus()`, `_ransac_filter()`, `_ncc_adaptive()`, `_classify_quality()` (+mad), `_eskf_filter_estimates()` (DR+weight) | TERCOM-коррекция по файлу высот. MAD+NCC гибрид, minima ratio, pre‑rejection gates, DR-пропагация + weighted correction. |
| **data_generator** | `data_generator.py` | `DataGenerator` | Симулирует полёт: NMEA строки с шумом. |
| **cli** | `cli.py` | CLI (click) | Точка входа: `prepare-route`, `viz-mission`, `generate-dem`, `download-dem`, `analyze`. |
| **simulation_ui** | `simulation_ui/main.py` | FastAPI SSE endpoint | Сервер для интерактивной симуляции TERCOM в реальном времени. Endpoint: `GET /api/simulate/{id}` → SSE stream из 27 шагов. |
| **simulation_ui/runner** | `simulation_ui/runner.py` | `SimulationRunner` | Оркестратор: загружает DEM, гоняет pipeline, yield-ит 27 StepData-словарей (0–26). Каждый шаг содержит `{id, number, phase, title, svg, metrics, explanation}`. Шаг 26 — сводная тепловая карта всех метрик полёта (NCC, quality, error, lost segments). Шаг 18 — trajectory data в JSON для карты. |
| **simulation_ui/svg_generator** | `simulation_ui/svg_generator.py` | `svg_dem()`, `svg_nmea()`, `svg_buffer()`, `svg_profile()`, `svg_heatmap()`, `svg_ncc_bar()`, `svg_lag()`, `svg_trajectory()`, `svg_eskf_error()`, `svg_quality()`, `svg_result()`, `svg_corridor()`, `svg_fingerprints()` | Генерация динамических SVG из реальных данных pipeline-прогона. Bootstrap dark theme цвета, 500px viewBox. |
| **simulation_ui/texts** | `simulation_ui/texts.py` | `STEPS` (list[dict]) | Тексты пояснений для каждого из 27 шагов: `title`, `subtitle`, `explanation`, `task`, `why` (3 карточки), `tags`. |
| **simulation_ui/static** | `simulation_ui/static/app.js` | SSE-клиент, step buffer, auto-play, speed control | SPA: выбор сценария → SSE стрим → пошаговый просмотр с авто-проигрыванием (×1–×10). |
| **simulation_ui/static** | `simulation_ui/static/style.css` | Bootstrap dark theme + кастомные классы | Анимации, progress bar, stepper, phase-цвета, why-grid. |

## Ключевые решения (чекпоинт — 4 фазы)

- **MAD default, NCC для отображения**: `_search_position_grid` использует MAD для поиска (минимизация), возвращает NCC при лучшем MAD. `WindowEstimate.correlation` = NCC, `mad_value` — новое поле. Тепловая карта = NCC (неизменна).
- **Mean‑subtracted MAD**: вычитание среднего из обоих массивов перед MAD — устраняет baro-смещение. Raw MAD = 500 м, mean‑sub = 0.9 м на правильной позиции.
- **Minima ratio = `second_best_mad / best_mad`**: адаптивный радиус исключения `min(2, pixel_radius−1)`. Выше = лучше (good ≥ 3.0).
- **Pre‑rejection gates**: `p2v < 5`, `mad > 30`, `ncc < 0.3`, `discr < 1.0` — консервативные пороги, ни одна корректная оценка не отбрасывается.
- **DR-пропагация + weighted correction**: `_eskf_filter_estimates` больше не использует ESKF (Kalman gain → 0 при dt=3–4 с). Вместо этого: DR от предыдущей filtered позиции + линейная коррекция с весом `w = clamp((discr−1)/10, 0, 1)`.
- **Accuracy после 4 фаз**: 4/8 правильных азимутов. Средняя ошибка: raw 254 м → filtered 156 м (−39%). Crimea — единственная регрессия (неверный азимут).

## Ключевые решения (оригинальные)

- **NavigationEstimate dataclass** вместо dict: `est.azimuth_deg` вместо `est["azimuth_deg"]`. `__dict__` для JSON.
- **Coarse-to-fine**: 10° coarse → 0.5° fine вокруг top-5. Margin = 6°.
- **DEM тюнинг**: synthetic σ=99м → dramatic σ=688м для наглядных демок.
- **Degree bug фикс**: ESKF `update_position` больше не делает `np.degrees()` на уже градусах.
- **Подписи к графикам** с примерами соотношений: каждая подпись содержит ✅⚠️❌ блок с конкретными числами (корреляция >0.95 → надёжно, ошибка азимута >30° → сбой и т.д.), чтобы пользователь понимал, хорошо это или плохо.
- **Adaptive NCC**: terrain_std ≥ 20 → детренд, < 10 → raw, 10–20 → max(raw, det). Исправляет коллапс детрендинга на равнине (Sakhalin σ=1.3 м).
- **NCC-weighted azimuth consensus**: взвешенное голосование (вес = NCC) по всем окнам для выбора итогового азимута. Scoring использует consensus_az, а не cand_az.
- **RANSAC position filter**: med + 2×MAD порог, ≥4 оценок, не трогает >50% выборки.
- **Ambiguity detection**: multi-start находит два азимута >30° с NCC в пределах 10% → `heatmap.ambiguous = True`.
- **Center-index fix**: ошибка позиции считалась от start-индекса окна вместо центра (смещение ~450 м для ws=150). Исправлено: `estimate_indices.append(i + ws // 2)`.
- **Grid radius 3→4**: поиск ±4 px вместо ±3. Покрытие DEM с разрешением 37 м/px: с ±111 м до ±148 м.

## DEMs в `data/dem/`

| DEM | Размер | Диапазон | Std | Описание |
|-----|--------|----------|-----|----------|
| `synthetic_kamchatka.tif` | 400×400 | 67–547 м | 99 м | Плавный, для отладки |
| `dramatic_kamchatka.tif` | 400×400 | 1–3489 м | 688 м | 6 вулканов + гребни + каньоны |
| `caucasus.tif` | 400×400 | 1–4114 м | 953 м | Пики до 5000 м, ущелья |
| `ural.tif` | 400×400 | 87–1600 м | 495 м | Пологий хребет |
| `altai.tif` | 400×400 | 103–3671 м | 817 м | Плато + пики |
| `crimea.tif` | 400×400 | 1–1192 м | 326 м | Гребень + море |
| `siberia.tif` | 400×400 | 30–86 м | 17 м | Равнина |
| `sakhalin.tif` | 400×400 | 1–900 м | 358 м | Остров + сопки |
| `karelia.tif` | 400×400 | 28–391 м | 85 м | Холмы + озёра |
| `primorye.tif` | 400×400 | 1–887 м | 222 м | Сопки + побережье |

## Производительность

- 53 теста за ~0.3 с
- Цель RPi: <100 ms/search через JIT
- ESKF predict/update/reset: << 1 ms

## Соглашения

- **Python 3.14**, numpy<2.5 (2.4.6), hatchling build, pyproject.toml (PEP 621)
- **pyproject.toml**: `gagarin = main:cli` entry point
- **No comments in code** — maintain this convention
- **Russian labels** in dashboard, English everywhere else
- **Plotly 6.0+** для HTML-графиков (не matplotlib)
- **pytest** для тестов (не unittest/nose)
- **ruff** для форматирования (не black/isort)
- `gagarin/` — основной пакет, `tests/` — тесты, `data/` — DEM + output

## Что ещё нужно

1. DEM profile caching в `_search_position_grid` — профили различаются только offset'ом, можно предвычислить раз и переиспользовать (×81 скорость на окно)
2. Реальный DEM Copernicus GLO-30 / SRTM вместо synthetic 400×400 — требуется tiled loading + reprojection
3. Dynamic heatmap length — `n = f(terrain_std)`: длинная на равнине, короткая в горах
4. Production‑hardening: статистическая валидация thresholds на множестве real‑world DEM

## Ссылки

- Copernicus GLO-30 DEM на AWS S3: `s3://copernicus-dem-30m/` (read-public, но таймаут)
- TERCOM: L. D. Hostetler, R. D. Andreas, "Nonlinear Kalman Filtering Techniques for Terrain-Aided Navigation"
- pyproj, pynmea2, plotly, numpy, rioxarray, click, pytest

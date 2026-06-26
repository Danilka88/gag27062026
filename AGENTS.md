# AGENTS.md — Gagarin

Технический контекст для будущих агентов / сессий.

## Архитектура

```
                     ┌─────────────┐
                     │  main.py    │ ← CLI: run, download-dem, generate-dem, analyze
                     └──────┬──────┘
                            │ run
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │pipeline  │  │ DataGen  │  │Viz       │
        │.py       │  │ .py      │  │*.py      │
        └────┬─────┘  └──────────┘  └────┬─────┘
             │                            │
    ┌───────┼──────┬──────┬──────┬───┐    ├──────┬──────┬──────┬──────┬────────┐
    ▼       ▼      ▼      ▼      ▼   ▼    ▼      ▼      ▼      ▼      ▼        ▼
┌──────┐ ┌────┐ ┌────┐ ┌────┐ ┌──┐ ┌──┐ ┌────┐ ┌──────┐ ┌────┐ ┌────┐ ┌────────┐
│buffer│ │cor-│ │est-│ │dem │ │geo│ │qu│ │temp│ │utils │ │dash│ │tra-│ │correla-│
│.py   │ │rel-│ │ima-│ │loa-│ │_u│ │al│ │late│ │.py   │ │boa-│ │jec-│ │tion.   │
│NMEABu│ │ator│ │tor │ │der │ │t-│ │it│ │.py  │ │save_ │ │rd  │ │tory│ │py      │
│ffer  │ │.py │ │.py │ │.py │ │il│ │y.│ │HTML_│ │html()│ │.py │ │.py │ │correla-│
│deque  │ │TER-│ │Velo│ │DEM │ │s.│ │py│ │TEMP │ │save_ │ │nav- │ │tra- │ │tion_he│
│adapt. │ │COM │ │cit │ │Lo- │ │py│ │  │ │LATE │ │dashb │ │iga- │ │jec- │ │atmap() │
│dist.  │ │Cor-│ │yEs│ │ader│ │of│ │  │ │     │ │oard()│ │tion_│ │tory_│ │        │
│       │ │r-  │ │tim-│ │Co- │ │fs│ │  │ │     │ │get_g │ │das- │ │map( │ │        │
│       │ │ela-│ │ator│ │ord │ │et│ │  │ │     │ │rid_o │ │hboa │ │)    │ │        │
│       │ │tor │ │Nav-│ │Tra-│ │_c│ │  │ │     │ │r_fal │ │rd() │ │     │ │        │
│       │ │Hyp-│ │iga-│ │nsf │ │oo│ │  │ │     │ │lback │ │     │ │     │ │        │
│       │ │oth-│ │tion│ │DEM-│ │rd│ │  │ │     │ │()    │ │     │ │     │ │        │
│       │ │esis│ │Est-│ │Int-│ │s_│ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │Sea-│ │ima-│ │erp-│ │ba│ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │rch │ │te  │ │ola-│ │tc│ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │Cor-│ │(da-│ │tor │ │h)│ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │rel-│ │tac-│ │    │ │  │ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │atio│ │las│ │    │ │  │ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │n Me│ │s) │ │    │ │  │ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │tric│ │   │ │    │ │  │ │  │ │     │ │      │ │     │ │     │ │        │
│       │ │s   │ │   │ │    │ │  │ │  │ │     │ │      │ │     │ │     │ │        │
└───────┘ └────┘ └───┘ └────┘ └──┘ └──┘ └─────┘ └──────┘ └────┘ └────┘ └────────┘
                            ┌───────┐ ┌────────┐ ┌──────────┐
                            │eskf  │ │config  │ │nmea_    │
                            │.py   │ │.py     │ │parser   │
                            │State │ │vali-   │ │.py      │
                            │Error │ │dation  │ │pynmea2  │
                            │Kalman│ │+ merger│ │wrapper  │
                            │Filter│ │        │ │         │
                            └──────┘ └────────┘ └─────────┘
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
| **viz/template** | `viz/template.py` | `HTML_TEMPLATE` | HTML-шаблон с тёмной темой (GitHub Dark), 5 карточек, табы Synthetic/Dramatic, адаптивная вёрстка. |
| **viz/utils** | `viz/utils.py` | `TEMPLATE`, `save_html()` (одиночный Figure), `save_dashboard()` (список chart-ов), `get_grid_or_fallback()`, константы стилей | Общие утилиты и функции сохранения HTML. |
| **viz/dashboard** | `viz/dashboard.py` | `navigation_dashboard(data)` → `go.Figure`, `unified_dashboard(syn, dram)` → `list[dict]` | Генерация дашбордов. `navigation_dashboard` — для одного DEM (старый формат). `unified_dashboard` — для сравнения DEM: возвращает список из 5 chart-словарей (terrain, profile, timeline, error, heatmap). |
| **viz/components** | `viz/components.py` | `terrain_traces()`, `profile_traces()`, `timeline_traces()`, `error_traces()`, `correlation_heatmap_trace()`, `drift_traces()`, `quality_pie()` | Фабрики Plotly trace-ов для каждого типа графика. Используются обоими дашбордами. |
| **viz/data_model** | `viz/data_model.py` | `DashboardData`, `TerrainData`, `TrajectoryData`, `EstimateData`, `CorrData`, `ProfileData`, `ErrorData`, `build_dashboard_data()` | Dataclass-ы для передачи данных в визуализацию. |
| **viz/trajectory** | `viz/trajectory.py` | `trajectory_map()` | 2D карта истинного vs оценённого трека (одиночный Figure). |
| **viz/correlation** | `viz/correlation.py` | `correlation_heatmap()` | Тепловая карта coarse search (одиночный Figure). |
| **viz/profile** | `viz/profile.py` | `profile_comparison()` | Сравнение измеренного vs эталонного профиля (одиночный Figure). |
| **data_generator** | `data_generator.py` | `DataGenerator` | Симулирует полёт: NMEA строки с шумом. |
| **main** | `main.py` | CLI (click) | Точка входа: `run`, `download-dem`, `generate-dem`, `analyze`. |
| **simulation_ui** | `simulation_ui/main.py` | FastAPI SSE endpoint | Сервер для интерактивной симуляции TERCOM в реальном времени. Endpoint: `GET /api/simulate/{id}` → SSE stream из 14 шагов. |
| **simulation_ui/runner** | `simulation_ui/runner.py` | `SimulationRunner` | Оркестратор: загружает DEM, гоняет pipeline, yield-ит 14 StepData-словарей. Каждый шаг содержит `{id, number, phase, title, svg, metrics, explanation}`. |
| **simulation_ui/svg_generator** | `simulation_ui/svg_generator.py` | `svg_dem()`, `svg_nmea()`, `svg_buffer()`, `svg_profile()`, `svg_heatmap()`, `svg_ncc_bar()`, `svg_lag()`, `svg_trajectory()`, `svg_eskf_error()`, `svg_quality()`, `svg_result()`, `svg_corridor()`, `svg_fingerprints()` | Генерация динамических SVG из реальных данных pipeline-прогона. Bootstrap dark theme цвета, 500px viewBox. |
| **simulation_ui/texts** | `simulation_ui/texts.py` | `STEPS` (list[dict]) | Тексты пояснений для каждого из 14 шагов: `title`, `subtitle`, `explanation`, `task`, `why` (3 карточки), `tags`. |
| **simulation_ui/static** | `simulation_ui/static/app.js` | SSE-клиент, step buffer, auto-play, speed control | SPA: выбор сценария → SSE стрим → пошаговый просмотр с авто-проигрыванием (×1–×10). |
| **simulation_ui/static** | `simulation_ui/static/style.css` | Bootstrap dark theme + кастомные классы | Анимации, progress bar, stepper, phase-цвета, why-grid. |

## Ключевые решения

- **NavigationEstimate dataclass** вместо dict: `est.azimuth_deg` вместо `est["azimuth_deg"]`. `__dict__` для JSON.
- **Coarse-to-fine**: 10° coarse → 0.5° fine вокруг top-5. Margin = 6°.
- **DEM тюнинг**: synthetic σ=95м → dramatic σ=687м для наглядных демок.
- **Degree bug фикс**: ESKF `update_position` больше не делает `np.degrees()` на уже градусах.
- **5 отдельных go.Figure вместо make_subplots** в `unified_dashboard()`. Каждый график — самостоятельный Figure с трейсами обоих DEM. Это позволяет рендерить их в отдельных HTML-карточках.
- **save_html()** для одиночных Figure (старый формат). **save_dashboard()** для списка chart-ов: использует HTML_TEMPLATE из `template.py`, сериализует каждый Figure в JSON, добавляет массивы видимости для табов.
- **HTML-шаблон** (`template.py`): GitHub Dark тема, 5 карточек, каждая с заголовком, Plotly-графиком и подписью. Табы Synthetic/Dramatic переключают видимость трейсов через `Plotly.restyle()`. Описания вкладок (что за DEM, зачем нужен) показываются под табами.
- **Подписи к графикам** с примерами соотношений: каждая подпись содержит ✅⚠️❌ блок с конкретными числами (корреляция >0.95 → надёжно, ошибка азимута >30° → сбой и т.д.), чтобы пользователь понимал, хорошо это или плохо.

## DEMs в `data/dem/`

| DEM | Размер | Диапазон | Std | Описание |
|-----|--------|----------|-----|----------|
| `synthetic_kamchatka.tif` | 400×400 | 101–600 m | 95 m | Плавный, для разработки |
| `dramatic_kamchatka.tif` | 400×400 | 10–3489 m | 687 m | 6 вулканов + гребни + каньоны |

## Производительность

- 32 теста за ~0.3 с
- `main.py run`: 231 estimate за ~13 с (~60 ms/search)
- Цель RPi: <100 ms/search через numba JIT
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

1. README.md
2. Docstrings на публичные функции/классы (большая работа, механическая)
3. Реальный DEM Copernicus GLO-30 (скачивание с S3 падает)
4. Numba JIT на hot path (для RPi)
5. INS drift simulation в data_generator

## Ссылки

- Copernicus GLO-30 DEM на AWS S3: `s3://copernicus-dem-30m/` (read-public, но таймаут)
- TERCOM: L. D. Hostetler, R. D. Andreas, "Nonlinear Kalman Filtering Techniques for Terrain-Aided Navigation"
- pyproj, pynmea2, plotly, numpy, rioxarray, click, pytest

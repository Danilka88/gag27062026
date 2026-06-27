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
| **data_generator** | `data_generator.py` | `DataGenerator` | Симулирует полёт: NMEA строки с шумом. |
| **cli** | `cli.py` | CLI (click) | Точка входа: `prepare-route`, `viz-mission`, `generate-dem`, `download-dem`, `analyze`. |
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
- **Подписи к графикам** с примерами соотношений: каждая подпись содержит ✅⚠️❌ блок с конкретными числами (корреляция >0.95 → надёжно, ошибка азимута >30° → сбой и т.д.), чтобы пользователь понимал, хорошо это или плохо.

## DEMs в `data/dem/`

| DEM | Размер | Диапазон | Std | Описание |
|-----|--------|----------|-----|----------|
| `synthetic_kamchatka.tif` | 400×400 | 101–600 m | 95 m | Плавный, для разработки |
| `dramatic_kamchatka.tif` | 400×400 | 10–3489 m | 687 m | 6 вулканов + гребни + каньоны |

## Производительность

- 32 теста за ~0.3 с
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

1. Docstrings на публичные функции/классы (большая работа, механическая)
2. Реальный DEM Copernicus GLO-30 (скачивание с S3 падает)
3. INS drift simulation в data_generator

## Ссылки

- Copernicus GLO-30 DEM на AWS S3: `s3://copernicus-dem-30m/` (read-public, но таймаут)
- TERCOM: L. D. Hostetler, R. D. Andreas, "Nonlinear Kalman Filtering Techniques for Terrain-Aided Navigation"
- pyproj, pynmea2, plotly, numpy, rioxarray, click, pytest

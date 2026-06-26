# AGENTS.md — Gagarin

Технический контекст для будущих агентов / сессий.

## Архитектура (текущая)

```
                    ┌─────────────┐
                    │  main.py    │ ← CLI: run, download-dem, generate-dem, analyze
                    └──────┬──────┘
                           │ run
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │pipeline  │ │ DataGen  │ │Viz       │
        │.py       │ │ .py      │ │*.py      │
        └────┬─────┘ └──────────┘ └──────────┘
             │
    ┌────────┼────────┬────────┬──────────┬─────────┐
    ▼        ▼        ▼        ▼          ▼         ▼
┌───────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐ ┌───────┐
│buffer │ │corre-│ │estim-│ │dem   │ │geo_    │ │quality│
│.py    │ │lator │ │ator  │ │loader│ │utils   │ │.py    │
│NMEABuf│ │.py   │ │.py   │ │.py   │ │.py     │ │.py    │
│fer    │ │TERCOM│ │Veloc-│ │DEMLo │ │offset  │ │_assess│
│deque  │ │Correl│ │ityEst│ │ader  │ │_coords │ │()     │
│adapt. │ │ator  │ │imator│ │Coord │ │_batch  │ │       │
│dist.  │ │Hypoth│ │Navig-│ │Transf│ │        │ │       │
│       │ │esis  │ │ation │ │DEMIn-│ │        │ │       │
│       │ │Search│ │Estim │ │terpol│ │        │ │       │
│       │ │Corre │ │ate   │ │ator  │ │        │ │       │
│       │ │lation│ │(data-│ │      │ │        │ │       │
│       │ │Metri │ │class)│ │      │ │        │ │       │
│       │ │cs    │ │      │ │      │ │        │ │       │
└───────┘ └──────┘ └──────┘ └──────┘ └────────┘ └───────┘
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
| **viz/utils** | `viz/utils.py` | `TEMPLATE`, `BEST_MARKER`, `TRUE_LINE`, `EST_LINE`, `save_html()`, `get_grid_or_fallback()` | Общие константы и утилиты визуализации. |
| **viz/dashboard** | `viz/dashboard.py` | `navigation_dashboard()`, `comparison_dashboard()` | Plotly HTML-дашборды. Русские подписи. |
| **viz/trajectory** | `viz/trajectory.py` | `trajectory_map()` | 2D карта истинного vs оценённого трека. |
| **viz/correlation** | `viz/correlation.py` | `correlation_heatmap()` | Тепловая карта coarse search. |
| **viz/profile** | `viz/profile.py` | `profile_comparison()` | Сравнение измеренного vs эталонного профиля. |
| **data_generator** | `data_generator.py` | `DataGenerator` | Симулирует полёт: NMEA строки с шумом. |
| **main** | `main.py` | CLI (click) | Точка входа: `run`, `download-dem`, `generate-dem`, `analyze`. |

## Ключевые решения

- **NavigationEstimate dataclass** вместо dict: `est.azimuth_deg` вместо `est["azimuth_deg"]`. `__dict__` для JSON.
- **Coarse-to-fine**: 10° coarse → 0.5° fine вокруг top-5. Margin = 6°.
- **DEM тюнинг**: synthetic σ=95м → dramatic σ=687м для наглядных демок.
- **Degree bug фикс**: ESKF `update_position` больше не делает `np.degrees()` на уже градусах.
- **save_html()** в `viz/utils.py`, реэкспорт через `viz/__init__.py`.

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

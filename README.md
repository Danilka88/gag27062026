# Gagarin

**TERCOM-навигация для БПЛА в условиях отсутствия GNSS.**

Система оценивает положение и скорость летательного аппарата путём корреляции
профилей радиовысотомера с цифровой моделью рельефа (DEM). Предназначена для
коммерческих БПЛА, работающих в GNSS-denied среде.

Включает **предполётное планирование**: оценку информативности рельефа вдоль
маршрута, выявление участков риска ложных корреляций и упаковку данных для
бортового использования.

---

## Технология

### TERCOM (Terrain Contour Matching)

Классический метод коррекции навигации по рельефу:

1. Борт измеряет абсолютную высоту (барометр) и относительную (радиовысотомер).
   Разность даёт профиль рельефа под траекторией.
2. Буфер накапливает `N` последних измерений — скользящее окно.
3. Для гипотез азимута и скорости строится ожидаемый (reference) профиль из DEM.
4. Вычисляется нормализованная кросс-корреляция (NCC) между наблюдаемым и
   эталонным профилями.
5. Гипотеза с максимальной корреляцией даёт оценку вектора скорости.
6. Dead reckoning (движение по сфере) интегрирует скорость в положение.
7. Error-State Kalman Filter (ESKF) сглаживает оценки и подавляет шум.

### coarse-to-fine search

| Этап | Шаг азимута | Количество гипотез | Описание |
|------|-------------|-------------------|----------|
| Coarse | 10° | 36 × N_speed | Полный охват 360° |
| Fine | 0.5° | ±6° вокруг top-5 | Уточнение вокруг лучших кандидатов |

Скорость уточняется одновременно через `np.linspace` в окрестности ±15 м/с.

### Pre-flight fingerprinting

Для каждой точки маршрута вычисляются метрики:
- **std elevation** — стандартное отклонение рельефа в окрестности
- **gradient magnitude** — модуль градиента высот
- **Minima Ratio** (Akinci 2026) — доля минимумов высот, характеризует
 「узнаваемость」участка
- **NCC under lateral offset** — насколько сильно падает корреляция при
  боковом смещении (индикатор ложных срабатываний)

Результат упаковывается в SQLite (с R-Tree индексом) + GeoTIFF карта
информативности.

---

## Архитектура

```
                    ┌──────────────────────────┐
                    │  simulation_ui/main.py   │
                    │  FastAPI + SSE (18 шагов)│
                    └────┬─────────────────────┘
                         │
         ┌───────────────┼───────────────────┐
         ▼               ▼                   ▼
   ┌──────────┐   ┌──────────┐   ┌──────────────────┐
   │ pipeline │   │data_gen  │   │  svg_generator   │
   │   .py    │   │erator.py │   │      .py         │
   └────┬─────┘   └──────────┘   └──────────────────┘
        │
   ┌────┼────┬─────┬──────┬──────┬────┐
   ▼    ▼    ▼     ▼      ▼      ▼    ▼
buffer correl estim  dem    geo   eskf qual
       ator  ator  loader  utils      ity
```

### Пакет `gagarin/` (ядро)

| Модуль | Назначение |
|--------|-----------|
| `config.py` | Все тюнябельные параметры: размер окна, шаги поиска, пороги. `merge()` с предупреждением на неизвестные ключи. |
| `nmea_parser.py` | Обёртка над `pynmea2`. Парсит `$GPGGA` → `NMEAReading` dataclass. |
| `buffer.py` | Скользящее окно (deque). `add()`, `is_full()`, `get_profile()`, `advance_distance()`. Адаптивная дистанция. |
| `dem_loader.py` | Загрузка GeoTIFF через `rioxarray`. Трансформация CRS (`pyproj`). Билинейная интерполяция. |
| `correlator.py` | `TERCOMCorrelator` — coarse → fine поиск. `HypothesisSearch`, `CorrelationMetrics` (NCC, cross-correlation, confidence). |
| `estimator.py` | `VelocityEstimator` — преобразует `MatchResult` в `NavigationEstimate` (dataclass). Dead reckoning central shift. |
| `geo_utils.py` | `offset_coords()` — движение по сфере. `offset_coords_batch()` — векторизованная версия для NumPy. |
| `quality.py` | Классификация good/marginal/poor + confidence score. |
| `eskf.py` | `ErrorStateKalmanFilter` — 6D фильтр (lat, lon, v_N, v_E, v_D, baro_bias). `solve` вместо `inv`. |
| `pipeline.py` | `NavigationPipeline` — оркестратор: буфер → корреляция → оценка → dead reckoning → ESKF. |
| `preprocess.py` | `TerrainAnalyzer`, `MissionPreprocessor` — предполётный анализ. |
| `data_generator.py` | Симуляция полёта: NMEA строки с шумом, случайные траектории. |
| `profile.py` | Извлечение и валидация барометрических/радиолокационных профилей. |
| `constants.py` | `EARTH_RADIUS`, `NEAR_ZERO`, `GRAVITY`. |

### Пакет `simulation_ui/` (интерактивная симуляция)

| Модуль | Назначение |
|--------|-----------|
| `main.py` | FastAPI сервер: `GET /api/simulate/{id}` → SSE поток из 18 шагов. |
| `runner.py` | `SimulationRunner` — загружает DEM, гоняет pipeline, выдаёт StepData словари. |
| `svg_generator.py` | 13 SVG-генераторов: DEM, NMEA, буфер, профиль, тепловая карта, NCC bar, лаг, траектория, ESKF ошибка, качество, corridor, fingerprints. |
| `texts.py` | Пояснения для каждого шага: заголовок, подзаголовок, explanation, task, why (3 карточки), tags. |
| `static/` | SPA на чистом JS: SSE-клиент, step buffer, auto-play (×1–×10), пошаговый просмотр, AI-анализ. |

### Пакет `gagarin/viz/`

| Модуль | Назначение |
|--------|-----------|
| `mission.py` | `mission_viewer()` — 3-панельный HTML вьювер: карта, профиль информативности, fingerprint матрица. |

---

## Установка

### Требования

- Python ≥ 3.11
- NumPy ≥ 1.22 (< 2.5)
- Браузер для simulation UI

### Из репозитория

```bash
git clone <repo> gagarin
cd gagarin
uv sync     # или: pip install -e ".[dev]"
```

### Проверка

```bash
uv run pytest -v
# 41 passed
```

### Запуск симуляции

```bash
uv run uvicorn simulation_ui.main:app
# → http://127.0.0.1:8000
```

---

## Использование

### Интерактивная симуляция (UI)

```bash
uv run uvicorn simulation_ui.main:app --reload
```

Откройте браузер на `http://127.0.0.1:8000`. Доступно 10 сценариев
с разными DEM (Камчатка, Кавказ, Крым, Урал, Алтай и др.).

UI показывает 18 шагов TERCOM-конвейера в реальном времени:
1. Fingerprints маршрута (карта информативности)
2. Загрузка DEM
3. Парсинг NMEA
4. Буферизация
5. Профиль рельефа
6. Тепловая карта корреляций
7. NCC bar (результаты coarse поиска)
8. Cross-correlation lag
9. Оценка скорости
10. Dead reckoning
11. ESKF коррекция
12. Ошибка ESKF
13. Качество оценки
14. Траектория
15. Corridor неопределённости
16. Результат
17. Сводка улучшений
18. Финальная траектория

### CLI

```bash
# Список команд
gagarin --help

# Предполётный анализ маршрута
gagarin prepare-route \
  --waypoints waypoints.csv \
  -d data/dem/dramatic_kamchatka.tif \
  -o mission_pkg

# Визуализация миссии
gagarin viz-mission mission_pkg
# → открывается mission_viewer.html

# Генерация синтетических DEM
gagarin generate-dem -o data/dem/my_dem.tif

# Скачивание Copernicus GLO-30
gagarin download-dem \
  --lat 56.0 --lon 160.0 \
  --size 0.5 \
  -o data/dem/copernicus.tif

# Обработка NMEA лога
gagarin analyze nmea_log.txt
```

### Предполётный workflow

```bash
# 1. Создать waypoints CSV
cat > waypoints.csv <<EOF
lat,lon
56.10,160.60
56.12,160.63
56.15,160.68
56.18,160.72
56.20,160.75
56.23,160.77
EOF

# 2. Анализ рельефа
gagarin prepare-route --waypoints waypoints.csv \
  -d data/dem/dramatic_kamchatka.tif \
  -o mission_pkg

# 3. Просмотр
gagarin viz-mission mission_pkg
```

---

## DEM

| DEM | Размер | Высоты | Std | Описание |
|-----|--------|--------|-----|----------|
| `synthetic_kamchatka.tif` | 400×400 | 67–547 м | 99 м | Плавный, для отладки |
| `dramatic_kamchatka.tif` | 400×400 | 1–3489 м | 688 м | 6 вулканов, гребни, каньоны |
| `caucasus.tif` | 400×400 | 1–4114 м | 953 м | Пики до 5000 м, ущелья |
| `ural.tif` | 400×400 | 87–1600 м | 495 м | Пологий хребет |
| `altai.tif` | 400×400 | 103–3671 м | 817 м | Плато + пики |
| `crimea.tif` | 400×400 | 1–1192 м | 326 м | Гребень + море |
| `siberia.tif` | 400×400 | 30–86 м | 17 м | Равнина |
| `sakhalin.tif` | 400×400 | 1–900 м | 358 м | Остров + сопки |
| `karelia.tif` | 400×400 | 28–391 м | 85 м | Холмы + озёра |
| `primorye.tif` | 400×400 | 1–887 м | 222 м | Сопки + побережье |

Генерация всех DEM: `gagarin generate-all`

---

## Производительность

| Операция | Время |
|----------|-------|
| 41 тест | ~0.3 с |
| 231 оценка (300 с полёт) | ~13 с real-time |
| 1 корреляционный поиск | ~60 мс |
| ESKF predict / update / reset | << 1 мс |
| 6 waypoints → 122 fingerprint | ~5 с |

---

## Ссылки

- L. D. Hostetler, R. D. Andreas, *Nonlinear Kalman Filtering Techniques for Terrain-Aided Navigation*
- Copernicus GLO-30 DEM: `s3://copernicus-dem-30m/`
- `pynmea2`, `rioxarray`, `pyproj`, `plotly`, `click`, `numpy`

## Лицензия

MIT — см. `LICENSE`.

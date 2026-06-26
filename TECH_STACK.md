# Tech Stack Analysis — Gagarin (TERCOM Navigation)

> Почему выбран каждый компонент, какие альтернативы рассматривались,
> в чём преимущества, ограничения и перспективы масштабирования.

---

## 1. Core Algorithms

### 1.1 TERCOM (Terrain Contour Matching)

**Задача:** Определение местоположения и скорости БПЛА по профилям радиовысотомера
в условиях отсутствия GNSS.

**Почему TERCOM, а не SITAN, ICP или Particle Filter:**

| Метод | Сравнение |
|---|---|
| **TERCOM (batch NCC)** | batch-корреляция всего накопленного окна — детерминированно, без итераций. Время ~const(O(N×M)). Не требуется начальная гипотеза близко к истине. |
| **SITAN** | extended Kalman filter в реальном времени, линеаризует рельеф в точке. Требует хорошей начальной оценки. Сходится быстро, но может разойтись. |
| **ICP (Iterative Closest Point)** | Итеративное выравнивание 2D/3D точек. O(k×N×logN). Избыточен для 1D профилей. |
| **Particle Filter** | O(P×N) частиц. Медленнее TERCOM на малых окнах, но робастнее на шумах. Основной конкурент для продакшна. |

**Преимущества TERCOM для данного проекта:**
1. Детерминизм — одинаковый результат при одинаковых входных данных (легче отлаживать)
2. coarse-to-fine даёт ~664ms на MacBook Air M4 (360 coarse гипотез + fine refinement)
3. Не требует начальной гипотезы (search по всей сетке azimuth×speed)
4. Простая кросс-корреляция — не надо обучать модель
5. Доказанная авионика 1960-х (Cruise Missile, Tomahawk)

**Недостатки:**
1. С каждым окном накапливается ошибка позиционирования → дрейф оценки
2. Без IMU/INS integration дрейф неизбежен (истинная проблема проекта)
3. Шумный DEM (особенно Copernicus GLO-30 ~30m) даёт ложные корреляции

**Масштабирование:**
- O(A×S×W) где A — количество азимутов, S — скоростей, W — размер окна.
- coarse-topN 5 → fine (6°×0.5°, 15м/с×~12 шагов) лишь ×10 к coarse.
- Batch-операции векторизованы numpy → GPU потенциально через CuPy/JAX.
- На RPi (ARM64) ожидается ~5-10s/окно → нужны оптимизации (numba JIT, downsampling DEM, меньше гипотез).
- **Не масштабируется горизонтально** — последовательный streaming.

---

### 1.2 NCC (Normalized Cross-Correlation)

**Задача:** Численная мера сходства между наблюдённым профилем рельефа
и эталонным профилем из DEM.

**Почему NCC, а не:**

| Метод | Сравнение |
|---|---|
| **NCC** | инвариантен к масштабу (нормирован), O(W), прост. Результат в [-1, 1] |
| **Pearson correlation** | то же самое (NCC ≡ Pearson для двух векторов) |
| **Spearman rank** | робастен к выбросам, но теряет амплитуду рельефа — не подходит |
| **Mutual Information** | медленный O(W²), избыточен для 1D профилей |
| **MSE / MAE** | не нормированы — не сравнить между разными профилями |

**Преимущества NCC:**
1. Нормирован — можно сравнивать профили разной амплитуды
2. O(W) — минимальная сложность
3. Даёт пик ~1.0 при идеальном совпадении, ~0-0.3 при случайном
4. Лаг через `np.correlate()` дополняет основную корреляцию

**Масштабирование:**
- O(W) легко, W=200 константа → ∼2μs на профиль в numpy
- Fine refinement: 5×~24×~12 ≈ 1440 вызовов → ∼3ms
- Отлично векторизуется: все 360 coarse гипотез в одном `np.array` почти возможны

---

### 1.3 ESKF (Error-State Kalman Filter)

**Задача:** Сглаживание зашумлённых TERCOM-оценок, слияние position + velocity наблюдений.

**Почему Error-State (indirect), а не direct EKF или UKF:**

| Метод | Сравнение |
|---|---|
| **ESKF (indirect)** | Оценивает ошибку (δx), а не полное состояние. Меньше линейности в δx, чем в x. 6D-вектор (lat,lon,vx,vy,bias_x,bias_y). |
| **EKF (direct)** | Линеаризует нелинейную динамику полного состояния. 4-6D, но линеаризация грубее для position. |
| **UKF** | sigma-points, O(N³) против O(N²) EKF. Не нужен Jacobian, но дороже. Избыточен для 4-6D задачи. |
| **Particle Filter** | Сотни-тысячи частиц. Может работать с multi-modal распределением, но slow на RPi. |

**Преимущества ESKF:**
1. Ошибки в δx действительно примерно линейны — линеаризация точнее, чем в direct EKF
2. 6D — минимальная размерность для position + velocity + bias
3. `predict()` и `update()` — O(N²) = O(36) — ∼1μs
4. Легко ресетить: `δx → 0` после инжекции → не накапливается ошибка фильтра
5. Раздельные `update_position` и `update_velocity` дают гибкость

**Масштабирование:**
- O(N²) с N=6 — незначимо
- Можно увеличить размерность до 9-12 добавив bias акселерометра/гироскопа — всё ещё O(144) 
- Легко портируется на C/C++ для embedded
- Не подлежит горизонтальному масштабированию (один последовательный фильтр)

---

### 1.4 Coarse-to-Fine Search

**Задача:** Ускорение перебора azimuth×speed без потери точности.

**Почему coarse-to-fine, а не:**

| Метод | Сравнение |
|---|---|
| **Coarse-to-fine** | 36 az × 10 sp = 360 coarse → top5 × (12az×25sp) ≈ 1500 fine. Всего ~1860 гипотез. |
| **Full brute-force** | 72 az × 15 sp = 1080 (тоже fine step). Сейчас ~1.7× быстрее. |
| **MCMC / random sampling** | Мог бы сходиться быстрее для высокой размерности, но для 2D (az, sp) coarse-to-fine проще. |
| **Gradient descent** | NCC не гладкая — локальные максимумы. Coarse гарантирует глобальный поиск. |

**Преимущества:**
1. Алгоритмически прост, детерминирован
2. fine margin = 6° (полшага 10° + запас) гарантирует покрытие
3. 664ms против 880ms brute-force (×1.32 ускорение)

**Масштабирование:**
- coarse step 10° → 36 azimuths — можно уменьшить до 5° (72) за ×2 времени
- fine margin 6° при 10° coarse — может быть уменьшен до 5° при достаточном SNR
- **Бутылочное горлышко:** `elevation_batch()` — 1860× вызов bi-linear interpolation
  — оптимизация через `numba.jit` даст ×5-10

---

### 1.5 Velocity Estimation + Dead Reckoning

**Задача:** Преобразование `MatchResult` в географические координаты (lag → offset).
Синхронизация центрального положения конвейера.

**Альтернатив нет:** Это необходимый glue code между TERCOM и ESKF.

**Масштабирование:** O(1) — тригонометрия + сложение.

---

### 1.6 Quality Assessment

**Задача:** Оценка достоверности корреляции (good/marginal/poor).

**Почему такое решение, а не вероятностный подход:**
- Текущий assess() — набор пороговых правил (confidence > 0.6, 0.3-0.6, < 0.3)
- peak_sharpness и discrimination_ratio — дополнительные эвристики
- **Можно улучшить:** Gaussian Process confidence, calibration на исторических данных,
  bootstrap-оценка распределения NCC

**Масштабирование:** O(W) — тривиально.

---

## 2. Python Scientific Stack

### 2.1 NumPy (`numpy>=1.22, <2.5`)

**Задача:** Все численные расчёты — массивы, линейная алгебра, тригонометрия,
статистика, конкатенация, random.

**Почему NumPy, а не:**

| Библиотека | Сравнение |
|---|---|
| **NumPy** | De facto standard scientific Python. Векторизация, broadcasting, BLAS/LAPACK под капотом. |
| **JAX** | JIT + GPU + autograd. Но beta, сложнее с rioxarray, нет ARM64 wheels для RPi. |
| **CuPy** | GPU-only. Не подходит для RPi. |
| **Pure Python lists** | В 10-100× медленнее — критично для 1860 гипотез. |

**Преимущества:**
1. Векторизованные операции — `elevation_batch()` без циклов
2. BLAS через `np.linalg.inv` — O(N³) для ESKF, но N=6 → незначимо
3. Широкая экосистема: rioxarray, xarray, scipy, plotly — все базируются на numpy
4. Стабильный ABI, C extensions, ARM64 wheels

**Масштабирование:**
- numpy не multi-thread (GIL), но `np.dot` и `np.linalg` используют OpenMP/BLAS threads
- Векторизация batch-операций — ключевой приём производительности
- На RPi numpy без MKL — примерно ×1.5-2 медленнее, чем на MacBook
- Переход на JAX возможен, но потребует замены rioxarray на rasterio + JAX array

**Констрейнт:** `numpy<2.5` из-за numba 0.65.1 (numpy 2.5 сломал ABI). В будущем numpy 2.5+ заработает с numba.

---

### 2.2 SciPy (`scipy>=1.15`)

**Задача:** (задекларирован, но пока не используется)

**Почему в зависимостях:**
- `scipy.linalg` — если ESKF перейдёт на `sqrt`-filter (более устойчивый Joseph form)
- `scipy.ndimage` — для фильтрации DEM (Gaussian blur, morphological ops)
- `scipy.optimize` — для fine-search минимизацией MSE
- `scipy.signal` — cross-correlation с sub-sample точностью

**На данный момент:** все операции через numpy — dependency "just in case".

**Масштабирование:** Не влияет, пока не импортится.

---

### 2.3 Numba (`numba>=0.65`)

**Задача:** (задекларирован, но пока не используется)

**Почему в зависимостях:**
- Ключевой кандидат для JIT-компиляции `elevation_batch()` (hot path: 1860 вызовов × билинейная интерполяция)
- `_ncc` — хотя и так быстрый, но JIT уберёт Python overhead
- `_build_reference_profile` — может быть JIT-скомпилирован

**Почему Numba, а не Cython или raw C extension:**
- Numba: декоратор `@jit` → LLVM → машинный код. Минимальные изменения кода.
- Cython: требует `.pyx` файлов, typing, отдельной компиляции.
- C extension: максимальный контроль, но overhead на поддержку.
- Numba ≈ 80% производительности C с 10% усилий.

**Масштабирование:**
- JIT даёт ×5-10 на численных циклах
- `nopython=True` mode — максимальная скорость
- На RPi ARM64: numba работает через LLVM, производительность ~×3-5 от Python
- **Ограничение:** numpy 2.5 сломал ABI, зафиксировано <2.5

---

## 3. Geospatial

### 3.1 Rioxarray (`rioxarray>=0.22`)

**Задача:** Открытие GeoTIFF DEM, чтение CRS, affine transform, bounds.

**Почему rioxarray, а не:**

| Библиотека | Сравнение |
|---|---|
| **rioxarray** | Xarray-native: DEM загружается как `xr.DataArray` с координатами lon/lat. `rio.crs`, `rio.bounds()`, `rio.transform()` — доступ через `.rio` accessor. |
| **rasterio** | Ниже уровнем. Работает с `dataset` и `transform` напрямую. Самый быстрый I/O. Нет интеграции с xarray — нужно писать обёртки. |
| **GDAL (osgeo)** | C-API через Python. Максимальный контроль, но un-Pythonic, тяжёлый. |
| **raw PIL/imageio** | Не читает GeoTIFF метаданные (CRS, transform). |

**Преимущества rioxarray:**
1. `elevation_batch()` использует `(row, col)` через transform → numpy индексация — без pyproj на hot path
2. `xr.DataArray` с lon/lat координатами — читаемые дампы
3. CRS-aware: автоматическая reprojection при необходимости
4. Лёгкий синтаксис: `ds.rio.bounds()` vs `gdal.Info()`

**Масштабирование:**
- DEM 400×400 = 1.3 MB — весь файл в памяти → не проблема
- Реальный Copernicus tile ~30 MB × 4 = 120 MB — всё ещё вмещается в RAM (16GB)
- Для 1m DEM (LiDAR) → 1GB+/tile → нужен chunked I/O (xarray chunks, dask)
- `rioxarray` с `dask` (chunks) масштабируется до 100GB+ растро

---

### 3.2 Xarray (`xarray>=2025`)

**Задача:** Labeled array — DEM с координатами (lat, lon, elev).

**Почему xarray, а не:**

| Библиотека | Сравнение |
|---|---|
| **xarray** | Labeled dimensions, alignment, integration с rioxarray, dask. |
| **pandas** | 2D-DataFrame для растра неэффективен из-за MultiIndex. |
| **numpy + separate arrays** | Без координат — ошибки индексации, ручной alignment. |

**Преимущества xarray:**
1. DEM dimensions (lat, lon) — slice через `.sel(lat=..., lon=...)` можно (но в hot path используем transform)
2. `.rio` accessor через rioxarray
3. Совместимость с NetCDF/HDF5 для больших DEM

**Масштабирование:**
- Для текущих размеров избыточно (numpy хватило бы)
- На big data: xarray + dask → out-of-core операции на растрах 100GB+
- **Для RPi:** overhead xarray заметен — старт ~0.3s на загрузку. Можно кешировать в памяти.

---

### 3.3 PyProj (`pyproj>=3.7`)

**Задача:** Пересчёт координат между CRS DEM и EPSG:4326 (lat/lon).

**Почему pyproj, а не:**

| Библиотека | Сравнение |
|---|---|
| **pyproj** | Pythonic обёртка над PROJ. `Transformer.from_crs(a, b, always_xy=True)` — просто. |
| **GDAL OSR** | osr.CoordinateTransformation — verbose, C-стиль. |
| **math-only** | Только для сферической модели Земли (WGS84). Не работает с проекциями DEM. |

**Преимущества pyproj:**
1. Правильная репроекция для любых CRS (UTM, Mercator, Custom)
2. `Transformer.transform(lon, lat)` — сквозной проброс во все CRS
3. `always_xy=True` — единый порядок (lon, lat) вместо (lat, lon) PROJ по-умолчанию

**Масштабирование:**
- Трансформер создаётся один раз → cached
- Batch transform: `.transform(lons.tolist(), lats.tolist())` — C-код, быстро
- Для 1860 гипотез: 1860 × 2 трансформации → <1ms

---

### 3.4 DEM / GeoTIFF

**Задача:** Цифровая модель рельефа — база данных высот.

**Copernicus GLO-30 Public DEM:**
- 30m resolution, глобальное покрытие
- Cloud-Optimized GeoTIFF (COG) — HTTP range requests, без скачивания целиком
- License: свободно (Copernicus Programme, CC BY 4.0-like)

**Почему GeoTIFF, а не:**

| Формат | Сравнение |
|---|---|
| **GeoTIFF (COG)** | Стандарт де-факто. Rioxarray открывает нативно. COG позволяет частичную загрузку. |
| **NetCDF** | Лучше для многомерных данных, но тяжелее для 2D DEM. |
| **HDF5** | Гибкий, но требует extra библиотек. |
| **TileDB / GeoParquet** | Новые форматы — незрелый Python экосистемный support для растров. |

**Преимущества GeoTIFF:**
1. Copernicus GLO-30 распространяется именно в COG
2. Rioxarray открывает напрямую
3. Сжатие (DEFLATE, LZW) — 30m tile ~30MB без сжатия, ~10MB со сжатием
4. COG overlay — можно загрузить только нужный bounding box

**Масштабирование:**
- 30m resolution → ~3600×3600 px на 1°×1° tile
- Для маршрута 25s × 60m/s = 1500m → окно 200 точек, область 2×2 км → ~70×70 px
- Текущий DEM 400×400 — 400 km² — с запасом
- На большие расстояния (100+ km) нужно multi-tile stitching или CDB (Oracle) масштабирование

---

## 4. Visualization

### 4.1 Plotly (`plotly>=6.0`)

**Задача:** Интерактивная визуализация terrain, trajectory, correlation, dashboard.

**Почему Plotly, а не:**

| Библиотека | Сравнение |
|---|---|
| **Plotly** | Интерактивный HTML (zoom, pan, hover). Работает в браузере. Python → HTML без сервера. |
| **Matplotlib** | Статичный PNG — нет интерактивности. 3D медленный. Отличный для papers, не для отладки. |
| **Bokeh** | Интерактивный, но сложнее API, меньше типов графиков (нет Surface 3D). |
| **Folium** | Только карты (Leaflet). Нет heatmap или profile. |
| **Kepler.gl** | Тяжёлый (React), только карты. Overkill. |
| **PyVista / Mayavi** | 3D-визуализация научных данных — избыточно. |

**Преимущества Plotly:**
1. `Surface + Scatter3d + Heatmap + Scatter` — все типы в одной библиотеке
2. `make_subplots` — 2×2 dashboard с разнотипными графиками
3. `plotly.io.write_html()` — самодостаточный HTML (все данные в JSON внутри)
4. Plotly Dark template — читаемо на проекторе
5. Hover info — дебаг correlation по каждой точке

**Масштабирование:**
- HTML-файлы: 4 графика → ~1-3 MB каждый (можно `auto_play=False` → меньше)
- Dashboard с Surface 3D → ~3-5 MB — тяжело для браузера
- Для >1000 точек trajectory → агрегировать (downsample до 200 точек)
- Для real-time dashboard: plotly не предназначен для real-time (<1s обновления) — нужен dash/websocket

---

## 5. Data Formats

### 5.1 NMEA 0183 (`pynmea2>=1.19`)

**Задача:** Парсинг/GPS-сообщений — радиовысотомер в формате $GPGGA.

**Почему NMEA, а не:**

| Формат | Сравнение |
|---|---|
| **NMEA 0183** | Стандарт для GNSS-приёмников, радиовысотомеров, АИС. Поддерживается pynmea2. Текстовый — читаемый. |
| **UBX (u-blox)** | Бинарный, компактный. Есть библиотеки (pyubx2). Не подходит для коммерческих высотомеров. |
| **RTCM** | Differential GNSS correction — избыточный. |
| **Custom binary** | Требует документации протокола — редкий сценарий. |
| **CSV/JSON** | Если данные с логгера — да, но в реальном времени NMEA исторически стандарт. |

**Преимущества NMEA + pynmea2:**
1. `pynmea2.parse()` — полный парсер с checksum, типом сообщения, всеми полями
2. Текстовый: можно читать `cat flight_log.nmea`, дебажить вручную
3. Checksum — защита от битых строк (используется в проекте)
4. Стандартный для COTS радиовысотомеров (FreeFlight, Honeywell, Trig)

**Масштабирование:**
- Одно сообщение ~80 байт, 10 Hz → ~800 байт/с → 2.9 MB/час
- Парсинг: `pynmea2` — Python, ~10μs/сообщение на MacBook, ~30μs на RPi
- Для >100 Hz нужен бинарный протокол

---

### 5.2 JSON

**Задача:** Конфигурация (`config.json`) и сериализация результатов (`estimates.json`).

**Почему JSON, а не:**

| Формат | Сравнение |
|---|---|
| **JSON** | Человеко-читаемый, стандарт для конфигов. Встроенный `json` module. |
| **YAML/TOML** | Для конфигов — читаемее (комментарии, многострочные). Но Python не built-in. |
| **HDF5** | Для результатов — эффективнее, но требует h5py. Overkill для 50-200 estimate-ов. |
| **Parquet** | Эффективный, columnar. Избыточен на данном этапе. |
| **SQLite** | Для логов полёта — хорошая альтернатива. Однофайловый, запросы, быстрый. |

**Преимущества JSON:**
1. `json.load / json.dump` — zero dependency
2. `Config.merge(json_dict)` — прямая интеграция с dataclass
3. Легко дебажить, передавать, логировать

**Масштабирование:**
- Для длительных полётов (часы → миллионы строк) JSON неэффективен.
- Альтернатива: SQLite для streaming логов, Parquet для анализа.

---

## 6. CLI / Dev Tools

### 6.1 Click (`click>=8.1`)

**Задача:** CLI entry point для команд `gagarin run`, `download-dem`, `analyze`.

**Почему Click, а не:**

| Библиотека | Сравнение |
|---|---|
| **Click** | Декораторы, автоматическая генерация `--help`, typed options. Минимум бойлерплейта. |
| **argparse** | Стандартная библиотека. Более многословен, нет автоматических групп. |
| **Typer** | Поверх Click + type hints. Современный, но ещё один dependency. |
| **Fire** | Автоматический CLI из любой функции. Непредсказуемые имена аргументов. |

**Преимущества Click:**
1. `@cli.group()` → subcommands (run, download-dem, analyze)
2. `@click.option`, `@click.argument` — декларативно, автоматический `--help`
3. `click.echo()` — colourised вывод?
4. Широко используется в индустрии

**Масштабирование:**
- Не влияет на runtime — только CLI dispatch

---

### 6.2 Pytest (`pytest>=8.0`)

**Задача:** Unit-тестирование ядра алгоритмов.

**Почему Pytest, а не:**

| Библиотека | Сравнение |
|---|---|
| **pytest** | `assert` вместо `self.assertEqual`, auto-discovery, fixtures, параметризация, маркеры. |
| **unittest** | Java-style boilerplate (class, self.assertEqual). Медленнее написание. |
| **doctest** | Тесты в docstring — для демонстрации, не для coverage. |

**Масштабирование:**
- 31 тест → <0.3s
- Параметризация `@pytest.mark.parametrize` легко расширяет coverage
- `pytest-benchmark` для performance regression тестов (задекларирован)

---

### 6.3 Hatchling

**Задача:** PEP 517 build backend, сборка wheel.

**Почему Hatchling, а не:**

| Инструмент | Сравнение |
|---|---|
| **hatchling** | Minimal build backend. PEP 621 (pyproject.toml metadata) из коробки. Нет external `setup.py`. |
| **setuptools** | Legacy. Требует `setup.py` или `setup.cfg`. Более тяжёлый. |
| **poetry** | Менеджер зависимостей + build. Тяжёлый для простого проекта. |
| **pdm** | PEP 582, современный, но ещё niche. |

**Преимущества Hatchling:**
1. `packages = ["gagarin"]` — вся конфигурация в pyproject.toml
2. PEP 621 compliant
3. Быстрая сборка (нет лишних плагинов)
4. `[project.scripts]` entry point

---

## 7. Others

### 7.1 Pandas (`pandas>=2.2`)

**Задача:** (задекларирован, не используется)

**Потенциальное применение:**
- Анализ логов полёта (DataFrame результатов)
- Feature engineering для оценки качества match

**Альтернатива:** Polars — быстрее, меньше memory, но моложе.
Для анализа результатов (≤10k строк) разница несущественна.

---

### 7.2 Requests (`requests>=2.32`)

**Задача:** HTTP-загрузка DEM tiles с S3 и geocoding с Nominatim.

**Почему requests, а не:**

| Библиотека | Сравнение |
|---|---|
| **requests** | Самый популярный HTTP client. Полный API (streaming, timeout, headers). |
| **urllib (stdlib)** | Низкоуровневый, неудобный. |
| **httpx** | Async support. Но для однократной загрузки tiles избыточен. |
| **aiohttp** | async/await — нужен event loop. Overkill. |

**Преимущества:**
1. `stream=True` — чанковая загрузка больших tile (~30 MB)
2. Timeout 300s для медленного S3
3. Простой API для Nominatim REST

---

### 7.3 Download Script (`download_dem.py`)

**Интеграция с Copernicus GLO-30 via S3:**
- https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com
- Tile: `Copernicus_DSM_COG_10_{tile_y}_00_{tile_x}_00_DEM`
- Nominatim для reverse geocoding (place name → coordinate)

**Проблема:** S3 timeout (~55% при лимите 120s). Copernicus S3 медленный для России/Азии.
**Альтернативы:**
- OpenTopography API (быстрее, но лимит запросов)
- NASA SRTM (3 arcsec, 90m resolution — хуже)
- NASADEM (30m, merged SRTM + other sources)

---

## Summary Table

| Компонент | Роль | Альтернатива(ы) | Ключевое преимущество | Масштабирование |
|---|---|---|---|---|
| **TERCOM** | core algorithm | SITAN, Particle Filter | Детерминизм, отсутствие начальной гипотезы | O(A×S×W), GPU-ready |
| **NCC** | similarity metric | MI, MSE | Нормирован, O(W) | O(W), векторизуется |
| **ESKF** | sensor fusion | EKF, UKF, PF | Точнее direct EKF, 6D | O(36) — negligible |
| **numpy** | numerics | JAX, CuPy | Экосистема, ARM64, BLAS | Векторизация |
| **rioxarray** | GeoTIFF I/O | rasterio, GDAL | Xarray-native, простота | Chunk via dask |
| **xarray** | labeled arrays | pandas, numpy | Координаты, alignment | Dask → out-of-core |
| **pyproj** | reprojection | GDAL OSR | Pythonic API | Batch C transform |
| **plotly** | viz | matplotlib, bokeh | Интерактивный HTML, 3D + Heatmap | Dashboard ~5MB |
| **pynmea2** | NMEA parser | custom parser | Checksum, GGA parsing | ~10μs/msg |
| **click** | CLI | argparse, typer | Группы, авто-help | Dispatch only |
| **pytest** | testing | unittest | assert, auto-discovery | 0.3s/31 tests |
| **hatchling** | build | setuptools, poetry | PEP 621, minimal | N/A |
| **requests** | HTTP | httpx, urllib | streaming, timeout | Однократный download |

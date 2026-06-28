# Примеры для третьего чекпоинта

Набор тестовых данных для проверки TERCOM-навигации через веб-интерфейс.

## Как использовать

1. Запустите сервер: `uvicorn simulation_ui.main:app --reload`
2. Откройте `http://localhost:8000/checkpoint`
3. Выберите пример из папок ниже
4. Загрузите DEM (файл `.tif` указан в `params.txt`) и высоты (`altitudes.txt`)
5. Введите параметры из `params.txt`
6. Нажмите «Запустить»

## Примеры

| № | Папка | DEM | Формат | Описание |
|---|-------|-----|--------|----------|
| 1 | `01_kamchatka_pixel` | synthetic_kamchatka.tif | pixel | Плавный рельеф, низкий шум |
| 2 | `02_kamchatka_pixel_noisy` | synthetic_kamchatka.tif | pixel | Высокий шум + скорость |
| 3 | `03_dramatic_kamchatka_pixel` | dramatic_kamchatka.tif | pixel | Вулканы, сильный рельеф |
| 4 | `04_caucasus_geo` | caucasus.tif | geo | Кавказские пики, азимут на север |
| 5 | `05_crimea_geo` | crimea.tif | geo | Гребень + море |
| 6 | `06_altai_pixel` | altai.tif | pixel | Плато + пики |
| 7 | `07_ural_pixel` | ural.tif | pixel | Пологий хребет |
| 8 | `08_sakhalin_pixel` | sakhalin.tif | pixel | Остров + сопки |

## Структура примера

```
01_kamchatka_pixel/
├── altitudes.txt    # Барометрические высоты (одна на строку)
└── params.txt       # Параметры для формы (DEM, start, azimuth, speed...)
```

## Примечания

- Все DEM находятся в `data/dem/`
- Примеры с geo-координатами требуют переключения формата на «Гео (lat, lon)»
- Точность TERCOM зависит от рельефа: на драматичной Камчатке корреляция выше

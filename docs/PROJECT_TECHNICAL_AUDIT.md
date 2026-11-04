# PersonaRec — Full Technical Audit & Diagnostic Report

## 1. Общая архитектура проекта

PersonaRec — веб-приложение на Flask для поиска похожих аниме и персональных рекомендаций.
Основной алгоритм — user-based Collaborative Filtering с косинусным сходством на центрированных оценках.
Источник данных — Kaggle Anime Dataset (`anime.csv`, `rating.csv`). Интеграция AniList добавлена отдельным пакетом `anilist/`
и не меняет исходный датасет и baseline `stand 0.3` (MAE 0.912, RMSE 1.204).

### Основные компоненты
- `app.py` — Flask application и все маршруты.
- `services/` — бизнес-логика поиска, каталога, рекомендаций.
- `recommendations/` — математика сходства.
- `anilist/` — сбор, обработка, сопоставление и нормализация данных AniList.
- `scripts/` — CLI-скрипты запуска пайплайна и валидации.
- `templates/`, `static/` — UI.
- `data/raw/` — исходные CSV Kaggle.
- `data/anilist/` — отдельное хранилище AniList-данных.
- `tests/` — unit-тесты AniList-компонентов.

## 2. Дерево проекта

```text
Personal.rec_web/
├── app.py
├── requirements.txt
├── render.yaml
├── README.md
├── .gitignore
├── .env.example
├── anilist/
│   ├── __init__.py
│   ├── client.py
│   ├── storage.py
│   ├── collect_catalog.py
│   ├── collect_users.py
│   ├── mapping.py
│   ├── normalize.py
│   └── pipeline.py
├── services/
│   ├── anime_search.py
│   ├── anime_catalog.py
│   ├── recommendation_service.py
│   └── hybrid_recommendation.py
├── recommendations/
│   └── similarity.py
├── scripts/
│   ├── run_anilist_collect.py
│   └── validate_anilist_dataset.py
├── tests/
│   ├── test_normalize.py
│   ├── test_mapping.py
│   ├── test_mapping_build.py
│   └── test_reliability.py
├── templates/
├── static/
├── data/
│   ├── raw/
│   │   └── anime.csv
│   └── anilist/
└── docs/
```

## 3. Назначение модулей

### Точка входа и маршруты
- `app.py` — создаёт Flask app, определяет все маршруты, обращается к AniList через `requests`, использует сервисы.

### Сервисы
- `services/anime_search.py` — поиск аниме через AniList GraphQL (`search_anime`).
- `services/anime_catalog.py` — получение MAL ID по AniList ID и карточек по MAL ID (`get_mal_id_by_anilist_id`, `get_anime_by_mal_ids`).
- `services/recommendation_service.py` — поиск похожих аниме по жанровым TF-IDF векторам (`find_similar_anime`).
- `services/hybrid_recommendation.py` — загрузка профилей и гибридные рекомендации (`load_profiles`, `recommend_for_user`).

### Рекомендательное ядро
- `recommendations/similarity.py` — `cosine_similarity` с центрированием по среднему.

### AniList integration
- `anilist/client.py` — GraphQL-клиент с throttling/retry.
- `anilist/storage.py` — CSV storage, checkpoint, upsert/dedupe.
- `anilist/collect_catalog.py` — сбор каталога по ID-батчам.
- `anilist/collect_users.py` — сбор пользовательских списков, enumeration.
- `anilist/mapping.py` — сопоставление Kaggle ↔ AniList.
- `anilist/normalize.py` — нормализация оценок.
- `anilist/pipeline.py` — оркестрация CLI.

### Тесты
- `tests/test_normalize.py`, `tests/test_mapping.py`, `tests/test_mapping_build.py`, `tests/test_reliability.py`.

## 4. Архитектура рекомендательной системы

### 4.1. Загрузка данных
`services/hybrid_recommendation.py::load_profiles()`:
- Читает `rating.csv` и `anime.csv` из `_data_dir()` (env `PERSONAL_REC_DATA_DIR` или `data/raw`).
- Фильтрует `rating != -1`.
- Фильтрует пользователей с числом оценок < `MIN_USER_RATINGS` (50).
- Фильтрует аниме с числом оценок < `MIN_ANIME_RATINGS` (30).
- Формирует `profiles: dict[user_id, dict[anime_id, rating]]`, `anime` DataFrame по популярным аниме, `item_users: dict[anime_id, set[user_id]]`.

### 4.2. Cosine similarity
`recommendations/similarity.py::cosine_similarity`:
- На общих item'ах вычисляет средние оценок пользователя, центрирует, считает косинус.

### 4.3. Поиск соседей и рекомендация
`services/hybrid_recommendation.py::recommend_for_user`:
- Берёт профиль target.
- Кандидаты — пользователи, оценившие общие аниме.
- Требует `len(common) >= 3`.
- `similarity >= MIN_SIMILARITY` (0.3).
- Сортирует, берёт до 50 соседей.
- Предсказывает оценки для непросмотренных аниме.
- Возвращает список с `predicted_rating`, `supporters`, `prediction_source`.

### 4.4. Похожие аниме (content-based)
`services/recommendation_service.py::find_similar_anime`:
- Строит TF-IDF жанровые векторы по `data/raw/anime.csv`.
- Исключает сиквелы/франшизы по названию.
- Возвращает список похожих с `match_percent`.

## 5. Схема идентификаторов

- Kaggle `anime_id` = MAL ID.
- AniList `idMal` = MAL ID.
- AniList `id` = AniList ID.
- User ID из Kaggle = числовой идентификатор пользователя в `rating.csv`.
- Внутренних БД нет.

Связи:
- `Kaggle anime_id ↔ MAL ID ↔ AniList.idMal ↔ AniList.id` (через mapping).
- Flask `/anime/<anilist_id>` использует AniList ID.
- `/api/similar` использует MAL ID (или получает его из AniList ID).
- Рекомендательный алгоритм использует Kaggle `anime_id` (MAL ID).

## 6. Интеграция AniList

Путь данных:
AniList API → `anilist/client.py` → `collect_catalog.py`/`collect_users.py` → `data/anilist/raw/*.csv` → `mapping.py` → `normalize.py` → `data/anilist/processed/*.csv`.

Важно: AniList-данные **не используются** рекомендательным алгоритмом `hybrid_recommendation.py` или `recommendation_service.py`. Они используются только для каталога/поиска/отображения.

## 7. Диагностика проблемы с соседями

Проблема: для аниме, добавленных из AniList, не находятся соседи.

Анализ кода:
- `find_similar_anime` работает только с `data/raw/anime.csv` (Kaggle). AniList-аниме не попадают в `_genre_vectors()`.
- `recommend_for_user` использует Kaggle `anime_id`. AniList-аниме не представлены в `profiles`/`item_users`, если нет mapping и импорта взаимодействий.
- Новые аниме не проходят фильтрацию по минимальному количеству оценок, так как отсутствуют в `rating.csv`.

Вывод: AniList-аниме не участвуют в similarity, так как алгоритм полностью основан на Kaggle dataset.

Дополнительная диагностика на реальных данных невозможна: `rating.csv` отсутствует, AniList-данные не собраны.

## 8. Состояние проекта

- Python 3.12.14
- Flask 3.1.3
- pandas 2.3.3
- requests 2.32.5
- rapidfuzz 3.14.6
- `requirements.txt`, `.env.example`, `docs/` присутствуют.
- Базы данных нет (CSV-файлы).
- Переменные окружения: `PERSONAL_REC_DATA_DIR`, `PERSONAL_REC_ANILIST_DIR`, `ANILIST_*`.

## 9. Flask маршруты

- `/` — главная.
- `/health` — health check.
- `/api/anime?q=` — автодополнение AniList.
- `/api/similar?mal_id=` — похожие аниме.
- `/api/recommendations?user_id=&limit=` — персональные рекомендации.
- `/anime/<anilist_id>` — страница аниме.
- `/register`, `/search` — страницы.

## 10. Тестирование

Существующие тесты:
- `tests/test_normalize.py` (10)
- `tests/test_mapping.py` (6)
- `tests/test_mapping_build.py` (9)
- `tests/test_reliability.py` (3)

Все 28 тестов проходят (mock-данные). Реальные данные не используются.

Не покрыто:
- Flask routes
- `recommendation_service`
- `hybrid_recommendation`
- End-to-end интеграция

## 11. Известные ограничения

- `rating.csv` отсутствует в репозитории.
- AniList-данные не собраны.
- AniList-аниме не участвуют в рекомендациях.
- Нет базы данных.
- Нет авторизации/регистрации (только страница).

## 12. Файлы, потенциально требующие изменений

- `services/recommendation_service.py` — добавление AniList-аниме в жанровые векторы.
- `services/hybrid_recommendation.py` — интеграция AniList-взаимодействий.
- `anilist/mapping.py` — использование mapping в рекомендациях.
- `app.py` — маршруты для новых данных.

## 13. Резюме

- Работает: Flask-сайт, поиск AniList, похожие аниме по Kaggle, тесты AniList.
- Реализовано, но не проверено: сбор AniList, mapping, normalization.
- Не работает: участие AniList-аниме в рекомендациях.
- Подтверждённые проблемы: отсутствие AniList-аниме в similarity-матрице.
- Гипотезы: mapping не используется рекомендациями; AniList ID не конвертируются в Kaggle ID в алгоритме.
- Первичная проверка: убедиться, что mapping существует и используется в `recommendation_service`/`hybrid_recommendation`.

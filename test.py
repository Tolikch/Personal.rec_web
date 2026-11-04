import pandas as pd

ratings = pd.read_parquet(
    "data/anilist/ratings.parquet"
)

print("Всего записей:", len(ratings))
print("Пользователей:", ratings["user_id"].nunique())
print("Аниме:", ratings["anilist_id"].nunique())

print(
    "Дубликаты:",
    ratings.duplicated(
        ["user_id", "anilist_id"]
    ).sum()
)

print(ratings.head())
print(ratings.describe())
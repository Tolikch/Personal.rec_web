from services.anime_search import search_anime


queries = [
    "Атака титанов",
    "Тетрадь смерти",
    "Naruto",
    "Shingeki no Kyojin"
]

for query in queries:
    print(f"\nПоиск: {query}")

    results = search_anime(query)

    if not results:
        print("Результатов нет.")
        continue

    for anime in results:
        print(
            f"- {anime['title']} | "
            f"English: {anime['title_english']} | "
            f"ID: {anime['mal_id']}"
        )
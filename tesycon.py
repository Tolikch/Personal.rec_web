import requests

URL = "https://graphql.anilist.co"

QUERY = """
query ($search: String) {
    Media(search: $search, type: ANIME) {
        id
        title {
            romaji
            english
            native
        }
        synonyms
        coverImage {
            medium
        }
    }
}
"""

search_terms = [
    "Атака титанов",
    "Тетрадь смерти",
    "Наруто",
    "Death Note"
]

for term in search_terms:
    print(f"\nПоиск: {term}")

    try:
        response = requests.post(
            URL,
            json={
                "query": QUERY,
                "variables": {"search": term}
            },
            timeout=15
        )

        response.raise_for_status()
        data = response.json()

        anime = data.get("data", {}).get("Media")

        if not anime:
            print("Аниме не найдено.")
            continue

        titles = anime["title"]

        print("ID:", anime["id"])
        print("Название:", titles.get("romaji"))
        print("Английское:", titles.get("english"))
        print("Японское:", titles.get("native"))
        print("Совпадение:", term in anime.get("synonyms", []))

    except requests.RequestException as error:
        print("Ошибка запроса:", error)
    except (KeyError, TypeError, ValueError) as error:
        print("Ошибка обработки ответа:", error)
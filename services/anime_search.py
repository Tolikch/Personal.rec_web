import requests

API_URL = "https://graphql.anilist.co"

SEARCH_QUERY = """
query ($search: String) {
    Page(perPage: 10) {
        media(search: $search, type: ANIME, sort: SEARCH_MATCH) {
            id
            idMal
            title {
                romaji
                english
                native
            }
            synonyms
            coverImage {
                medium
            }
            seasonYear
            episodes
            averageScore
            genres
        }
    }
}
"""


def search_anime(query):
    query = query.strip()

    if len(query) < 2:
        return []

    response = requests.post(
        API_URL,
        json={
            "query": SEARCH_QUERY,
            "variables": {"search": query}
        },
        timeout=15
    )

    response.raise_for_status()

    data = response.json()
    media = data.get("data", {}).get("Page", {}).get("media", [])

    results = []

    for anime in media:
        title = anime.get("title") or {}

        results.append({
            "id": anime.get("id"),
            "mal_id": anime.get("idMal"),
            "title": title.get("english") or title.get("romaji"),
            "title_romaji": title.get("romaji"),
            "title_english": title.get("english"),
            "title_native": title.get("native"),
            "synonyms": anime.get("synonyms") or [],
            "image": (anime.get("coverImage") or {}).get("medium"),
            "year": anime.get("seasonYear"),
            "episodes": anime.get("episodes"),
            "score": anime.get("averageScore"),
            "genres": anime.get("genres") or []
        })

    return results
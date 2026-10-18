import requests


API_URL = "https://graphql.anilist.co"

RECOMMENDATION_QUERY = """
query ($ids: [Int]) {
    Page(perPage: 30) {
        media(idMal_in: $ids, type: ANIME) {
            id
            idMal
            title { romaji english native }
            coverImage { large }
            seasonYear
            averageScore
            genres
        }
    }
}
"""

ANIME_ID_QUERY = """
query ($id: Int) {
    Media(id: $id, type: ANIME) {
        id
        idMal
    }
}
"""


def get_mal_id_by_anilist_id(anilist_id):
    response = requests.post(
        API_URL,
        json={
            "query": ANIME_ID_QUERY,
            "variables": {"id": int(anilist_id)},
        },
        timeout=15,
    )
    response.raise_for_status()
    media = response.json().get("data", {}).get("Media") or {}
    return media.get("idMal")


def get_anime_by_mal_ids(anime_ids):
    anime_ids = [int(anime_id) for anime_id in anime_ids[:30]]
    if not anime_ids:
        return {}

    response = requests.post(
        API_URL,
        json={"query": RECOMMENDATION_QUERY, "variables": {"ids": anime_ids}},
        timeout=20,
    )
    response.raise_for_status()
    media = response.json().get("data", {}).get("Page", {}).get("media", [])
    return {int(anime["idMal"]): anime for anime in media if anime.get("idMal")}

from flask import Flask, render_template, request, redirect, url_for
from flask import jsonify
from services.anime_search import search_anime
from services.hybrid_recommendation import load_profiles, recommend_for_user
from services.recommendation_service import find_similar_anime
from services.anime_catalog import get_anime_by_mal_ids, get_anime_by_anilist_ids, get_mal_id_by_anilist_id
from services.content_similarity import find_similar_items
import requests
app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok"})

@app.route("/api/anime")
def anime_autocomplete():
    query = request.args.get("q", "").strip()

    if len(query) < 2:
        return jsonify({"results": []})

    try:
        results = search_anime(query)
        return jsonify({"results": results})

    except requests.RequestException:
        return jsonify({
            "results": [],
            "error": "Не удалось подключиться к каталогу аниме."
        }), 503

@app.route("/api/recommendations")
def recommendations():
    raw_user_id = request.args.get("user_id", "").strip()
    if not raw_user_id.isdigit():
        return jsonify({"error": "Укажи числовой user_id из набора Personal.Rec."}), 400

    try:
        profiles, anime, item_users = load_profiles()
        results = recommend_for_user(
            int(raw_user_id), profiles, anime, item_users,
            limit=request.args.get("limit", 10),
        )
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 503
    except (ValueError, TypeError):
        return jsonify({"error": "Параметр limit должен быть числом."}), 400

    if results is None:
        return jsonify({"error": "Пользователь не найден или не прошёл фильтрацию."}), 404
    return jsonify({
        "user_id": int(raw_user_id),
        "results": results,
        "model": "hybrid_user_based",
    })


def _fetch_seed_media(anilist_id=None, mal_id=None):
    # Try to fetch richer metadata from AniList for the seed.
    if anilist_id and str(anilist_id).isdigit():
        try:
            response = requests.post(
                "https://graphql.anilist.co",
                json={"query": "query ($id: Int) { Media(id: $id, type: ANIME) { id idMal title { romaji english native } synonyms description(asHtml:false) coverImage { large } seasonYear episodes averageScore genres format } }",
                      "variables": {"id": int(anilist_id)}},
                timeout=15,
            )
            response.raise_for_status()
            media = response.json().get("data", {}).get("Media")
            if media:
                return media
        except requests.RequestException:
            pass
    if mal_id and str(mal_id).isdigit():
        try:
            response = requests.post(
                "https://graphql.anilist.co",
                json={"query": "query ($ids: [Int]) { Page(perPage: 1) { media(idMal_in: $ids, type: ANIME) { id idMal title { romaji english native } synonyms description(asHtml:false) coverImage { large } seasonYear episodes averageScore genres format } } }",
                      "variables": {"ids": [int(mal_id)]}},
                timeout=15,
            )
            response.raise_for_status()
            media_list = response.json().get("data", {}).get("Page", {}).get("media", [])
            if media_list:
                return media_list[0]
        except requests.RequestException:
            pass
    return None


def _recommendation_cards(anilist_id=None, mal_id=None):
    seed_media = _fetch_seed_media(anilist_id=anilist_id, mal_id=mal_id)
    # If seed not found in AniList but mal_id known, try unified catalog item id.
    seed = seed_media if seed_media else (int(mal_id) if mal_id and str(mal_id).isdigit() else None)
    if seed is None:
        return [], "Не удалось получить данные выбранного аниме."

    recommendation_rows = find_similar_items(seed, limit=12)
    if not recommendation_rows:
        return [], "Похожие аниме не найдены."

    # Fetch AniList cards for results.
    mal_ids = [r["mal_id"] for r in recommendation_rows if r.get("mal_id")]
    anilist_ids = [r["anilist_id"] for r in recommendation_rows if r.get("anilist_id") and not r.get("mal_id")]
    anime_by_mal = get_anime_by_mal_ids(mal_ids) if mal_ids else {}
    anime_by_anilist = get_anime_by_anilist_ids(anilist_ids) if anilist_ids else {}

    cards = []
    for recommendation in recommendation_rows:
        anime = None
        if recommendation.get("mal_id") and recommendation["mal_id"] in anime_by_mal:
            anime = anime_by_mal[recommendation["mal_id"]]
        elif recommendation.get("anilist_id") and recommendation["anilist_id"] in anime_by_anilist:
            anime = anime_by_anilist[recommendation["anilist_id"]]
        if not anime:
            # fallback: use recommendation metadata
            cards.append({
                **recommendation,
                "anilist_id": recommendation.get("anilist_id"),
                "title": recommendation.get("title"),
                "image": None,
                "year": recommendation.get("year"),
                "score": None,
                "genres": [],
            })
            continue
        title = anime.get("title") or {}
        cards.append({
            **recommendation,
            "anilist_id": anime.get("id"),
            "title": title.get("english") or title.get("romaji") or recommendation.get("title"),
            "image": (anime.get("coverImage") or {}).get("large"),
            "year": anime.get("seasonYear"),
            "score": round(anime["averageScore"] / 10, 1) if anime.get("averageScore") is not None else None,
            "genres": anime.get("genres") or [],
        })

    message = None if cards else "AniList не вернул карточки для найденных рекомендаций."
    return cards, message


@app.route("/api/similar")
def similar_anime_api():
    mal_id = request.args.get("mal_id", "").strip()
    anime_id = request.args.get("anime_id", "").strip()

    try:
        if not mal_id.isdigit() and anime_id.isdigit():
            mal_id = str(get_mal_id_by_anilist_id(anime_id) or "")
        cards, message = _recommendation_cards(anilist_id=anime_id, mal_id=mal_id)
    except FileNotFoundError as error:
        return jsonify({"error": str(error)}), 503
    except requests.RequestException as error:
        app.logger.error("Ошибка запроса рекомендаций: %s", error)
        return jsonify({"error": "AniList временно недоступен. Попробуй ещё раз."}), 503

    return jsonify({"mal_id": int(mal_id), "results": cards, "message": message})

@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/search", methods=["GET"])
def search():
    anime_name = request.args.get("anime", "").strip()
    mode = request.args.get("mode", "similar")
    anime_id = request.args.get("anime_id", "").strip()
    mal_id = request.args.get("mal_id", "").strip()

    if not anime_name:
        return redirect(url_for("index"))

    if mode == "collection":
        return redirect(url_for("register"))

    try:
        if not mal_id.isdigit() and anime_id.isdigit():
            mal_id = get_mal_id_by_anilist_id(anime_id)
        anime_cards, message = _recommendation_cards(anilist_id=anime_id, mal_id=mal_id)
    except FileNotFoundError as error:
        anime_cards = []
        message = str(error)
    except requests.RequestException as error:
        app.logger.error("Ошибка загрузки данных из AniList: %s", error)
        anime_cards = []
        message = "Не удалось загрузить данные из AniList. Проверь соединение и попробуй снова."

    return render_template(
        "index.html",
        anime_name=anime_name,
        search_performed=True,
        recommendations=anime_cards,
        recommendation_message=message,
    )

@app.route("/anime/<int:anime_id>")
def anime_detail(anime_id):
    query = """
query ($id: Int) {

    Media(id: $id, type: ANIME) {

        id

        idMal

        title {

            romaji

            english

            native

        }

        synonyms

        description(asHtml: false)

        coverImage {

            large

            extraLarge

        }

        bannerImage

        seasonYear

        episodes

        averageScore

        genres

        status

        format

    }

}

"""

    try:
        response = requests.post(
            "https://graphql.anilist.co",
            json={
                "query": query,
                "variables": {"id": anime_id}
            },
            timeout=15
        )
        response.raise_for_status()

        data = response.json()
        anime = data.get("data", {}).get("Media")

        if anime:
            titles = anime.get("title", {})

            russian_title = next(
                (
                    title for title in anime.get("synonyms", [])
                    if any("\u0400" <= char <= "\u04FF" for char in title)
                ),
                None
            )

            anime["display_title"] = (
                    russian_title
                    or titles.get("english")
                    or titles.get("romaji")
                    or titles.get("native")
                    or "Неизвестное аниме"
            )

            if anime.get("averageScore") is not None:
                anime["averageScoreOutOf10"] = round(
                    anime["averageScore"] / 10, 1
                )

        if anime:
            titles = [
                anime.get("title", {}).get("native"),
                anime.get("title", {}).get("english"),
                anime.get("title", {}).get("romaji")
            ]

            russian_title = next(
                (
                    title for title in anime.get("synonyms", [])
                    if any("\u0400" <= char <= "\u04FF" for char in title)
                ),
                None
            )

            anime["display_title"] = russian_title or next(
                (title for title in titles if title),
                "Неизвестное аниме"
            )
        if not anime:
            return render_template("404.html"), 404

        return render_template("anime.html", anime=anime)

    except requests.RequestException as error:
        app.logger.error("Ошибка загрузки аниме: %s", error)
        return render_template("anime_error.html"), 503


if __name__ == "__main__":
    app.run(debug=True)

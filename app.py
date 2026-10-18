from flask import Flask, render_template, request, redirect, url_for
from flask import jsonify
from services.anime_search import search_anime
from services.hybrid_recommendation import load_profiles, recommend_for_user
from services.recommendation_service import find_similar_anime
from services.anime_catalog import get_anime_by_mal_ids, get_mal_id_by_anilist_id
import requests
app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html")

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


def _recommendation_cards(mal_id):
    recommendation_rows = find_similar_anime(mal_id)
    if recommendation_rows is None:
        return [], "Выбранное аниме отсутствует в каталоге алгоритма."

    anime_by_mal_id = get_anime_by_mal_ids(
        [item["mal_id"] for item in recommendation_rows]
    )
    cards = []
    for recommendation in recommendation_rows:
        anime = anime_by_mal_id.get(recommendation["mal_id"])
        if not anime:
            continue
        title = anime.get("title") or {}
        cards.append({
            **recommendation,
            "anilist_id": anime.get("id"),
            "title": title.get("english") or title.get("romaji") or recommendation["title"],
            "image": (anime.get("coverImage") or {}).get("large"),
            "year": anime.get("seasonYear"),
            "score": round(anime["averageScore"] / 10, 1)
            if anime.get("averageScore") is not None else None,
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
        if not mal_id.isdigit():
            return jsonify({"error": "Не удалось определить MAL ID выбранного аниме."}), 400
        cards, message = _recommendation_cards(mal_id)
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
        if not mal_id.isdigit():
            if not anime_id.isdigit():
                return redirect(url_for("index"))
            mal_id = get_mal_id_by_anilist_id(anime_id)
        if not mal_id:
            return render_template(
                "index.html",
                anime_name=anime_name,
                search_performed=True,
                recommendations=[],
                recommendation_message=(
                    "Для этого тайтла AniList не указал MAL ID, "
                    "поэтому алгоритм каталога не может найти похожие аниме."
                ),
            )

        anime_cards, message = _recommendation_cards(mal_id)
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

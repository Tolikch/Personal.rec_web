from flask import Flask, render_template, request, redirect, url_for
from flask import jsonify
from services.anime_search import search_anime
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

@app.route("/register")
def register():
    return render_template("register.html")


@app.route("/search", methods=["GET"])
def search():
    anime_name = request.args.get("anime", "").strip()
    mode = request.args.get("mode", "similar")

    if not anime_name:
        return redirect(url_for("index"))

    if mode == "collection":
        return redirect(url_for("register"))

    return render_template(
        "index.html",
        anime_name=anime_name,
        search_performed=True
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

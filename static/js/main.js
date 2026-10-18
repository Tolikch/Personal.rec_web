document.addEventListener("DOMContentLoaded", () => {
    const searchForm = document.getElementById("search-form");
    const animeInput = document.getElementById("anime-input");
    const animeResults = document.getElementById("anime-results");
    const animeId = document.getElementById("anime-id");
    const malId = document.getElementById("mal-id");
    const searchHint = document.getElementById("search-hint");
    let recommendationOutput = document.getElementById("recommendation-output");

    if (!recommendationOutput && searchForm) {
        recommendationOutput = document.createElement("div");
        recommendationOutput.id = "recommendation-output";
        recommendationOutput.setAttribute("aria-live", "polite");
        searchForm.insertAdjacentElement("afterend", recommendationOutput);

        searchForm.parentElement
            .querySelectorAll(":scope > .search-message, :scope > .recommendation-grid")
            .forEach(element => recommendationOutput.appendChild(element));
    }

    if (!searchForm || !animeInput || !animeResults || !animeId || !malId || !searchHint || !recommendationOutput) {
        console.error("Personal.Rec: необходимые элементы поиска не найдены.");
        return;
    }

    let debounceTimer;
    let controller;

    function hideResults() {
        animeResults.classList.remove("visible");
        animeResults.replaceChildren();
    }

    function showRecommendationMessage(message) {
        recommendationOutput.replaceChildren();
        const notice = document.createElement("div");
        notice.className = "search-message recommendation-notice";
        notice.textContent = message;
        recommendationOutput.appendChild(notice);
    }

    function createRecommendationCard(anime) {
        const link = document.createElement("a");
        link.className = "recommendation-card";
        link.href = `/anime/${encodeURIComponent(anime.anilist_id)}`;

        const poster = document.createElement("div");
        poster.className = "recommendation-poster";
        if (anime.image) {
            const image = document.createElement("img");
            image.src = anime.image;
            image.alt = `Постер ${anime.title}`;
            image.loading = "lazy";
            poster.appendChild(image);
        } else {
            const placeholder = document.createElement("div");
            placeholder.className = "recommendation-poster-placeholder";
            placeholder.textContent = "Нет постера";
            poster.appendChild(placeholder);
        }

        const badge = document.createElement("span");
        badge.className = "match-badge";
        badge.textContent = `Вероятность понравиться: ${anime.match_percent}%`;
        poster.appendChild(badge);

        const info = document.createElement("div");
        info.className = "recommendation-card-info";
        const title = document.createElement("h3");
        title.textContent = anime.title;
        info.appendChild(title);

        const meta = document.createElement("div");
        meta.className = "recommendation-card-meta";
        if (anime.year) {
            const year = document.createElement("span");
            year.textContent = anime.year;
            meta.appendChild(year);
        }
        if (anime.score) {
            const score = document.createElement("span");
            score.textContent = `★ ${Number(anime.score).toFixed(1)}/10`;
            meta.appendChild(score);
        }
        info.appendChild(meta);

        const track = document.createElement("div");
        track.className = "match-track";
        track.setAttribute("aria-label", `Сходство ${anime.match_percent} процентов`);
        const fill = document.createElement("span");
        fill.style.width = `${anime.match_percent}%`;
        track.appendChild(fill);
        info.appendChild(track);

        if (anime.genres && anime.genres.length) {
            const genres = document.createElement("p");
            genres.className = "recommendation-genres";
            genres.textContent = anime.genres.join(" · ");
            info.appendChild(genres);
        }

        link.append(poster, info);
        return link;
    }

    function renderRecommendations(data, seedName) {
        recommendationOutput.replaceChildren();

        const summary = document.createElement("div");
        summary.className = "search-message";
        const heading = document.createElement("h2");
        heading.textContent = "Похожие аниме";
        const selected = document.createElement("p");
        selected.append("Алгоритм сравнил жанры для: ");
        const strong = document.createElement("strong");
        strong.textContent = seedName;
        selected.appendChild(strong);
        const explanation = document.createElement("p");
        explanation.textContent = "Процент показывает оценку алгоритма, насколько вероятно, что аниме тебе понравится.";
        summary.append(heading, selected, explanation);
        recommendationOutput.appendChild(summary);

        if (data.message || !data.results || data.results.length === 0) {
            const notice = document.createElement("div");
            notice.className = "search-message recommendation-notice";
            notice.textContent = data.message || "Похожие аниме не найдены.";
            recommendationOutput.appendChild(notice);
            return;
        }

        const grid = document.createElement("section");
        grid.className = "recommendation-grid";
        grid.setAttribute("aria-label", "Похожие аниме");
        data.results.forEach(anime => grid.appendChild(createRecommendationCard(anime)));
        recommendationOutput.appendChild(grid);
    }

    function showMessage(message) {
        animeResults.replaceChildren();

        const element = document.createElement("div");
        element.className = "anime-results-message";
        element.textContent = message;

        animeResults.appendChild(element);
        animeResults.classList.add("visible");
    }

    function createAnimeResult(anime) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "anime-result";

        const image = document.createElement("img");
        image.alt = "";
        image.loading = "lazy";

        if (anime.image) {
            image.src = anime.image;
        }

        const info = document.createElement("div");
        info.className = "anime-result-info";

        const title = document.createElement("div");
        title.className = "anime-result-title";
        title.textContent =
            anime.title_english ||
            anime.title_romaji ||
            anime.title ||
            "Без названия";

        const meta = document.createElement("div");
        meta.className = "anime-result-meta";

        const details = [];

        if (anime.year) details.push(anime.year);
        if (anime.episodes) details.push(`${anime.episodes} эп.`);
        if (anime.score) details.push(`Оценка ${(anime.score / 10).toFixed(1)}/10`);

        meta.textContent = details.join(" · ") || "Аниме";

        info.append(title, meta);
        button.append(image, info);

        button.addEventListener("click", () => {
            animeInput.value = anime.title_english || anime.title_romaji || anime.title || "";
            animeId.value = anime.id || "";
            malId.value = anime.mal_id || "";
            searchHint.textContent = malId.value
                ? "Аниме выбрано. Теперь нажми «Найти»."
                : "У этого тайтла нет MAL ID, поэтому найти похожие аниме не получится.";
            hideResults();
        });

        return button;
    }

    async function loadAnime(query) {
        if (controller) {
            controller.abort();
        }

        controller = new AbortController();
        showMessage("Ищем аниме...");

        try {
            const response = await fetch(
                `/api/anime?q=${encodeURIComponent(query)}`,
                { signal: controller.signal }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || "Ошибка поиска");
            }

            if (animeInput.value.trim() !== query) {
                return;
            }

            animeResults.replaceChildren();

            if (!data.results || data.results.length === 0) {
                showMessage("Ничего не найдено. Попробуй другое название.");
                return;
            }

            data.results.forEach(anime => {
                animeResults.appendChild(createAnimeResult(anime));
            });

            animeResults.classList.add("visible");

        } catch (error) {
            if (error.name === "AbortError") return;

            console.error("Ошибка поиска аниме:", error);
            showMessage("Не удалось загрузить результаты. Попробуй ещё раз.");
        }
    }

    animeInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        animeId.value = "";
        malId.value = "";
        recommendationOutput.replaceChildren();
        searchHint.textContent = "Введи название, выбери аниме из списка, затем нажми «Найти».";

        const query = animeInput.value.trim();

        if (query.length < 2) {
            hideResults();
            return;
        }

        debounceTimer = setTimeout(() => {
            loadAnime(query);
        }, 400);
    });

    searchForm.addEventListener("submit", event => {
        const selectedMode = searchForm.querySelector('input[name="mode"]:checked')?.value;
        if (selectedMode === "collection") {
            return;
        }

        event.preventDefault();
        if (!animeInput.value.trim()) {
            animeInput.focus();
            return;
        }

        if (!animeId.value) {
            showMessage("Выбери аниме из списка результатов.");
            return;
        }

        if (!malId.value) {
            showMessage("Для этого тайтла отсутствует MAL ID. Выбери другой результат.");
            return;
        }

        const submitButton = searchForm.querySelector('button[type="submit"]');
        const oldButtonText = submitButton.innerText;
        submitButton.disabled = true;
        submitButton.textContent = "Ищем…";
        showRecommendationMessage("Подбираем похожие аниме…");

        const params = new URLSearchParams({
            mal_id: malId.value,
            anime_id: animeId.value,
        });

        fetch(`/api/similar?${params.toString()}`)
            .then(async response => {
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || "Не удалось выполнить поиск.");
                }
                return data;
            })
            .then(data => renderRecommendations(data, animeInput.value.trim()))
            .catch(error => showRecommendationMessage(error.message || "Не удалось выполнить поиск. Попробуй ещё раз."))
            .finally(() => {
                submitButton.disabled = false;
                submitButton.textContent = oldButtonText;
            });
    });

    document.addEventListener("click", event => {
        if (
            !animeResults.contains(event.target) &&
            event.target !== animeInput
        ) {
            hideResults();
        }
    });
});

document.addEventListener("DOMContentLoaded", () => {
    const searchForm = document.getElementById("search-form");
    const animeInput = document.getElementById("anime-input");
    const animeResults = document.getElementById("anime-results");
    const animeId = document.getElementById("anime-id");

    if (!searchForm || !animeInput || !animeResults || !animeId) {
        console.error("Personal.Rec: необходимые элементы поиска не найдены.");
        return;
    }

    let debounceTimer;
    let controller;

    function hideResults() {
        animeResults.classList.remove("visible");
        animeResults.replaceChildren();
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
        if (anime.score) details.push(`Оценка ${anime.score}%`);

        meta.textContent = details.join(" · ") || "Аниме";

        info.append(title, meta);
        button.append(image, info);

        button.addEventListener("click", () => {
    window.location.href = `/anime/${anime.id}`;
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
        if (!animeInput.value.trim()) {
            event.preventDefault();
            animeInput.focus();
            return;
        }

        if (!animeId.value) {
            event.preventDefault();
            showMessage("Выбери аниме из списка результатов.");
        }
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
from anilist.normalize import normalize_score
from anilist.mapping import _normalize_title

print("=== SCORE NORMALIZATION ===")

tests = [
    (8, "POINT_10"),
    (80, "POINT_100"),
    (4, "POINT_5"),
    (2, "POINT_3"),
    (0, "POINT_10"),
    (None, "POINT_10"),
]

for score, fmt in tests:
    print(score, fmt, "->", normalize_score(score, fmt))


print("\n=== TITLE NORMALIZATION ===")

titles = [
    "Attack on Titan",
    "Shingeki no Kyojin",
    "進撃の巨人",
    "進撃の巨人 Season 2",
]

for title in titles:
    print(repr(title), "->", repr(_normalize_title(title)))
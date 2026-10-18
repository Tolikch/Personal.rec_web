def cosine_similarity(profile_a, profile_b, common=None):
    if common is None:
        common = set(profile_a).intersection(profile_b)
    if len(common) < 3:
        return 0.0

    values_a = [profile_a[item] for item in common]
    values_b = [profile_b[item] for item in common]
    mean_a = sum(values_a) / len(values_a)
    mean_b = sum(values_b) / len(values_b)
    centered_a = [value - mean_a for value in values_a]
    centered_b = [value - mean_b for value in values_b]
    numerator = sum(a * b for a, b in zip(centered_a, centered_b))
    norm_a = sum(value ** 2 for value in centered_a) ** 0.5
    norm_b = sum(value ** 2 for value in centered_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return numerator / (norm_a * norm_b)

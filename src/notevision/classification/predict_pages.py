"""Rule-based prediction of pages containing music notation."""

from typing import Mapping


def rule_based_has_music(features: Mapping[str, object]) -> dict[str, int | float]:
    """Estimate whether page features resemble music staff notation."""
    line_count = max(0, int(features.get("horizontal_line_count", 0)))
    line_density = max(0.0, float(features.get("horizontal_line_density", 0.0)))
    staff_groups = max(0, int(features.get("staff_like_line_groups", 0)))

    line_score = min(line_count / 10.0, 1.0)
    density_score = min(line_density / 0.025, 1.0)
    staff_score = min(staff_groups / 2.0, 1.0)

    score = (
        0.35 * line_score
        + 0.25 * density_score
        + 0.40 * staff_score
    )
    score = round(min(max(score, 0.0), 1.0), 4)

    return {
        "has_music_pred": int(score >= 0.45 and line_count >= 4),
        "has_music_score": score,
    }

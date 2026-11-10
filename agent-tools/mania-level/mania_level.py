"""Convert a Phigros level to a 4K osu!mania star rating.

    python3 mania_level.py 15.5
"""
import sys

LOW_LEVEL = 14.0
HIGH_LEVEL = 18.0


def level_to_mania_star(level: float) -> float:
    """4K osu!mania star rating of a Phigros chart at this level.

    Quadratic fitted by research-tools/phigros-finetune/fit_mania_star.py on 250
    official charts of level 14 to 18, the only range it covers; other levels are
    clamped to that range. A single chart differs from it by about 0.24 stars.
    """
    level = min(max(float(level), LOW_LEVEL), HIGH_LEVEL)
    return 0.159305 * level**2 - 4.419535 * level + 33.238293


if __name__ == "__main__":
    print(round(level_to_mania_star(float(sys.argv[1])), 3))

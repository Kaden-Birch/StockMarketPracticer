"""Level math and the cosmetic title ladder (roadmap 6.2-6.3, 6.5).

Cumulative XP to reach level n: 50 * n * (n-1)  (level 1 = 0, level 2 = 100,
level 3 = 300, level 10 = 4500, ...). Titles are cosmetic only."""

TITLES: list[tuple[int, str]] = [
    (1, "Beginner Investor"),
    (5, "Market Student"),
    (10, "Market Apprentice"),
    (15, "Portfolio Builder"),
    (20, "Strategy Developer"),
    (25, "Seasoned Investor"),
    (30, "Institutional Investor"),
    (40, "Legendary Investor"),
]


def xp_for_level(level: int) -> int:
    """Cumulative XP required to reach `level`."""
    return 50 * level * (level - 1)


def level_from_xp(xp: int) -> int:
    level = 1
    while xp_for_level(level + 1) <= xp:
        level += 1
    return level


def title_for_level(level: int) -> str:
    current = TITLES[0][1]
    for threshold, title in TITLES:
        if level >= threshold:
            current = title
    return current


def level_progress(xp: int) -> dict:
    level = level_from_xp(xp)
    floor = xp_for_level(level)
    ceiling = xp_for_level(level + 1)
    return {
        "level": level,
        "title": title_for_level(level),
        "xp": xp,
        "level_floor_xp": floor,
        "next_level_xp": ceiling,
        "progress_pct": round((xp - floor) / (ceiling - floor) * 100, 1),
        "titles": [{"level": lvl, "title": t, "earned": level >= lvl} for lvl, t in TITLES],
    }

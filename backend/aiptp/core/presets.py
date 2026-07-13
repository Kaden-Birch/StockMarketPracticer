"""Experience Presets (roadmap 6.11.5): per-portfolio module activation.
Presets gate which modules act on a portfolio; the global module switch
gates the whole platform. Experience *levels* (Beginner/Classic/Expert,
roadmap 6.11.6) are orthogonal and stored as Portfolio.mode."""

PRESETS: dict[str, dict] = {
    "LEARNING": {
        "label": "Learning",
        "description": "Education-focused: mentor and analytics without XP, "
                       "levels, achievements, or leaderboards.",
        "disabled_modules": ["gamification"],
    },
    "ACADEMY": {
        "label": "Academy",
        "description": "Everything enabled. The default experience.",
        "disabled_modules": [],
    },
    "PROFESSIONAL": {
        "label": "Professional",
        "description": "Clean analytics and reporting; no gamification or "
                       "cosmetic rewards.",
        "disabled_modules": ["gamification"],
    },
}

DEFAULT_PRESET = "ACADEMY"


def preset_allows(preset: str, module_id: str) -> bool:
    spec = PRESETS.get(preset or DEFAULT_PRESET, PRESETS[DEFAULT_PRESET])
    return module_id not in spec["disabled_modules"]


def presets_view() -> list[dict]:
    return [
        {"id": pid, **spec} for pid, spec in PRESETS.items()
    ]

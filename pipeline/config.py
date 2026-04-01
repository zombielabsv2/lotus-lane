"""Character definitions and pipeline configuration for The Lotus Lane."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_DIR = PROJECT_ROOT / "strips"
STRIPS_JSON = PROJECT_ROOT / "strips.json"
CHARACTERS_DIR = PROJECT_ROOT / "characters"

# API Keys (from environment)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Schedule: 3x/week (Mon, Wed, Fri)
PUBLISH_DAYS = [0, 2, 4]  # Monday=0, Wednesday=2, Friday=4

# Characters
CHARACTERS = {
    "arjun": {
        "name": "Arjun",
        "age": 32,
        "role": "Software engineer at a Bangalore startup",
        "appearance": "Indian man, short neat black hair, slim build, rectangular glasses, usually wearing a hoodie or casual office kurta. Clean-shaven. Friendly but tired eyes. Medium brown skin.",
        "personality": "Overworked, deals with imposter syndrome, recently started Buddhist practice. Earnest, self-deprecating humor. Overthinks everything. Pressure from family to settle down.",
        "color": "#4A90D9",
    },
    "meera": {
        "name": "Meera",
        "age": 28,
        "role": "Graduate student in psychology",
        "appearance": "Indian woman, long dark hair often in a braid, warm brown skin, expressive eyes, wears casual academic clothes — cardigans, jeans, oxidized silver jhumkas. Small nose pin.",
        "personality": "Anxious but deeply thoughtful. Skeptical about religion but curious about philosophy. Struggles with perfectionism and comparison. Navigating traditional family expectations vs her own path.",
        "color": "#E67E22",
    },
    "sudha": {
        "name": "Sudha",
        "age": 55,
        "role": "Recently separated, rebuilding her life after kids left home",
        "appearance": "Indian woman, salt-and-pepper hair in a neat bun, warm smile, strong presence. Wears elegant cotton sarees or salwar kameez. Reading glasses often on her head. Fair skin with laugh lines.",
        "personality": "Long-time Buddhist practitioner. Wise but not preachy. Going through her own struggles (separation, empty nest) while supporting others. Sharp Marathi wit.",
        "color": "#8E44AD",
    },
    "vikram": {
        "name": "Vikram",
        "age": 40,
        "role": "Single dad, runs a small manufacturing business",
        "appearance": "Indian man, stocky build, short black hair with some gray at temples, trimmed beard, work-worn hands. Wears plain shirts with sleeves rolled up. Dark complexion, strong jaw.",
        "personality": "Tough exterior, gentle heart. New to Buddhism — introduced by Sudha. Struggles with vulnerability, societal expectations of being the provider, parenting alone after wife passed away.",
        "color": "#27AE60",
    },
}

# Challenge categories with sub-topics
CHALLENGE_TOPICS = {
    "work-stress": [
        "toxic boss", "layoff anxiety", "imposter syndrome", "burnout",
        "career stagnation", "work-life balance", "difficult coworker",
        "being overlooked for promotion", "starting a new job", "deadline pressure",
    ],
    "relationships": [
        "argument with partner", "loneliness", "trust issues", "breakup recovery",
        "communication breakdown", "long-distance strain", "jealousy",
        "falling out with a friend", "in-laws conflict", "dating anxiety",
    ],
    "family": [
        "parenting struggles", "aging parents", "sibling conflict", "empty nest",
        "blended family tensions", "family expectations", "generational gap",
        "teenage rebellion", "divorce impact on kids", "caretaker fatigue",
    ],
    "health": [
        "chronic illness", "mental health stigma", "injury recovery", "insomnia",
        "anxiety attacks", "depression fog", "health scare", "addiction recovery",
        "body image", "aging and vitality",
    ],
    "finances": [
        "debt overwhelm", "job loss", "living paycheck to paycheck",
        "financial comparison", "unexpected expense", "retirement worry",
        "supporting family financially", "career vs passion pay gap",
    ],
    "self-doubt": [
        "feeling not enough", "comparison trap", "fear of failure",
        "starting over at any age", "losing motivation", "identity crisis",
        "feeling like a fraud", "fear of judgment", "purpose and meaning",
    ],
    "grief-loss": [
        "loss of a loved one", "mourning a relationship", "loss of a dream",
        "pet loss", "miscarriage", "losing a mentor", "coping with change",
    ],
    "perseverance": [
        "wanting to give up", "repeated failure", "patience running thin",
        "slow progress", "no visible results from effort", "hitting a wall",
    ],
}

# Art style prompt prefix (for consistent visual style)
ART_STYLE = (
    "High-quality digital illustration in the style of a professional webtoon or graphic novel. "
    "Clean linework, rich saturated colors, detailed backgrounds. Characters should look polished "
    "and well-proportioned with expressive faces and natural body language. Lighting should be "
    "cinematic with warm tones. Indian settings and characters. Art quality comparable to "
    "published manhwa or Webtoon Originals. Single scene, no panel borders or splits."
)

# Panel layout
PANELS_PER_STRIP = 4
STRIP_WIDTH = 1024  # pixels — matches source image width, no horizontal scaling
PANEL_HEIGHT = 700  # pixels per panel — center-crops from 1024x1024 for slight landscape feel
PANEL_GAP = 0       # no gap — dialogue bands separate panels

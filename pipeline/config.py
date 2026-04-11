"""Character definitions and pipeline configuration for The Lotus Lane."""

import os
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
STRIPS_DIR = PROJECT_ROOT / "strips"
STRIPS_JSON = PROJECT_ROOT / "strips.json"
CHARACTERS_DIR = PROJECT_ROOT / "characters"

# Image CDN — strip PNGs are hosted on a separate GitHub Pages repo
ASSETS_BASE_URL = "https://zombielabsv2.github.io/lotus-lane-assets"

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
# These map to universal human struggles — the audience is everyone who suffers,
# not just Buddhist practitioners. Topics should be Google-searchable problems.
CHALLENGE_TOPICS = {
    "work-stress": [
        "toxic boss", "layoff anxiety", "imposter syndrome", "burnout",
        "career stagnation", "work-life balance", "difficult coworker",
        "being overlooked for promotion", "starting a new job", "deadline pressure",
        "feeling invisible at work", "dreading Monday mornings", "office politics",
        "micromanaging boss", "quitting without a plan",
    ],
    "relationships": [
        "argument with partner", "loneliness", "trust issues", "breakup recovery",
        "communication breakdown", "long-distance strain", "jealousy",
        "falling out with a friend", "in-laws conflict", "dating anxiety",
        "one-sided friendship", "partner not listening", "growing apart",
        "social media comparison in relationships", "forgiving someone who hurt you",
    ],
    "family": [
        "parenting struggles", "aging parents", "sibling conflict", "empty nest",
        "blended family tensions", "family expectations", "generational gap",
        "teenage rebellion", "divorce impact on kids", "caretaker fatigue",
        "parenting a child with special needs", "guilt about not doing enough",
        "toxic family dynamics", "living up to parents' dreams",
    ],
    "health": [
        "chronic illness", "mental health stigma", "injury recovery", "insomnia",
        "anxiety attacks", "depression fog", "health scare", "addiction recovery",
        "body image", "aging and vitality",
        "panic attacks at night", "brain fog and exhaustion", "therapy stigma in India",
    ],
    "finances": [
        "debt overwhelm", "job loss", "living paycheck to paycheck",
        "financial comparison", "unexpected expense", "retirement worry",
        "supporting family financially", "career vs passion pay gap",
        "EMI stress", "asking parents for money as an adult",
        "friends earning more than you", "startup failure and debt",
    ],
    "self-doubt": [
        "feeling not enough", "comparison trap", "fear of failure",
        "starting over at any age", "losing motivation", "identity crisis",
        "feeling like a fraud", "fear of judgment", "purpose and meaning",
        "scrolling and feeling worthless", "everyone has it figured out except me",
        "too old to change careers", "not knowing what you want",
    ],
    "grief-loss": [
        "loss of a loved one", "mourning a relationship", "loss of a dream",
        "pet loss", "miscarriage", "losing a mentor", "coping with change",
        "anniversary grief", "grief that comes in waves", "survivor guilt",
        "losing a parent young",
    ],
    "perseverance": [
        "wanting to give up", "repeated failure", "patience running thin",
        "slow progress", "no visible results from effort", "hitting a wall",
        "everyone else is succeeding", "starting from zero again",
        "doing everything right and still failing",
    ],
    "anger": [
        "rage you cannot explain", "anger at injustice", "resentment eating you alive",
        "snapping at people you love", "anger after betrayal",
        "road rage and daily frustration", "holding grudges",
    ],
    "loneliness": [
        "lonely in a crowd", "no one really knows me", "new city no friends",
        "loneliness after divorce", "loneliness in marriage",
        "losing your friend group in your 30s", "feeling like a burden",
    ],
    "envy": [
        "friend got promoted and you did not", "sibling has it all",
        "ex is thriving and you are not", "Instagram highlight reel vs your reality",
        "jealousy of younger people getting ahead",
    ],
}

# Map of affliction themes to human-readable page titles for SEO landing pages.
# Each key is a URL slug, value is (page_title, meta_description, related_categories).
AFFLICTION_PAGES = {
    "dealing-with-jealousy": (
        "How to Deal with Jealousy",
        "Jealousy is eating you alive. Ancient wisdom and modern stories on letting go of envy and finding your own path.",
        ["envy", "self-doubt", "relationships"],
    ),
    "overcoming-imposter-syndrome": (
        "Overcoming Imposter Syndrome",
        "You feel like a fraud at work. You're not alone. Stories and wisdom for anyone who thinks they don't belong.",
        ["work-stress", "self-doubt"],
    ),
    "when-grief-wont-stop": (
        "When Grief Won't Stop",
        "Grief doesn't follow a timeline. Wisdom for the 3am moments when loss hits all over again.",
        ["grief-loss"],
    ),
    "feeling-like-a-failure": (
        "Feeling Like a Failure After 30",
        "Everyone else has it figured out. You don't. Here's what an 800-year-old letter says about that.",
        ["self-doubt", "perseverance", "finances"],
    ),
    "loneliness-despite-everything": (
        "Lonely Even When You're Not Alone",
        "Surrounded by people but deeply lonely. Stories about finding real connection.",
        ["loneliness", "relationships"],
    ),
    "toxic-workplace-survival": (
        "Surviving a Toxic Workplace",
        "Your boss is terrible, your coworkers are worse, and you can't quit yet. Wisdom for staying sane.",
        ["work-stress"],
    ),
    "anger-you-cant-control": (
        "When Anger Takes Over",
        "You snap at the people you love. The rage doesn't make sense. Here's what ancient philosophy says about it.",
        ["anger", "relationships", "family"],
    ),
    "starting-over": (
        "Starting Over at Any Age",
        "Divorce, job loss, or just the feeling that you need to begin again. Courage for the reset.",
        ["perseverance", "self-doubt", "grief-loss"],
    ),
    "parenting-is-breaking-me": (
        "When Parenting Feels Impossible",
        "You love your kids but parenting is crushing you. Wisdom for the days when you have nothing left.",
        ["family"],
    ),
    "financial-anxiety": (
        "Drowning in Financial Anxiety",
        "Debt, EMIs, and the fear of not providing. Stories about finding peace when money is tight.",
        ["finances"],
    ),
    "how-to-forgive": (
        "How to Forgive Someone Who Hurt You",
        "You know you should let go but you can't. What a 13th-century philosopher said about forgiveness.",
        ["relationships", "anger", "grief-loss"],
    ),
    "comparison-trap": (
        "Everyone Is Doing Better Than Me",
        "Instagram says everyone is thriving. You're barely surviving. Here's the truth about comparison.",
        ["envy", "self-doubt", "loneliness"],
    ),
    "depression-fog": (
        "When You Can't Get Out of Bed",
        "The fog is real. You're not lazy. Stories and ancient wisdom for the days everything feels heavy.",
        ["health", "loneliness"],
    ),
    "relationship-falling-apart": (
        "When Your Relationship Is Falling Apart",
        "You used to be happy together. Now you're just two strangers. Wisdom for the space between love and leaving.",
        ["relationships"],
    ),
    "burnout-recovery": (
        "Burned Out and Running on Empty",
        "You've given everything and there's nothing left. What to do when hustle culture breaks you.",
        ["work-stress", "health"],
    ),
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

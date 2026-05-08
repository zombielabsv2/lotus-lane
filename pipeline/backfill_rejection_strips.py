#!/usr/bin/env python3
"""
Hand-authored rejection-themed strip scripts (Opus 4.7, zero Claude API).

Writes 5 script.json files into strips/cache/<date>/ for the following dates,
chosen to fill Mon/Wed/Fri gaps before 2026-04-29:

  2026-02-02 — Seven Rounds and a Voicemail (job rejection)
  2026-02-04 — She Just Stopped Replying (ghosting)
  2026-02-06 — Forty-Seven Pass Letters (creative rejection)
  2026-02-20 — The Group Chat Got a New Group Chat (friend exclusion)
  2026-03-27 — My Father Said "I Have No Daughter Anymore" (family rejection)

The workflow `generate-strip.yml` (modified to accept a `date` input) picks
up these caches when triggered with workflow_dispatch -f date=<date>. It
skips the Claude script call (cache hit) and proceeds straight to GPT-4o
panel generation, Playwright text overlay, video, hook reel, and YouTube
upload — one strip per workflow run, queued via the strips-json-writer
concurrency group so they serialize.

Cost per strip: ~Rs.18-25 (4 GPT-4o panels + ElevenLabs TTS for video).
5 strips total: ~Rs.90-125. YouTube quota: 5 uploads * 1600 units = 8000
of 10000 daily, well under the cap.
"""
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CACHE_ROOT = PROJECT_ROOT / "strips" / "cache"


SCRIPTS = [
    {
        "date": "2026-02-02",
        "category": "rejection",
        "topic": "job rejection after multiple interview rounds",
        "characters": [],
        "script": {
            "title": "Seven Rounds and a Voicemail",
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "A small but tidy Mumbai apartment kitchen at 9pm. Riya, a 28-year-old Indian woman with shoulder-length straight black hair and round-frame glasses, wears a faded grey sweatshirt over jeans. She stands frozen by the kitchen counter, holding her phone to her ear, a bowl of half-eaten poha forgotten beside her. Her expression is stunned, eyes wide, mouth slightly open. Behind her, the open laptop on the dining table shows the company's careers page.",
                    "dialogue": [
                        "Voicemail: We've decided to move forward with another candidate. Best wishes.",
                        "Riya: That's it? After seven rounds?"
                    ],
                    "mood": "stunned"
                },
                {
                    "panel_number": 2,
                    "scene_description": "Riya is now slumped on a beige sofa in the living room, knees pulled up to her chest. The same grey sweatshirt is now darker around the shoulder where she has wiped her face. The room is dim, lit only by a single warm yellow lamp and the laptop screen on the coffee table showing the rejection email. A printed copy of her resume lies on the floor.",
                    "dialogue": [
                        "Riya: I rebuilt my entire life around getting this job.",
                        "Riya: I told everyone. I told Amma."
                    ],
                    "mood": "devastated"
                },
                {
                    "panel_number": 3,
                    "scene_description": "Close-up of Riya at the same coffee table, but now she has opened a worn leather notebook and is writing in it with a black pen. Her face is calmer, though tear tracks are still visible on her cheeks. Beside her on the table is a small framed photo of her at her engineering graduation with her mother. The lamp light catches the edge of her glasses. Behind her, the window shows the lights of Mumbai at night.",
                    "dialogue": [
                        "Riya (writing): What I learned in seven rounds...",
                        "Riya (writing): System design. The C-suite's questions. How I behave under pressure."
                    ],
                    "mood": "thoughtful"
                },
                {
                    "panel_number": 4,
                    "scene_description": "Morning light now floods the same living room. Riya, in a fresh white kurta, sits at the dining table with the laptop open, typing a message. Her expression is calm and steady, no longer puffy from crying. A fresh cup of chai steams beside her. The notebook from the previous panel sits open with a list of names.",
                    "dialogue": [
                        "Riya: Hi Vikram, this is Riya. I made it to your final round last month and didn't get the offer.",
                        "Riya: I'd love to be considered if anything else opens up. Here's what I learned about myself in your process..."
                    ],
                    "mood": "resolute"
                }
            ],
            "nichiren_quote": "Iron, when heated in fire and pounded, becomes a fine sword.",
            "source": "Nichiren Daishonin, 'The True Aspect of All Phenomena,' WND-1, p. 384",
            "message": "A rejection after seven rounds is not a verdict on your worth - it is data. The interviews changed you whether or not the offer came. Use what was forged.",
            "tags": ["rejection", "work-stress", "self-worth", "perseverance"]
        }
    },
    {
        "date": "2026-02-04",
        "category": "rejection",
        "topic": "romantic ghosting / sudden silence",
        "characters": [],
        "script": {
            "title": "She Just Stopped Replying",
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "A Bangalore studio apartment at midnight. Karthik, a 32-year-old Indian man with a short trimmed beard and tired eyes, wears a wrinkled blue t-shirt. He sits on the edge of an unmade bed, holding his phone with both hands, staring at the screen. The phone shows a WhatsApp chat where his last three messages are marked with single grey ticks. The room is lit by the blue glow of the screen and a desk lamp. An untouched Swiggy bag sits on the floor.",
                    "dialogue": [
                        "Karthik: Six months. And now nothing. Not even an explanation."
                    ],
                    "mood": "anguished"
                },
                {
                    "panel_number": 2,
                    "scene_description": "Karthik now stands at his small kitchen counter at 2am, microwaving leftover dal. The kitchen light is harsh and fluorescent. He stares blankly at the rotating plate inside. His phone sits face-down on the counter beside him. His expression is hollow, exhausted but unable to sleep.",
                    "dialogue": [
                        "Karthik: Was it me? Did I say something? Did I not say something?",
                        "Karthik: I keep replaying every word."
                    ],
                    "mood": "spiraling"
                },
                {
                    "panel_number": 3,
                    "scene_description": "Morning. Karthik sits across from his older sister Divya, 38, a woman with hair tied back in a low bun, wearing a green cotton kurta. They are at a sunlit corner cafe in Indiranagar with two cups of filter coffee between them. Karthik's eyes are red but he is sitting upright. Divya is mid-sentence, her hand resting on his.",
                    "dialogue": [
                        "Divya: Anna, listen to me. Her silence is information about her. Not about you.",
                        "Divya: A person who can disappear without a word is not a person who could have stayed."
                    ],
                    "mood": "tender"
                },
                {
                    "panel_number": 4,
                    "scene_description": "Karthik is now jogging through Cubbon Park in the late afternoon, wearing running shorts and a grey tee, earphones in. The afternoon light filters through the trees. His face is flushed from exertion but no longer hollow - there is a quiet steadiness in his expression. In his hand he holds his phone, and we can see the chat with the woman has been archived.",
                    "dialogue": [
                        "Karthik (thinking): The pain is real. The story I was telling about it was not.",
                        "Karthik (thinking): One foot. Then the next."
                    ],
                    "mood": "grounded"
                }
            ],
            "nichiren_quote": "True happiness is not the absence of suffering. It is the ability to find meaning and joy even in the midst of suffering.",
            "source": "Daisaku Ikeda, Discussions on Youth",
            "message": "Ghosting tells you more about the person who left than the person who was left. The pain is real. The verdict you keep writing about yourself is not.",
            "tags": ["rejection", "heartbreak", "loneliness", "letting-go"]
        }
    },
    {
        "date": "2026-02-06",
        "category": "rejection",
        "topic": "creative rejection / repeated no's",
        "characters": [],
        "script": {
            "title": "Forty-Seven Pass Letters",
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "A small home study in Pune, late afternoon. Anjali, a 39-year-old Indian woman with greying hair pulled into a loose plait, wearing a maroon shawl over a kurta, sits at a wooden desk surrounded by stacks of paper and a printer. Her face is tired and slightly defeated. She is reading the latest email on her laptop screen. Behind her, on a corkboard, are pinned forty-six small printed rejection emails, all marked 'Pass.' She is reading the forty-seventh.",
                    "dialogue": [
                        "Anjali: 'We loved the voice but it doesn't fit our list right now.'",
                        "Anjali: Forty-seven. They all loved the voice."
                    ],
                    "mood": "deflated"
                },
                {
                    "panel_number": 2,
                    "scene_description": "Anjali is now crouching on the floor of the study, gathering printed pages of her novel manuscript that have spilled from a fallen folder. Her shawl has slipped off one shoulder. The manuscript pages are titled 'The Saltwater Daughter.' Her expression is somewhere between grief and grim determination, eyes shining but not crying.",
                    "dialogue": [
                        "Anjali: Nobody is going to publish this book. Not one of them.",
                        "Anjali: I gave it five years."
                    ],
                    "mood": "grief"
                },
                {
                    "panel_number": 3,
                    "scene_description": "Same room, evening. Anjali sits on the floor with her back against the desk, the manuscript pages now stacked neatly in her lap. She has a cup of chai in one hand. On the wall, beside the rejection corkboard, hangs a framed photograph of her late grandmother, who clearly inspired the book. Anjali is looking at the photograph with a small, sad smile.",
                    "dialogue": [
                        "Anjali (thinking): Naani told me writers in our family have always been read by no one.",
                        "Anjali (thinking): That didn't stop them writing."
                    ],
                    "mood": "reflective"
                },
                {
                    "panel_number": 4,
                    "scene_description": "Morning. Anjali at the same desk, now wearing a clean cream kurta. Her laptop is open to a new document titled 'Chapter One.' Her hands are on the keys, posture upright. The forty-seven rejection emails are still on the corkboard - she has not taken them down - but next to them is now pinned a single sheet that reads 'Book 2: Notes.' Through the window, morning sun catches the dust in the air.",
                    "dialogue": [
                        "Anjali (typing): Chapter One.",
                        "Anjali (thinking): The first book taught me how to write. The second one is the one they'll buy."
                    ],
                    "mood": "resolute"
                }
            ],
            "nichiren_quote": "The most important thing is to never be defeated by your weaknesses. Each time you struggle and stand back up, you become stronger.",
            "source": "Daisaku Ikeda, Faith Into Action",
            "message": "Forty-seven no's is not a verdict. It is a tuition fee paid to learn the craft. The book that finally lands will be the one written by the person who paid it.",
            "tags": ["rejection", "perseverance", "self-doubt", "starting-over"]
        }
    },
    {
        "date": "2026-02-20",
        "category": "rejection",
        "topic": "social rejection / left out of friend group",
        "characters": [],
        "script": {
            "title": "The Group Chat Got a New Group Chat",
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "A bright South Delhi cafe at lunchtime. Priya, a 35-year-old Indian woman with wavy chin-length hair, wears a pale blue cotton kurta and silver jhumkas. She sits alone at a small table holding her phone and looking at it with confusion. On her phone screen, an Instagram story is visible: four of her oldest friends are at a beach in Goa, captioned 'GIRLS TRIP! Year four!' Priya's untouched cappuccino is in front of her.",
                    "dialogue": [
                        "Priya: Year four? I wasn't there for any of them."
                    ],
                    "mood": "confused"
                },
                {
                    "panel_number": 2,
                    "scene_description": "Priya is back at her shared workspace cubicle, staring at her laptop without typing. Her face is now hurt and quietly humiliated. On her desk are small touches that show how much she had invested in those friendships: a printed group photo from college framed beside the keyboard, a friendship-bracelet bowl, and a thank-you card from one of those same friends.",
                    "dialogue": [
                        "Priya (thinking): Three years of being the one who organizes everything.",
                        "Priya (thinking): And they made a different chat."
                    ],
                    "mood": "hurt"
                },
                {
                    "panel_number": 3,
                    "scene_description": "Evening. Priya is on the rooftop terrace of her apartment building, leaning on the railing with a glass of water. The Delhi sky is amber with sunset. Beside her stands her downstairs neighbour, Reema, 41, a woman with short grey hair and a kind, weathered face. Reema is smoking a single cigarette and listening intently. Priya looks at Reema, eyes wet but voice steady.",
                    "dialogue": [
                        "Priya: I'm not even angry. I just feel like I was the one who didn't get the memo.",
                        "Reema: Beta, sometimes the memo never comes. The friendship just quietly grew up without you in it."
                    ],
                    "mood": "vulnerable"
                },
                {
                    "panel_number": 4,
                    "scene_description": "Priya is now at her dining table, the laptop closed beside her. She is opening a small handwritten address book and dialing a number on her phone. Her expression is tender, no longer hurt - resolute. The framed college photo is still on her desk in the background, but now beside it she has placed two new photos: one of Reema laughing on the terrace, and one of a younger cousin she has not called in months.",
                    "dialogue": [
                        "Priya (on phone): Hi Naina. It's Priya didi. I'm sorry I haven't called in so long.",
                        "Priya (thinking): The right people are already in my life. I have just been calling the wrong ones."
                    ],
                    "mood": "warm"
                }
            ],
            "nichiren_quote": "A single warm word can give someone the courage to go on living. Never underestimate the power of a kind heart.",
            "source": "Daisaku Ikeda, For Today and Tomorrow",
            "message": "Some friendships quietly grow up without you. The grief is real. So is the empty space they leave - which is exactly the room you needed to invite the right people in.",
            "tags": ["rejection", "friendship", "loneliness", "letting-go"]
        }
    },
    {
        "date": "2026-03-27",
        "category": "rejection",
        "topic": "family rejection / disowned",
        "characters": [],
        "script": {
            "title": "My Father Said I Have No Daughter Anymore",
            "panels": [
                {
                    "panel_number": 1,
                    "scene_description": "A Hyderabad apartment, late evening. Lata, a 30-year-old Indian woman with long black hair and red bangles on her wrists (recently married), wears a deep maroon cotton sari. She stands frozen in her own living room holding her phone, the call just ended. Behind her, her husband Faisal, 33, with kind eyes and a navy kurta, watches from the doorway, hands at his sides, not knowing what to do. The room is full of small Tamil household details - a brass lamp, a framed picture of Murugan.",
                    "dialogue": [
                        "Lata (whispering): He said the words. 'I have no daughter anymore.'"
                    ],
                    "mood": "shock"
                },
                {
                    "panel_number": 2,
                    "scene_description": "Lata is now sitting on the floor of the living room with her back against the sofa, knees pulled up. The maroon sari is rumpled. She is looking at an old photograph in her hands - her with her father at her tenth birthday, both of them smiling, his hand on her shoulder. Faisal sits next to her on the floor, not touching her, just present. His hand rests on the floor close to hers.",
                    "dialogue": [
                        "Lata: He used to call me Lata-papa.",
                        "Faisal: He still does, in his head. He just won't let his mouth say it."
                    ],
                    "mood": "broken"
                },
                {
                    "panel_number": 3,
                    "scene_description": "Several days later. Lata sits at a small home altar in the corner of the apartment - a humble wooden shelf with a Gohonzon scroll, a small offering of fruit, and a candle. She is in a simple cream kurta, eyes closed, hands joined in prayer. Her face is no longer destroyed. There are tear tracks but also stillness. The morning light through the window is soft.",
                    "dialogue": [
                        "Lata (thinking): Suffer what there is to suffer. Enjoy what there is to enjoy.",
                        "Lata (thinking): I will not stop being his daughter just because he stopped saying it."
                    ],
                    "mood": "still"
                },
                {
                    "panel_number": 4,
                    "scene_description": "Three months later, the same apartment, but more lived-in now - a few new framed photographs on the wall (Lata and Faisal's wedding, and one of Lata's mother holding a phone, smiling secretly). Lata stands at the kitchen counter on a video call, her face warm and a little teary. On the laptop screen we see her mother in the family kitchen back home, looking around guiltily as she whispers.",
                    "dialogue": [
                        "Mother (on screen, whispering): He fell asleep. Show me the new ironing board, kanna.",
                        "Lata (smiling, eyes wet): Amma. Look at me. We are all still a family. He just hasn't caught up yet."
                    ],
                    "mood": "tender"
                }
            ],
            "nichiren_quote": "Suffer what there is to suffer, enjoy what there is to enjoy. Regard both suffering and joy as facts of life.",
            "source": "Nichiren Daishonin, 'Happiness in This World,' WND-1, p. 681",
            "message": "When family rejects you, the grief is sacred and the wound is real. But you do not stop being a daughter, a son, a sibling - you become the one who keeps the door open while the other person learns to walk back through it.",
            "tags": ["rejection", "family", "letting-go", "perseverance"]
        }
    },
]


def main():
    print(f"Writing {len(SCRIPTS)} rejection strip script.json caches...\n")
    for entry in SCRIPTS:
        date = entry["date"]
        cache_dir = CACHE_ROOT / date
        cache_dir.mkdir(parents=True, exist_ok=True)
        out = cache_dir / "script.json"
        # Schema mirrors what generate_strip.py writes via _save_cached_script:
        #   {"script": {...}, "category": "...", "topic": "...", "characters": [...]}
        payload = {
            "script": entry["script"],
            "category": entry["category"],
            "topic": entry["topic"],
            "characters": entry["characters"],
        }
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  {date}: {entry['script']['title']}  ->  {out.relative_to(PROJECT_ROOT)}")

    print(f"\nDONE. Now trigger generate-strip.yml for each date:")
    for entry in SCRIPTS:
        print(f"  gh workflow run generate-strip.yml -f date={entry['date']}")


if __name__ == "__main__":
    main()

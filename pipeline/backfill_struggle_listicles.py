#!/usr/bin/env python3
"""
One-shot backfill: hand-authored listicles for the 7 struggles that had
zero listicle coverage on 2026-05-09.

These listicles bypass the Claude API call — content is hand-written here.
All Pillow rendering still runs through the existing pipeline functions.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.generate_listicle import (
    generate_hero,
    generate_infographic,
    generate_carousel_cover,
    generate_carousel_slide,
    save_listicle,
)


# Each listicle: backdated to fill 2026-04-01 through 2026-04-07 (gap before
# the daily cron started 2026-04-08). title, items[5], theme metadata,
# struggles[] tags for the wisdom-page hub.
LISTICLES = [
    {
        "date": "2026-04-01",
        "theme": "health",
        "theme_name": "Health & Life Force",
        "title": "Body Failing You? 5 Truths to Hold Onto When Healing Feels Impossible",
        "struggles": ["chronic-illness"],
        "items": [
            {
                "quote": "Health is not simply the absence of illness. It is a dynamic state of vitality in which we can challenge anything.",
                "source": "The Wisdom for Creating Happiness and Peace",
                "explanation": "Real health is not the body that has never broken - it is the spirit that keeps choosing to live anyway.",
            },
            {
                "quote": "Illness can be an opportunity for human revolution. Through illness, we can deepen our faith and grow as human beings.",
                "source": "For Today and Tomorrow",
                "explanation": "What the body is forced to surrender, the inner self can quietly take back - patience, attention, smaller joys.",
            },
            {
                "quote": "The life force that comes from strong faith is the greatest medicine.",
                "source": "Faith Into Action",
                "explanation": "When the prescription bottles stop working, the will to keep showing up for one more morning is what carries you.",
            },
            {
                "quote": "Winter always turns to spring. Never, from ancient times on, has anyone heard or seen of winter that did not turn to spring.",
                "source": "The Writings of Nichiren Daishonin",
                "explanation": "Bodies move in seasons too. The flare you are inside now is not a forecast for the rest of your life.",
            },
            {
                "quote": "Even if you cannot stand, your spirit can. Even if your body is weak, your heart can be strong.",
                "source": "Discussions on Youth",
                "explanation": "The smallest unit of dignity left to a sick person is choosing what to think while the body does its work without permission.",
            },
        ],
    },
    {
        "date": "2026-04-02",
        "theme": "happiness",
        "theme_name": "Happiness",
        "title": "Can't Stop Comparing Yourself? 5 Truths About the Envy That's Eating You",
        "struggles": ["dealing-with-jealousy", "comparison-trap"],
        "items": [
            {
                "quote": "Happiness is not something that someone else can give you. It is something you must create yourself.",
                "source": "The Wisdom for Creating Happiness and Peace",
                "explanation": "Their promotion did not steal a finite supply of joy from you - your supply is in a different account, and only you can fund it.",
            },
            {
                "quote": "True happiness is not the absence of suffering. It is the ability to find meaning and joy even in the midst of suffering.",
                "source": "Discussions on Youth",
                "explanation": "The happy people you envy are not happy because their lives are easier. They have practiced finding good in lives that are also hard.",
            },
            {
                "quote": "A great human revolution in just a single individual will help achieve a change in the destiny of a nation.",
                "source": "The Human Revolution",
                "explanation": "The energy you spend resenting them is energy you are choosing not to spend changing the one life you actually control.",
            },
            {
                "quote": "When we change ourselves, our world changes too. The environment is the mirror of our inner life.",
                "source": "For Today and Tomorrow",
                "explanation": "Envy is a signal, not a verdict - it is your gut telling you what you actually want, in language that feels like venom.",
            },
            {
                "quote": "The most important thing is to never be defeated by your weaknesses. Each time you struggle and stand back up, you become stronger.",
                "source": "Faith Into Action",
                "explanation": "The version of you that stops comparing and starts building is one honest hour of effort away from the version that keeps scrolling.",
            },
        ],
    },
    {
        "date": "2026-04-03",
        "theme": "courage",
        "theme_name": "Courage",
        "title": "Money Suffocating You? 5 Truths That Aren't About Frugality Tips",
        "struggles": ["financial-anxiety"],
        "items": [
            {
                "quote": "Courage is not the absence of fear. Courage is feeling fear, recognizing fear, and still taking action.",
                "source": "Discussions on Youth",
                "explanation": "Opening the bank app while shaking is courage. The point is not to be unafraid - it is to look anyway.",
            },
            {
                "quote": "No one succeeds without struggle. Difficulties are the forge in which we are shaped.",
                "source": "Discussions on Youth",
                "explanation": "Almost everyone you admire has had a season of looking at a number that scared them. The shame you feel is private; the experience is not.",
            },
            {
                "quote": "Now is the time to act. Not tomorrow, not next week, not when conditions are perfect. Now.",
                "source": "Discussions on Youth",
                "explanation": "The conversation with the bank, the call to the family member, the spreadsheet you are avoiding - one of those tonight changes more than another month of dread.",
            },
            {
                "quote": "Buddhism is about winning. It is about the courage to overcome obstacles, to triumph over anything that stands in the way of our happiness.",
                "source": "Faith Into Action",
                "explanation": "Money is a problem to solve, not a verdict on your worth. People with less than you have built lives larger than yours.",
            },
            {
                "quote": "A hundred theories without a single action are worthless. Even one small step taken with determination changes everything.",
                "source": "For Today and Tomorrow",
                "explanation": "The first concrete step - listing every debt, calling one creditor, cutting one fixed cost - converts dread into a project, and projects can be finished.",
            },
        ],
    },
    {
        "date": "2026-04-04",
        "theme": "compassion",
        "theme_name": "Compassion",
        "title": "Parenting Breaking You? 5 Truths When You've Lost Yourself in the Caretaking",
        "struggles": ["parenting-is-breaking-me", "caregiver-burden"],
        "items": [
            {
                "quote": "True compassion is not soft or weak. It takes great strength to truly care about others, to truly understand their suffering.",
                "source": "Discussions on Youth",
                "explanation": "What you are doing every day is not minor. The world has agreed to call it 'just parenting' - the world is wrong.",
            },
            {
                "quote": "A single warm word can give someone the courage to go on living. Never underestimate the power of a kind heart.",
                "source": "For Today and Tomorrow",
                "explanation": "The warmth you have been pouring into someone smaller than you is the same warmth that runs out if you do not also pour some back into yourself.",
            },
            {
                "quote": "Compassion is not about feeling pity for others. It is about sharing their suffering and walking with them through it.",
                "source": "The Wisdom for Creating Happiness and Peace",
                "explanation": "Your child does not need a perfect parent. They need one who is still in the room with them - including in the moments you are barely holding on.",
            },
            {
                "quote": "Fall down seven times, stand up eight. This is the spirit of a winner.",
                "source": "For Today and Tomorrow",
                "explanation": "Every parent in history has had the moment they thought they were failing this child. Most of them were wrong - and so are you.",
            },
            {
                "quote": "The most important thing is to never be defeated by your weaknesses. Each time you struggle and stand back up, you become stronger.",
                "source": "Faith Into Action",
                "explanation": "Asking for help is not the failure - pretending you do not need it is. You are allowed to be a person, not just a parent.",
            },
        ],
    },
    {
        "date": "2026-04-05",
        "theme": "courage",
        "theme_name": "Courage",
        "title": "They Said No? 5 Truths About What Rejection Actually Means About You",
        "struggles": ["rejection", "feeling-like-a-failure"],
        "items": [
            {
                "quote": "Courage is not the absence of fear. Courage is feeling fear, recognizing fear, and still taking action.",
                "source": "Discussions on Youth",
                "explanation": "You showed up. You asked. You let yourself be seen. Most people stay safe. You did the harder thing - that part is yours to keep.",
            },
            {
                "quote": "A great human revolution in just a single individual will help achieve a change in the destiny of a nation.",
                "source": "The Human Revolution",
                "explanation": "Their no was about their fit, their timing, their fear - not a final ruling on whether you are worth choosing.",
            },
            {
                "quote": "The most important thing is to never be defeated by your weaknesses. Each time you struggle and stand back up, you become stronger.",
                "source": "Faith Into Action",
                "explanation": "The interview, the manuscript, the person - it is not the rejection that defines you. It is the fact that you go again.",
            },
            {
                "quote": "Iron, when heated in fire and pounded, becomes a fine sword.",
                "source": "Nichiren Daishonin, 'The True Aspect of All Phenomena'",
                "explanation": "Every yes you ever get is built on the no's that came first. You are not behind - you are in the forge.",
            },
            {
                "quote": "Hope is not a matter of ability; it is a matter of decision.",
                "source": "Discussions on Youth",
                "explanation": "Hope after rejection is not a feeling you wait to arrive. It is a decision you make at 11pm with red eyes, before any evidence shows up.",
            },
        ],
    },
    {
        "date": "2026-04-06",
        "theme": "perseverance",
        "theme_name": "Perseverance",
        "title": "Boss Making You Miserable? 5 Truths About Surviving What You Can't Yet Quit",
        "struggles": ["toxic-workplace-survival", "sidelined-at-work"],
        "items": [
            {
                "quote": "The last five minutes of endurance - that is what decides victory or defeat. Never give up in the crucial moment.",
                "source": "The New Human Revolution, Vol. 3",
                "explanation": "Most toxic chapters end. Either you leave, they leave, or the dynamic shifts. The trick is not letting it eat you while you wait.",
            },
            {
                "quote": "No one succeeds without struggle. Difficulties are the forge in which we are shaped.",
                "source": "Discussions on Youth",
                "explanation": "The skills you are building right now - reading a difficult person, protecting your peace, picking battles - will serve you in every job that comes after this one.",
            },
            {
                "quote": "Buddhism is about winning. It is about the courage to overcome obstacles, to triumph over anything that stands in the way of our happiness.",
                "source": "Faith Into Action",
                "explanation": "Winning here does not mean staying. Sometimes the win is keeping your sanity intact long enough to engineer your exit.",
            },
            {
                "quote": "Fall down seven times, stand up eight. This is the spirit of a winner.",
                "source": "For Today and Tomorrow",
                "explanation": "The bad meeting, the unfair review, the colleague who undermines you - none of these get to write your professional story unless you let them.",
            },
            {
                "quote": "When we change ourselves, our world changes too. The environment is the mirror of our inner life.",
                "source": "For Today and Tomorrow",
                "explanation": "You cannot fix your boss. You can fix what time you go to bed, who you call after work, and what you let into your home from this place.",
            },
        ],
    },
    {
        "date": "2026-04-07",
        "theme": "life-and-death",
        "theme_name": "Life and Death",
        "title": "Grief Won't Let Go? 5 Truths When Time Hasn't Healed Anything",
        "struggles": ["when-grief-wont-stop"],
        "items": [
            {
                "quote": "Life and death are not separate. They are two aspects of the same life. To live deeply is to face death honestly.",
                "source": "The Wisdom for Creating Happiness and Peace",
                "explanation": "The grief is not a problem to fix. It is the love still doing what love does, after the person it was for has gone elsewhere.",
            },
            {
                "quote": "Those we have loved do not disappear. They live on in our hearts, in our actions, in the courage we draw from their memory.",
                "source": "For Today and Tomorrow",
                "explanation": "Your job is not to forget them. Your job is to keep carrying them - in how you eat dinner, what you laugh at, who you become.",
            },
            {
                "quote": "Hope is not a matter of ability; it is a matter of decision.",
                "source": "Discussions on Youth",
                "explanation": "Some days, hope means deciding to take a shower. Some days it means making one phone call. Grief gets to keep its size; you get to keep moving.",
            },
            {
                "quote": "Winter always turns to spring. Never, from ancient times on, has anyone heard or seen of winter that did not turn to spring.",
                "source": "The Writings of Nichiren Daishonin",
                "explanation": "The grief does not leave. It changes shape - from a wall you cannot get past to a room you can sometimes walk through.",
            },
            {
                "quote": "Gratitude is the seed of happiness. The ability to feel grateful, even amid hardship, is the mark of a strong heart.",
                "source": "For Today and Tomorrow",
                "explanation": "The fact that it hurts this much is the receipt that the love was real. Most people in this world will not be missed at this volume.",
            },
        ],
    },
]


def main():
    print(f"Backfilling {len(LISTICLES)} listicles for missing struggles...\n")
    for entry in LISTICLES:
        print(f"=== {entry['date']} | {entry['title'][:60]}... ===")
        print(f"  struggles: {entry['struggles']}")
        listicle = {
            "title": entry["title"],
            "items": entry["items"],
            "struggles": entry["struggles"],
            "theme": entry["theme"],
            "theme_name": entry["theme_name"],
        }
        print(f"  rendering hero...")
        hero = generate_hero(listicle)
        print(f"  rendering infographic...")
        infographic = generate_infographic(listicle)
        print(f"  rendering carousel cover...")
        carousel_cover = generate_carousel_cover(listicle)
        print(f"  rendering 5 carousel slides...")
        carousel_slides = [
            generate_carousel_slide(item, i + 1, 5, listicle["theme_name"])
            for i, item in enumerate(listicle["items"])
        ]
        print(f"  saving...")
        save_listicle(listicle, entry["date"], infographic, carousel_cover, carousel_slides, hero)
        print()
    print("DONE — 7 listicles backfilled. Zero API cost.")


if __name__ == "__main__":
    main()

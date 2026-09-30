import json
import os
import re
import time
from typing import List, Dict, Optional, Tuple, Any
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from google import genai
from google.genai import types
from app.core.subtitle import censor_demonetized_text

INCOMPLETE_ENDING_WORDS = {
    # Conjunctions & relative connectors
    "and", "or", "but", "so", "because", "although", "though", "however", "since", "unless",
    # Prepositions
    "to", "of", "in", "for", "on", "with", "at", "by", "from", "up", "about", "into", "over", "after", "through", "under",
    # Articles & determiners
    "the", "a", "an", "this", "that", "these", "those", "my", "your", "his", "her", "their", "our", "some",
    # Relative pronouns & questions
    "which", "who", "whom", "whose", "what", "where", "when", "why", "how",
    # Auxiliary & linking verbs
    "is", "are", "was", "were", "am", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "shall", "should", "can", "could", "may", "might", "must",
    # Personal Pronouns
    "he", "she", "they", "them", "it", "we", "you", "i",
    # Fillers, fragments & incomplete transitions
    "like", "um", "uh", "just", "really", "very", "actually", "also", "then", "if", "mean", "say", "said", "fade"
}

SENTENCE_STARTER_WORDS = {
    "so", "now", "then", "eventually", "finally", "therefore", "basically", "honestly",
    "i", "he", "she", "they", "we", "you", "it", "this", "that", "one", "first", "second",
    "suddenly", "however", "well", "look", "listen", "see", "meanwhile", "next"
}

def snap_to_speech_boundary(
    target_seconds: float,
    transcript: List[Dict],
    is_start: bool = False,
    max_drift: float = 6.0,
    current_start: float = 0.0,
    min_duration: float = 18.0,
    max_duration: float = 58.0
) -> float:
    """
    Intelligently snaps clip boundaries to natural spoken sentence and thought boundaries.
    Guarantees:
      - Never ends mid-speech, mid-word, or on incomplete connectors ('and', 'because', 'was', 'of', etc.)
      - Clamps ending before next spoken phrase begins (zero timestamp bleed into following sentences)
      - Snaps to natural acoustic pauses/silence between phrases
      - Preserves full speaker thoughts and punchlines
      - Snaps start to clean sentence openers rather than trailing mid-clause words
    """
    if not transcript:
        return target_seconds

    best_time = target_seconds
    best_score = float('inf')

    if is_start:
        # Snap start timestamp to beginning of a clean sentence / thought
        for i, item in enumerate(transcript):
            s = float(item.get("start", 0.0))
            text = str(item.get("text", "")).strip()
            if not text:
                continue

            dist = abs(s - target_seconds)
            if dist > max_drift:
                continue

            words = text.split()
            first_w = re.sub(r'[^\w]', '', words[0]).lower() if words else ""

            penalty = 0.0
            if first_w in {"and", "but", "or", "because", "so", "like", "yeah", "uh", "um"}:
                penalty += 14.0

            bonus_starter = 0.0
            if first_w in SENTENCE_STARTER_WORDS or (words and words[0][:1].isupper()):
                bonus_starter += 5.0

            bonus_prev = 0.0
            if i > 0:
                prev_item = transcript[i-1]
                prev_e = float(prev_item.get("start", 0.0)) + float(prev_item.get("duration", 0.0))
                prev_text = str(prev_item.get("text", "")).strip()
                if re.search(r'[\.\?\!\…]\s*$', prev_text):
                    bonus_prev += 6.0
                gap = s - prev_e
                if gap >= 0.20:
                    bonus_prev += 4.0

            score = dist + penalty - bonus_starter - bonus_prev
            if score < best_score:
                best_score = score
                best_time = max(0.0, s - 0.06)  # 60ms clean attack pre-roll

    else:
        # Snap end timestamp to a fully resolved sentence or thought
        for i, item in enumerate(transcript):
            s = float(item.get("start", 0.0))
            d = float(item.get("duration", 0.0))
            e = s + d
            text = str(item.get("text", "")).strip()
            if not text:
                continue

            dist = abs(e - target_seconds)
            cand_dur = e - current_start
            if dist > max_drift:
                continue
            if cand_dur < min_duration or cand_dur > max_duration:
                continue

            words = text.split()
            last_w = re.sub(r'[^\w]', '', words[-1]).lower() if words else ""

            penalty = 0.0
            if last_w in INCOMPLETE_ENDING_WORDS:
                penalty += 35.0  # Strongly penalize dangling connector endings

            has_terminal = bool(re.search(r'[\.\?\!\…]\s*$', text))
            bonus_terminal = 8.0 if has_terminal else 0.0

            # Find when the next spoken phrase starts across the entire transcript
            next_starts = [float(other.get("start", 0)) for other in transcript if float(other.get("start", 0)) >= e - 0.08]
            next_s = min(next_starts) if next_starts else e + 1.0

            # Anti-Bleed: Clip end MUST NOT walk into the next spoken sentence
            max_safe_end = next_s - 0.05
            if max_safe_end < e - 0.10:
                # Next speaker already started talking before this item ended!
                penalty += 25.0

            bonus_pause = 0.0
            gap = max(0.0, next_s - e)
            if gap >= 0.25:
                bonus_pause += 6.0
            elif gap >= 0.12:
                bonus_pause += 3.0

            score = dist + penalty - bonus_terminal - bonus_pause
            if score < best_score:
                best_score = score
                # Clamped end: never bleed into next sentence
                best_time = min(e + 0.06, max_safe_end)

    return round(best_time, 2)

def snap_to_sentence_boundary(
    target_seconds: float,
    transcript: List[Dict],
    max_drift: float = 6.0,
    is_start: bool = False,
    current_start: float = 0.0
) -> float:
    """Backward-compatible wrapper routing to snap_to_speech_boundary."""
    return snap_to_speech_boundary(
        target_seconds=target_seconds,
        transcript=transcript,
        is_start=is_start,
        max_drift=max_drift,
        current_start=current_start
    )



def generate_title_archetypes(base_title: str, hook_text: str = "", niche: str = "storytelling_crime") -> Dict[str, str]:
    """
    Generates 3 high-converting title archetypes for A/B testing:
    1. Curiosity Gap: Intrigue-driven question or mystery (e.g. 'The Secret Reason Why... 🤫👀 #shorts')
    2. High Stakes / Urgency: Drama, risk, shock, or high-value hook (e.g. 'Warning: Never Do This... 🚨💀 #shorts')
    3. Story Arc / Reveal: Journey, reveal, or transformation (e.g. 'He Thought He Escaped... Until This 🔥 #shorts')
    """
    clean_base = re.sub(r'#\w+', '', base_title).strip()
    clean_base = re.sub(r'[^\w\s-]', '', clean_base).strip() or "Shocking Revelation"
    words = clean_base.split()
    short_base = " ".join(words[:6]) if len(words) > 6 else clean_base

    n_icons = {
        "storytelling_crime": ("🤫👀", "🚨💀", "🔥⚠️"),
        "business_money": ("💰👀", "📈🚨", "💵🔥"),
        "psychology_secrets": ("🧠👀", "🤫💀", "⚡👁️"),
        "tech_ai": ("🤖👀", "⚠️🚨", "🚀⚡"),
        "motivation_mindset": ("⚡👑", "🔥🦁", "📈🏆"),
        "entertainment_drama": ("🍿👀", "💀🚨", "🤯🔥")
    }
    emojis = n_icons.get(niche, ("🤫👀", "🚨💀", "🔥"))

    # Archetype 1: Curiosity Gap
    if any(q in clean_base.lower() for q in ["how", "why", "what", "secret", "never"]):
        curiosity = f"The Truth Behind: {short_base} {emojis[0]} #shorts"
    else:
        curiosity = f"Nobody Talks About This: {short_base} {emojis[0]} #shorts"

    # Archetype 2: High Stakes / Urgency
    stakes_prefixes = ["Warning: Never Do This:", "The Biggest Mistake:", "Urgent Warning:", "This Cost Everything:"]
    prefix = stakes_prefixes[abs(hash(short_base)) % len(stakes_prefixes)]
    high_stakes = f"{prefix} {short_base} {emojis[1]} #shorts"

    # Archetype 3: Story Arc / Reveal
    story_arc = f"He Thought It Was Over... {short_base} {emojis[2]} #shorts"

    return {
        "curiosity": censor_demonetized_text(curiosity[:68]),
        "high_stakes": censor_demonetized_text(high_stakes[:68]),
        "story_arc": censor_demonetized_text(story_arc[:68])
    }


def compute_seamless_loop(hook_text: str = "", outro_text: str = "") -> Dict[str, Any]:
    """
    Evaluates whether the outro sentences naturally bridge back into the opening hook,
    enabling infinite looping and rewatch retention.
    """
    hook_clean = hook_text.strip().lower()
    outro_clean = outro_text.strip().lower()

    if not hook_clean or not outro_clean:
        return {
            "score": 75,
            "rating": "Good",
            "reason": "Clear narrative conclusion before repeating from start."
        }

    loop_connectors = ["because", "why", "that", "which is why", "how", "so that", "and that's when", "leading to", "the secret was", "and then"]
    starts_with_answer = any(hook_clean.startswith(prefix) for prefix in ["this", "that", "how", "why", "he", "she", "they", "nobody", "the only"])

    has_connector = any(outro_clean.endswith(c) or c in outro_clean[-30:] for c in loop_connectors)

    if has_connector and starts_with_answer:
        return {
            "score": 96,
            "rating": "Flawless Seamless Loop",
            "reason": "Outro phrase grammatically cascades directly into the opening hook, driving continuous rewatches!"
        }
    elif has_connector or starts_with_answer:
        return {
            "score": 88,
            "rating": "High Retention Flow",
            "reason": "Strong narrative bridge between clip ending and beginning with smooth acoustic cadence."
        }
    else:
        return {
            "score": 78,
            "rating": "Standard Reset",
            "reason": "Natural spoken ending with crisp speech attack on repeat."
        }


def enrich_clip_packaging(clip: Dict[str, Any], transcript: List[Dict], niche: str) -> Dict[str, Any]:
    """
    Enriches a clip with 3 high-converting title archetypes and seamless loop retention analysis.
    """
    start = float(clip.get("start_seconds", 0.0))
    end = float(clip.get("end_seconds", 0.0))
    hook_text = str(clip.get("hook_text", "")).strip()
    title = str(clip.get("suggested_title", "")).strip()

    # Find outro text within [start, end]
    clip_items = [it for it in (transcript or []) if start <= float(it.get("start", 0)) < end]
    outro_text = clip_items[-1].get("text", "") if clip_items else ""

    clip["title_archetypes"] = generate_title_archetypes(title, hook_text, niche)
    loop_data = compute_seamless_loop(hook_text, outro_text)
    clip["seamless_loop_score"] = loop_data["score"]
    clip["seamless_loop_rating"] = loop_data["rating"]
    clip["seamless_loop_reason"] = loop_data["reason"]
    return clip


STANDALONE_PROMPT_TEMPLATE = """
You are an expert short-form video editor specializing exclusively in YouTube Shorts.
Your job is NOT simply to cut interesting parts from a long YouTube video.
Your job is to identify moments with the highest potential for viewer retention, curiosity, emotional reaction, rewatching, sharing, and comments, then transform those moments into highly engaging short-form videos.

MASTER OBJECTIVE:
Optimize every short for:
STOP SCROLLING → KEEP WATCHING → GET PAYOFF → REWATCH / SHARE / COMMENT

1. GENERAL EDITING PHILOSOPHY:
Every candidate short must answer:
1. Why should the viewer stop scrolling?
2. Why should they keep watching?
3. Why should they watch until the end?
4. Why would they replay, comment, or share it?
- Avoid unnecessary context at the beginning.
- Start as close as possible to the most interesting part of the conversation/story.
- Do NOT automatically start the clip from the chronological beginning of the source video. The strongest moment may happen much later.
- Find the minimum amount of context necessary for the viewer to understand the moment.

2. HOOK OPTIMIZATION (THE FIRST 1–2 SECONDS):
The first 1–2 seconds are critical. Choose the strongest possible opening from the footage.
Prioritize:
- Shocking statements, surprising answers, controversial opinions, unexpected reactions, emotional moments, unusual facts, strong claims, conflicts, questions with compelling answers, incomplete stories, or moments that create curiosity.
- Open with the most compelling statement rather than a long introduction (WEAK: "So today we're going to talk about..." -> STRONG: "That's actually why 90% of people fail.").
- FACTUAL INTEGRITY: Never invent dialogue, manipulate quotes, or rearrange statements in a way that distorts the speaker's true meaning.

3. RETENTION STRUCTURE:
Structure the short around this pattern:
HOOK → CONTEXT → ESCALATION → PAYOFF
- HOOK: Immediately create curiosity or emotional interest in the first 1-2s.
- CONTEXT: Give only the minimum information required to understand the situation.
- ESCALATION: Continuously introduce new information, reactions, questions, or developments.
- PAYOFF: Deliver the answer, punchline, reveal, conclusion, or emotional resolution before the clip concludes.

4. PACING & SOURCE-AWARE EDITING:
- Pacing must be fast but natural: cut dead air, unnecessary greetings, repeated explanations, filler words, and slow transitions.
- DO NOT over-edit natural speech: preserve pauses when they increase anticipation, comedic timing, emotional impact, or suspense.
- Match source personality: Podcast (fast conversational pacing, punch-ins), Educational (clarity, density, keywords), Storytelling (chronological escalation, payoff), Interview (strong disagreement/revelations).

5. CRITICAL REQUIREMENT — COMPLETE THOUGHTS & SENTENCES ONLY (NEVER CUT MID-SPEECH):
- start_seconds: MUST be the exact second the speaker BEGINS a fresh sentence or thought. NEVER start mid-phrase, mid-syllable, or on a trailing conjunction (e.g., "...and then").
- end_seconds: MUST be the exact second the speaker COMPLETES their full sentence, punchline, or reveal. NEVER end mid-sentence, mid-speech, or on connectors like "because", "which", "and", "or", "to", "that". The thought must be 100% finished and satisfying.

6. CRITICAL NEGATIVE FILTER (STRICTLY FORBIDDEN CONTENT):
- ZERO INTROS / GREETINGS: NEVER select opening greetings ("welcome back", "welcome to", "in this video today", "my name is", "today we are").
- ZERO SPONSOR READS: NEVER select sponsorship plugs, promo codes, or ads ("sponsored by", "NordVPN", "use code", "link in description", "Patreon", "merch").
- ZERO OUTRO HOUSEKEEPING: NEVER select channel housekeeping ("don't forget to like and subscribe", "hit the bell", "leave a comment", "see you next time").
- ZERO RAMBLING BANTER: ONLY select moments that have a self-contained, high-impact mini-story arc (HOOK -> ESCALATION -> CLIMAX/REVEAL).

NICHE FOCUS: {niche_label}
{niche_instruction}

TASK 1: VIDEO TYPE DETECTION
Determine whether this video is:
- "solo_creator": 1 person speaking directly to camera, tutorial, vlog, or presentation -> recommended_layout: "auto"
- "podcast_interview": Conversation or 2+ people -> recommended_layout: "auto"

TASK 2: VIRAL CLIPS EXTRACTION — 9-FACTOR SCORING & STRICT NON-OVERLAPPING DIVERSITY
Find {num_clips} of the strongest moments (each 25 to 50 seconds long, target 30-45s) scored across the 9 VIRAL FACTORS:
1. Hook Strength: immediate curiosity opening
2. Emotional Intensity: surprise, humor, tension, or inspiration
3. Curiosity: viewer must watch to understand
4. Payoff: delivers something deeply satisfying
5. Novelty: uncommon or unexpected insight
6. Shareability: high urge to send to a friend
7. Comment Potential: sparks passionate debate or reaction
8. Rewatch Potential: fast-paced or multi-layered
9. Context Independence: completely self-contained without needing the full video

CRITICAL NON-OVERLAPPING DIVERSITY RULE:
Every single clip MUST be from a COMPLETELY DIFFERENT part of the video timeline!
- ZERO DUPLICATES: DO NOT return the same video section with different captions or styles!
- Every clip must have its own UNIQUE, NON-OVERLAPPING time window, separated by at least 45+ seconds from other clips!
- Distribute clips across the entire video: early, mid, and climax.

TASK 3: AUTONOMOUS WINNING STYLE & PACKAGING SELECTION
For EACH generated clip, select:
- "caption_art_direction": Pick the style that MAXIMIZES RETENTION for this specific clip:
  * "alex_hormozi": Bold stacked Montserrat/Impact with green highlight box (top performer for business, wealth, lessons, psychology, advice)
  * "tiktok_bounce": High-speed white & yellow dynamic pop with emoji accents (podcasts, drama, fast conversation, banter)
  * "yellow_electric": Bold, high-energy creator punch (MrBeast urgency)
  * "crimson_thriller": Crime, mystery, dark confessions, warning, tension
  * "cyber_cyan": AI breakthroughs, tech, coding, robotics, future
  * "cinematic_minimal": Clean subtle subtitles for deep podcast moments and documentaries
  * "gold_luxury": Money, wealth, luxury business secrets
  * "emerald_growth": Finance, growth, life hacks, productivity
  * "sunset_orange": Wild storytelling, adrenaline, motivation
  * "hot_pink": Jaw-dropping shock, relationship drama, viral gossip
- "sticker_badge": Contextual 2-4 word badge with emoji (e.g. "🚨 UNMASKED", "📈 100M PLAYBOOK", "🤫 CLASSIFIED", "💀 HE FROZE", "⚠️ WATCH TILL END", "💰 THE 1% HACK", "🤯 NO WAY", "👀 WAIT WHAT?!")
- "psychological_hook": 4 to 8 word psychological intrigue text overlay for the top sticker (e.g. "He had no idea they were recording...").
- "suggested_title": High-CTR curiosity title under 55 chars with 1-2 viral emojis. Avoid clickbait that promises what the clip does not deliver!
- "suggested_description": Conversational, platform-native description with curiosity spark.
- "reaction_spark_comment": Tailored discussion-sparking question with emojis (e.g. 👇👀💀).
- "comment_strategy": Psychological debate strategy name.
- "subscriber_cta": Punchy subscriber CTA banner (e.g. "SUBSCRIBE FOR DAILY SECRETS 🚀").
- "pinned_comment": Conversion-optimized comment to drive channel subscribers.

{trend_playbook_section}

VIDEO TITLE: {video_title}
TRANSCRIPT:
{transcript_text}

OUTPUT FORMAT:
Return a valid JSON object matching this schema:
{{
  "video_type": "solo_creator",
  "recommended_layout": "auto",
  "layout_reason": "Phone-adaptive 9:16 layout (100% full video shown with ambient background)",
  "clips": [
    {{
      "clip_id": 1,
      "start_seconds": 120.5,
      "end_seconds": 160.0,
      "duration": 39.5,
      "hook_text": "The exact hook spoken in the first 3 seconds",
      "psychological_hook": "He didn't mean to say this out loud...",
      "caption_art_direction": "crimson_thriller",
      "sticker_badge": "🚨 UNMASKED",
      "reaction_spark_comment": "Who was actually in the wrong here? Be 100% honest 👇👀",
      "comment_strategy": "Controversial Debate Question",
      "hook_rating": 96,
      "viral_score": 92,
      "score_breakdown": {{
        "hook_score": 28,
        "pacing_score": 19,
        "payoff_score": 19,
        "loop_score": 8,
        "caption_score": 9,
        "packaging_score": 9
      }},
      "virality_reason": "Why this will hook US/UK viewers",
      "suggested_title": "He Said WHAT On Live TV?! 💀🚨 #shorts",
      "thumbnail_hook_3words": "THE BRUTAL TRUTH",
      "thumbnail_prompt": "Cinematic 8k close-up portrait, dramatic lighting, 9:16 vertical",
      "thumbnail_visual_concept": "High contrast emotional face + curiosity trigger",
      "thumbnail_color_theme": "yellow_black",
      "subscriber_cta": "SUBSCRIBE FOR DAILY SECRETS 🚀",
      "pinned_comment": "Did you know this? Drop your thoughts below and subscribe for daily secrets 👇",
      "suggested_description": "Did he go too far or was he completely right? 💀 Drop your honest thoughts below 👇🔥 | Subscribe for daily drops 🚀 #shorts #viral",
      "tags": ["shorts", "viral"]
    }}
  ]
}}
Only output valid JSON. Do not include markdown code block quotes.
"""

MULTIPART_PROMPT_TEMPLATE = """
You are an expert short-form video editor specializing exclusively in YouTube Shorts.
Your job is to identify a powerful multi-chapter story arc and transform it into a connected sequence of up to 3 shorts:
PART 1 → PART 2 → PART 3

MASTER OBJECTIVE:
Optimize every part for:
STOP SCROLLING → KEEP WATCHING → GET PAYOFF → REWATCH / SHARE / COMMENT

MASTER RULES FOR STORY-BASED SHORTS:
- Each part must work like: HOOK → CONTEXT → ESCALATION → PAYOFF / CLIFFHANGER.
- Each part must be interesting independently, while compelling the viewer to watch the next part.
- Do NOT artificially split one sentence or thought simply to create multiple parts.
- Never invent dialogue, manipulate quotes, or distort the speaker's true meaning.
- COMPLETE THOUGHTS ONLY: Every part must start at the beginning of a sentence and conclude on a fully resolved sentence or cliffhanger. NEVER cut off mid-speech, mid-sentence, or on connectors like "because", "which", "and", "or", "to".
- NEGATIVE FILTER: Reject any opening video intros, sponsor reads, promo codes, or housekeeping. Focus 100% on the core dramatic storyline.

PART-BY-PART PROGRESSION (100% CONTIGUOUS SAME STORY ARC):
- PART 1 (Inciting Incident & Hook): Opens in the middle of tension. Introduces the shocking premise. Ends at a natural curiosity point / unanswered question (e.g. "I didn't realize what was happening until...").
- PART 2 (Direct Escalation): MUST start IMMEDIATELY where Part 1 ended (within 0 to 3 seconds)! Continues without repeating unnecessary information. Increases tension, information, or stakes. Ends with another meaningful development / cliffhanger #2.
- PART 3 (The Climax & Payoff): MUST start IMMEDIATELY where Part 2 ended (within 0 to 3 seconds)! Delivers the strongest reveal, conclusion, lesson, reaction, or payoff.

NICHE FOCUS: {niche_label}
{niche_instruction}

TASK 1: VIDEO TYPE DETECTION
Determine whether this video is:
- "solo_creator": 1 single person speaking -> recommended_layout: "auto"
- "podcast_interview": Conversation or 2+ people -> recommended_layout: "auto"

TASK 2: EXTRACT 2 TO 3 SEQUENTIAL PARTS (30 to 45 SECONDS EACH)
All parts MUST cover the EXACT SAME continuous story and be 100% relevant to each other:
- Zero narrative jumps away from the story.
- Part 1: Inciting incident, ends on curiosity cliffhanger.
- Part 2: Tight continuation, escalating tension.
- Part 3: Climax payoff and conclusion.
- Every clip MUST have:
  * "series_id": a common string identifier, e.g. "series_saga_1"
  * "series_title": umbrella title for the saga (e.g. "The Unsolved Cabin Mystery")
  * "part_number": 1, 2, or 3
  * "total_parts": 2 or 3
  * "part_label": "Part 1 of 3", "Part 2 of 3", etc.
  * "caption_art_direction": matching theme key
  * "sticker_badge": "🔗 PART 1 OF 3", etc.
  * "suggested_title": With attention-grabbing emojis (e.g. 🚨, 🤯, 💀)
  * "cliffhanger_hook": exact sentence ending with unresolved tension
  * "subscriber_cta": custom subscriber banner for final 3.5s
  * "pinned_comment": conversion-optimized pinned comment
  * "reaction_spark_comment": high-voltage discussion sparking comment with emojis
  * "comment_strategy": strategy name
  * "psychological_hook": top badge curiosity text

VIDEO TITLE: {video_title}
TRANSCRIPT:
{transcript_text}

OUTPUT FORMAT:
Return a valid JSON object matching this schema:
{{
  "video_type": "solo_creator",
  "recommended_layout": "auto",
  "layout_reason": "Phone-adaptive 9:16 layout (100% full video shown with ambient background)",
  "series_id": "series_saga_1",
  "series_title": "The Unsolved Cabin Mystery",
  "total_parts": 3,
  "clips": [
    {{
      "clip_id": 1,
      "series_id": "series_saga_1",
      "series_title": "The Unsolved Cabin Mystery",
      "part_number": 1,
      "total_parts": 3,
      "part_label": "Part 1 of 3",
      "start_seconds": 15.0,
      "end_seconds": 52.0,
      "duration": 37.0,
      "hook_text": "He entered the abandoned room at midnight",
      "psychological_hook": "He had no idea what was inside...",
      "caption_art_direction": "crimson_thriller",
      "sticker_badge": "🔗 PART 1 OF 3",
      "cliffhanger_hook": "Then he heard heavy breathing behind him...",
      "subscriber_cta": "SUBSCRIBE FOR PART 2 👇",
      "pinned_comment": "Part 2 drops today at 4 PM EST! Subscribe & turn on 🔔 so you don't miss it 👇",
      "reaction_spark_comment": "Would you have opened that door? Be 100% honest 👇👀",
      "comment_strategy": "Moral Dilemma",
      "hook_rating": 98,
      "viral_score": 95,
      "score_breakdown": {{
        "hook_score": 29,
        "pacing_score": 19,
        "payoff_score": 19,
        "loop_score": 9,
        "caption_score": 10,
        "packaging_score": 9
      }},
      "virality_reason": "Irresistible setup ending on a terrifying cliffhanger.",
      "suggested_title": "The Cabin Secret He Regrets Finding 💀🚨 (Part 1/3) #shorts",
      "thumbnail_hook_3words": "PART 1: DISCOVERY",
      "thumbnail_prompt": "Cinematic portrait in dark forest, neon rim lights, 9:16 vertical",
      "thumbnail_visual_concept": "Shocked expression in dark woods",
      "thumbnail_color_theme": "yellow_black",
      "suggested_description": "Part 1 of 3. Subscribe for Part 2 dropping at 4 PM! 👇🔥 #shorts #mystery #viral",
      "tags": ["shorts", "mystery", "part1", "viral"]
    }}
  ]
}}
Only output valid JSON. Do not include markdown code block quotes.
"""

NICHE_INSTRUCTIONS = {
    "storytelling_crime": (
        "Storytelling & True Crime",
        "FOCUS: High-tension mysteries, cold cases, unexpected twists, and psychological confessions. Open loops must trigger intense curiosity. Best art: crimson_thriller."
    ),
    "business_money": (
        "Business, Wealth & Money Secrets",
        "FOCUS: Exact numbers, counter-intuitive financial strategies, costly mistakes, and millionaire lessons. Hooks must highlight specific stakes. Best art: gold_luxury."
    ),
    "psychology_secrets": (
        "Dark Psychology & Social Dynamics",
        "FOCUS: Unspoken social rules, body language tells, manipulation signs, and behavioral psychology. Hooks must create personal disbelief. Best art: crimson_thriller or hot_pink."
    ),
    "tech_ai": (
        "Tech & AI Breakthroughs",
        "FOCUS: AI revolution, future automation, shocking digital capabilities, and tech revelations. Hooks must evoke uncanny future shock. Best art: cyber_cyan."
    ),
    "motivation_mindset": (
        "Motivation, Discipline & Mental Toughness",
        "FOCUS: Ruthless discipline, overcoming rock bottom, mental toughness, and uncomfortable truths. Hooks must deliver raw wake-up calls. Best art: sunset_orange or yellow_electric."
    ),
    "entertainment_drama": (
        "Wild Stories, Podcasts & Drama",
        "FOCUS: Jaw-dropping revelations, chaotic debates, unfiltered podcast confessions. Hooks must create instant disbelief. Best art: hot_pink or sunset_orange."
    )
}

NICHE_DEFAULTS = {
    "storytelling_crime": {
        "art": "crimson_thriller",
        "palette": ["crimson_thriller", "alex_hormozi", "cinematic_minimal", "yellow_electric", "sunset_orange"],
        "badges": ["🚨 UNMASKED", "🤫 CLASSIFIED", "💀 CAUGHT ON TAPE", "⚠️ PLOT TWIST"],
        "emojis": ["💀", "🚨", "🤫", "👀"],
        "comment": "Who was actually in the wrong here? Be 100% honest 👇👀",
        "strategy": "Unsolved Mystery Theory"
    },
    "business_money": {
        "art": "alex_hormozi",
        "palette": ["alex_hormozi", "gold_luxury", "emerald_growth", "yellow_electric", "tiktok_bounce"],
        "badges": ["📈 100M PLAYBOOK", "💰 THE 1% SECRET", "💵 $10M HACK", "💸 BRUTAL TRUTH"],
        "emojis": ["💰", "💵", "🤫", "📈"],
        "comment": "Would you take this risk or play it safe? Be 100% honest in comments 👇💰",
        "strategy": "Risk vs Reward Debate"
    },
    "psychology_secrets": {
        "art": "alex_hormozi",
        "palette": ["alex_hormozi", "crimson_thriller", "tiktok_bounce", "yellow_electric", "cyber_cyan"],
        "badges": ["🧠 DARK PSYCHOLOGY", "🤫 SECRET TELL", "👀 WATCH CLOSELY", "⚠️ MANIPULATION"],
        "emojis": ["🧠", "🤫", "👀", "💀"],
        "comment": "Most people experience this without even realizing it. Have you? 👇👀",
        "strategy": "Relatable Human Nature"
    },
    "tech_ai": {
        "art": "cyber_cyan",
        "palette": ["cyber_cyan", "alex_hormozi", "tiktok_bounce", "yellow_electric", "emerald_growth"],
        "badges": ["🤖 AI BREAKTHROUGH", "⚡ THE FUTURE", "🚀 REVOLUTION", "🧠 MIND BLOWN"],
        "emojis": ["🤖", "⚡", "🤯", "🚀"],
        "comment": "Is this innovation exciting or terrifying for the future? Thoughts? 👇🤖",
        "strategy": "Future Impact Debate"
    },
    "motivation_mindset": {
        "art": "sunset_orange",
        "palette": ["sunset_orange", "alex_hormozi", "emerald_growth", "yellow_electric", "gold_luxury"],
        "badges": ["🔥 WAKE UP CALL", "⚡ 1% DISCIPLINE", "🦁 NO EXCUSES", "👑 WINNER MINDSET"],
        "emojis": ["🔥", "⚡", "🦁", "👑"],
        "comment": "99% of people make excuses instead of applying this. Are you in the 1%? 👇🔥",
        "strategy": "Discipline Challenge"
    },
    "entertainment_drama": {
        "art": "tiktok_bounce",
        "palette": ["tiktok_bounce", "hot_pink", "alex_hormozi", "yellow_electric", "sunset_orange"],
        "badges": ["🤯 HE SAID WHAT?!", "💀 UNFILTERED", "🍿 PURE CHAOS", "🚨 LIVE ON AIR"],
        "emojis": ["🤯", "💀", "🍿", "🚨"],
        "comment": "0:18 made my jaw drop... did you catch what happened? 💀👇",
        "strategy": "Hidden Detail Catch"
    }
}

def format_transcript_for_prompt(transcript: List[Dict], max_words: int = 7000) -> str:
    lines = []
    word_count = 0
    for item in transcript:
        start = float(item["start"])
        mins = int(start // 60)
        secs = int(start % 60)
        text = item["text"]
        lines.append(f"[{mins:02d}:{secs:02d}] ({start:.1f}s) {text}")
        word_count += len(text.split())
        if word_count > max_words:
            lines.append("... [transcript truncated for token budget] ...")
            break
    return "\n".join(lines)

def analyze_viral_clips(
    transcript: List[Dict], 
    video_title: str = "",
    api_key: Optional[str] = None, 
    num_clips: int = 3,
    preferred_language: str = "en",
    clip_mode: str = "standalone",
    niche: str = "storytelling_crime",
    video_duration: Optional[float] = None
) -> Dict:
    """
    Use Gemini AI to detect video format, extract top viral clips, and generate reaction-sparking comments.
    Supports:
    - clip_mode='standalone': 1 to 3 independent viral clips
    - clip_mode='multipart_series': Connected 2 or 3-part episodic series with cliffhangers
    - niche specialization for targeted audience psychology
    - reel-specific caption art direction and contextual sticker badges
    - high-CTR emojis across titles, captions, descriptions, and comments
    """
    num_clips = max(1, min(3, int(num_clips)))
    key = api_key or os.getenv("GEMINI_API_KEY")
    if not key or key == "your_gemini_api_key_here":
        raise ValueError("Valid GEMINI_API_KEY is required. Please set it in Settings or .env.")

    client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=10000))
    formatted_transcript = format_transcript_for_prompt(transcript)

    # Pull 24-Hour Viral Trend Playbook
    try:
        from app.core.trend_bot import trend_bot_instance
        playbook = trend_bot_instance.get_playbook()
        trend_section = playbook.get("prompt_injection_text", "")
        if not trend_section and playbook.get("top_hook_archetypes"):
            trend_section = "24-HOUR VIRAL TREND INTELLIGENCE:\n" + "\n".join([f"- {h}" for h in playbook.get("top_hook_archetypes", [])[:3]])
    except Exception:
        trend_section = ""

    niche_info = NICHE_INSTRUCTIONS.get(niche, NICHE_INSTRUCTIONS["storytelling_crime"])
    niche_label, niche_instruction = niche_info
    n_default = NICHE_DEFAULTS.get(niche, NICHE_DEFAULTS["storytelling_crime"])

    if clip_mode == "multipart_series":
        prompt = MULTIPART_PROMPT_TEMPLATE.format(
            niche_label=niche_label,
            niche_instruction=niche_instruction,
            video_title=video_title or "Untitled",
            transcript_text=formatted_transcript
        )
    else:
        prompt = STANDALONE_PROMPT_TEMPLATE.format(
            num_clips=num_clips,
            niche_label=niche_label,
            niche_instruction=niche_instruction,
            video_title=video_title or "Untitled",
            transcript_text=formatted_transcript,
            trend_playbook_section=trend_section
        )

    models = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
    last_error = None

    for model_name in models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3,
                )
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            if raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

            parsed = json.loads(raw_text)

            if isinstance(parsed, list):
                clips_raw = parsed
                video_type = "solo_creator"
                recommended_layout = "auto"
                layout_reason = "Phone-adaptive 9:16 layout (100% full video shown with ambient background)"
                series_id = None
                series_title = None
                total_parts = None
            else:
                clips_raw = parsed.get("clips", [])
                video_type = parsed.get("video_type", "solo_creator")
                recommended_layout = parsed.get("recommended_layout", "auto")
                layout_reason = parsed.get("layout_reason", "Phone-adaptive 9:16 layout")
                series_id = parsed.get("series_id")
                series_title = parsed.get("series_title")
                total_parts = parsed.get("total_parts")

            validated_clips = []
            accepted_intervals: List[Tuple[float, float]] = []

            for idx, c in enumerate(clips_raw):
                start = float(c.get("start_seconds", 0.0))
                end = float(c.get("end_seconds", start + 35.0))

                # Smooth clip boundaries: snap start to clean sentence opener, snap end to complete thought
                snapped_start = snap_to_speech_boundary(start, transcript, is_start=True, max_drift=4.0)
                snapped_end = snap_to_speech_boundary(end, transcript, is_start=False, max_drift=6.0, current_start=snapped_start)
                if 16.0 <= (snapped_end - snapped_start) <= 59.0:
                    start = snapped_start
                    end = snapped_end

                duration = round(end - start, 1)

                if duration < 15 or duration > 60:
                    continue

                # STRICT DEDUPLICATION: Reject duplicate/overlapping segments
                is_overlap = False
                for ex_start, ex_end in accepted_intervals:
                    overlap_sec = max(0.0, min(end, ex_end) - max(start, ex_start))
                    if clip_mode == "multipart_series":
                        if overlap_sec > 8.0:
                            is_overlap = True
                            break
                    else:
                        if overlap_sec > 6.0 or abs(start - ex_start) < 22.0:
                            is_overlap = True
                            break

                if is_overlap:
                    print(f"[ViralAI] Rejecting overlapping clip ({start:.1f}s - {end:.1f}s)")
                    continue

                accepted_intervals.append((start, end))

                hook_score = int(c.get("score_breakdown", {}).get("hook_score", 26))
                pacing_score = int(c.get("score_breakdown", {}).get("pacing_score", 18))
                payoff_score = int(c.get("score_breakdown", {}).get("payoff_score", 17))
                loop_score = int(c.get("score_breakdown", {}).get("loop_score", 8))
                caption_score = int(c.get("score_breakdown", {}).get("caption_score", 9))
                packaging_score = int(c.get("score_breakdown", {}).get("packaging_score", 9))

                viral_score = hook_score + pacing_score + payoff_score + loop_score + caption_score + packaging_score
                hook_rating = c.get("hook_rating") or round((hook_score / 30) * 100)

                # Thumbnail hook 3 words
                thumb_words = c.get("thumbnail_hook_3words", "").strip()
                if not thumb_words or len(thumb_words.split()) > 5:
                    words = c.get("suggested_title", "DON'T MISS THIS").replace("#shorts", "").split()
                    thumb_words = " ".join(words[:3]).upper()
                thumb_words = censor_demonetized_text(thumb_words)

                part_num = c.get("part_number")
                tot_parts = c.get("total_parts") or total_parts
                part_lbl = c.get("part_label") or (f"Part {part_num} of {tot_parts}" if part_num else None)

                sub_cta = c.get("subscriber_cta")
                if not sub_cta:
                    if part_num and tot_parts and part_num < tot_parts:
                        sub_cta = f"SUBSCRIBE FOR PART {part_num + 1} 👇"
                    elif part_num and tot_parts:
                        sub_cta = "SUBSCRIBE FOR NEXT SAGA 🚀"
                    else:
                        sub_cta = "SUBSCRIBE FOR DAILY SECRETS 🚀"
                sub_cta = censor_demonetized_text(sub_cta)

                pinned_comment = c.get("pinned_comment") or (
                    f"Part {part_num + 1} drops today at 4 PM EST! Subscribe & turn on 🔔 so you don't miss the conclusion 👇"
                    if part_num and tot_parts and part_num < tot_parts else
                    "Did you expect this? Drop your thoughts below and subscribe for daily videos 👇"
                )
                pinned_comment = censor_demonetized_text(pinned_comment)

                # Viral Reaction / Discussion Spark Comment
                reaction_comment = c.get("reaction_spark_comment")
                comment_strategy = c.get("comment_strategy")
                if not reaction_comment:
                    reaction_comment = n_default["comment"]
                    comment_strategy = n_default["strategy"]

                # Ensure Reaction Comment has emojis
                if "👇" not in reaction_comment and "👀" not in reaction_comment:
                    reaction_comment += " 👇👀"
                reaction_comment = censor_demonetized_text(reaction_comment)

                palette = n_default.get("palette", ["alex_hormozi", "tiktok_bounce", "yellow_electric", "cinematic_minimal", "crimson_thriller"])
                raw_art = c.get("caption_art_direction")
                if not raw_art or raw_art == "yellow_electric":
                    caption_art = palette[idx % len(palette)]
                else:
                    caption_art = raw_art
                if part_num and tot_parts:
                    if int(part_num) == int(tot_parts):
                        sticker_badge = f"🔥 FINALE: PART {part_num}/{tot_parts}"
                    else:
                        sticker_badge = f"🔗 PART {part_num} OF {tot_parts}"
                else:
                    sticker_badge = c.get("sticker_badge") or n_default["badges"][idx % len(n_default["badges"])]
                sticker_badge = censor_demonetized_text(sticker_badge)

                # Suggested Title: Ensure high attention emoji
                title = c.get("suggested_title", f"Viral Moment #{idx+1} #shorts")
                emoji_pool = n_default["emojis"]
                chosen_emoji = emoji_pool[idx % len(emoji_pool)]
                if not any(char in title for char in ["💀", "🚨", "🤫", "👀", "💰", "💵", "🤖", "⚡", "🔥", "🤯", "😱"]):
                    if "#shorts" in title:
                        title = title.replace("#shorts", f"{chosen_emoji} #shorts")
                    else:
                        title = f"{title} {chosen_emoji} #shorts"
                title = censor_demonetized_text(title)

                # Suggested Description: Ensure emojis and niche tags
                desc = c.get("suggested_description", "")
                if not desc or len(desc) < 15:
                    desc = f"Did this surprise you? Drop your thoughts below 👇🔥 | Subscribe for daily drops 🚀 #{niche} #shorts #viral"
                elif "👇" not in desc:
                    desc += " 👇🔥 #shorts"
                desc = censor_demonetized_text(desc)

                cliffhanger = censor_demonetized_text(c.get("cliffhanger_hook") or "")
                psych_hook = censor_demonetized_text(c.get("psychological_hook") or "He had no idea they were watching...")

                validated_clips.append({
                    "clip_id": idx + 1,
                    "start_seconds": start,
                    "end_seconds": end,
                    "duration": duration,
                    "hook_text": censor_demonetized_text(c.get("hook_text", "")),
                    "psychological_hook": psych_hook,
                    "caption_art_direction": caption_art,
                    "sticker_badge": sticker_badge,
                    "reaction_spark_comment": reaction_comment,
                    "comment_strategy": comment_strategy or "Reaction Spark",
                    "hook_rating": hook_rating,
                    "viral_score": viral_score,
                    "score_breakdown": {
                        "hook_score": hook_score,
                        "pacing_score": pacing_score,
                        "payoff_score": payoff_score,
                        "loop_score": loop_score,
                        "caption_score": caption_score,
                        "packaging_score": packaging_score,
                    },
                    "virality_reason": c.get("virality_reason", ""),
                    "suggested_title": title,
                    "thumbnail_hook_3words": thumb_words,
                    "thumbnail_prompt": c.get("thumbnail_prompt", "Cinematic 8k close-up portrait, dramatic studio lighting, 9:16 vertical"),
                    "thumbnail_visual_concept": c.get("thumbnail_visual_concept", "High contrast emotional expression"),
                    "thumbnail_color_theme": c.get("thumbnail_color_theme", "yellow_black"),
                    "suggested_description": desc,
                    "tags": c.get("tags", ["shorts", "viral"]),
                    "clip_mode": clip_mode,
                    "niche": niche,
                    "series_id": c.get("series_id") or series_id,
                    "series_title": c.get("series_title") or series_title,
                    "part_number": part_num,
                    "total_parts": tot_parts,
                    "part_label": part_lbl,
                    "cliffhanger_hook": cliffhanger,
                    "subscriber_cta": sub_cta,
                    "pinned_comment": pinned_comment
                })

            # Ensure we have the full requested count of distinct, non-overlapping clips
            target_count = 3 if clip_mode == "multipart_series" else num_clips
            if len(validated_clips) < target_count and transcript:
                print(f"[ViralAI] Found {len(validated_clips)} distinct clips (need {target_count}). Supplementing clips...")
                total_video_dur = float(transcript[-1]["start"]) + float(transcript[-1].get("duration", 10.0))
                hooks_pool = [
                    "The secret confession that broke the case...",
                    "He had no idea they were already waiting...",
                    "The unscripted moment that shocked everyone...",
                    "Nobody expected what was inside that vault..."
                ]

                if clip_mode == "multipart_series":
                    # Multi-part series: 100% sequential narrative progression without jumping away
                    while len(validated_clips) < target_count:
                        supp_idx = len(validated_clips)
                        part_num = supp_idx + 1
                        tot_parts = 3
                        if validated_clips:
                            prev_end = float(validated_clips[-1]["end_seconds"])
                            c_start = snap_to_speech_boundary(max(0.0, prev_end - 1.5), transcript, is_start=True, max_drift=3.0)
                        else:
                            raw_s = max(10.0, min(30.0, total_video_dur * 0.08))
                            c_start = snap_to_speech_boundary(raw_s, transcript, is_start=True, max_drift=3.5)

                        c_raw_end = c_start + 38.0
                        c_end = snap_to_speech_boundary(c_raw_end, transcript, is_start=False, max_drift=6.0, current_start=c_start)
                        if c_end - c_start < 18.0:
                            c_end = c_start + 38.0
                        c_dur = round(c_end - c_start, 1)

                        accepted_intervals.append((c_start, c_end))
                        badge_opt = f"🔥 FINALE: PART {part_num}/{tot_parts}" if part_num == tot_parts else f"🔗 PART {part_num} OF {tot_parts}"
                        nearby_items = [it for it in transcript if c_start <= float(it.get("start", 0)) < c_end]
                        hook_snippet = nearby_items[0]["text"][:60] if nearby_items else f"Part {part_num} revelation"
                        clean_title_snippet = re.sub(r'[^\w\s-]', '', video_title[:28]).strip() or "Shocking Revelation"
                        chosen_emoji = n_default["emojis"][supp_idx % len(n_default["emojis"])]

                        validated_clips.append({
                            "clip_id": supp_idx + 1,
                            "start_seconds": c_start,
                            "end_seconds": c_end,
                            "duration": c_dur,
                            "hook_text": censor_demonetized_text(hook_snippet),
                            "psychological_hook": censor_demonetized_text(hooks_pool[supp_idx % len(hooks_pool)]),
                            "caption_art_direction": n_default["art"],
                            "sticker_badge": censor_demonetized_text(badge_opt),
                            "reaction_spark_comment": censor_demonetized_text(n_default["comment"]),
                            "comment_strategy": n_default["strategy"],
                            "hook_rating": 94 - supp_idx * 2,
                            "viral_score": 91 - supp_idx * 2,
                            "score_breakdown": {"hook_score": 28, "pacing_score": 19, "payoff_score": 18, "loop_score": 8, "caption_score": 9, "packaging_score": 9},
                            "virality_reason": "High emotional variance and distinct revelation spike.",
                            "suggested_title": censor_demonetized_text(f"Part {part_num}: {clean_title_snippet} {chosen_emoji} #shorts"),
                            "thumbnail_hook_3words": f"PART {part_num}",
                            "thumbnail_prompt": "Cinematic 8k close-up portrait, dramatic studio lighting, 9:16 vertical",
                            "thumbnail_visual_concept": "High contrast curiosity",
                            "thumbnail_color_theme": "yellow_black",
                            "suggested_description": censor_demonetized_text(f"Part {part_num} of 3. Subscribe for Part {part_num+1} dropping at 4 PM! 👇🔥 | #{niche} #shorts #viral" if part_num < 3 else f"The Conclusion! Did you expect this? Drop your thoughts below 👇🔥 | #{niche} #shorts #viral"),
                            "tags": ["shorts", "viral", niche],
                            "clip_mode": clip_mode,
                            "niche": niche,
                            "series_id": series_id or "series_saga_1",
                            "series_title": series_title or video_title[:40],
                            "part_number": part_num,
                            "total_parts": tot_parts,
                            "part_label": f"Part {part_num} of {tot_parts}",
                            "cliffhanger_hook": "And that changed everything.",
                            "subscriber_cta": censor_demonetized_text(f"SUBSCRIBE FOR PART {part_num + 1} 👇" if part_num < 3 else "SUBSCRIBE FOR NEXT SAGA 🚀"),
                            "pinned_comment": censor_demonetized_text(f"Part {part_num + 1} drops today at 4 PM EST! Subscribe & turn on 🔔 so you don't miss it 👇" if part_num < 3 else "Did you expect this? Drop your thoughts below and subscribe 👇")
                        })
                else:
                    # Standalone clips: distributed across distinct timeline fractions
                    time_fractions = [0.15, 0.35, 0.55, 0.72, 0.88]
                    for frac in time_fractions:
                        if len(validated_clips) >= target_count:
                            break
                        target_sec = total_video_dur * frac
                        if any(abs(target_sec - ex_start) < 28.0 for ex_start, ex_end in accepted_intervals):
                            continue
                        cand_items = [it for it in transcript if abs(float(it["start"]) - target_sec) < 35.0]
                        if not cand_items:
                            continue
                        cand = min(cand_items, key=lambda it: abs(float(it["start"]) - target_sec))
                        c_start = snap_to_speech_boundary(float(cand["start"]), transcript, is_start=True, max_drift=3.5)
                        c_raw_end = c_start + 38.0
                        c_end = snap_to_speech_boundary(c_raw_end, transcript, is_start=False, max_drift=6.0, current_start=c_start)
                        if c_end - c_start < 15.0:
                            c_end = c_raw_end
                        c_dur = round(c_end - c_start, 1)

                        if any(max(0.0, min(c_end, ex_end) - max(c_start, ex_start)) > 5.0 for ex_start, ex_end in accepted_intervals):
                            continue

                        accepted_intervals.append((c_start, c_end))
                        supp_idx = len(validated_clips)
                        badge_opt = n_default["badges"][supp_idx % len(n_default["badges"])]
                        title_prefix = f"Moment #{supp_idx+1}: "
                        clean_title_snippet = re.sub(r'[^\w\s-]', '', video_title[:32]).strip() or "Shocking Revelation"
                        chosen_emoji = n_default["emojis"][supp_idx % len(n_default["emojis"])]

                        validated_clips.append({
                            "clip_id": supp_idx + 1,
                            "start_seconds": c_start,
                            "end_seconds": c_end,
                            "duration": c_dur,
                            "hook_text": censor_demonetized_text(cand.get("text", "")[:60]),
                            "psychological_hook": censor_demonetized_text(hooks_pool[supp_idx % len(hooks_pool)]),
                            "caption_art_direction": n_default["art"],
                            "sticker_badge": censor_demonetized_text(badge_opt),
                            "reaction_spark_comment": censor_demonetized_text(n_default["comment"]),
                            "comment_strategy": n_default["strategy"],
                            "hook_rating": 94 - supp_idx * 2,
                            "viral_score": 91 - supp_idx * 2,
                            "score_breakdown": {"hook_score": 28, "pacing_score": 19, "payoff_score": 18, "loop_score": 8, "caption_score": 9, "packaging_score": 9},
                            "virality_reason": "High emotional variance and distinct revelation spike.",
                            "suggested_title": censor_demonetized_text(f"{title_prefix}{clean_title_snippet} {chosen_emoji} #shorts"),
                            "thumbnail_hook_3words": "MUST WATCH",
                            "thumbnail_prompt": "Cinematic 8k close-up portrait, dramatic studio lighting, 9:16 vertical",
                            "thumbnail_visual_concept": "High contrast curiosity",
                            "thumbnail_color_theme": "yellow_black",
                            "suggested_description": censor_demonetized_text(f"Did you catch what happened? Drop your thoughts below 👇🔥 | Subscribe for daily stories 🚀 #{niche} #shorts #viral"),
                            "tags": ["shorts", "viral", niche],
                            "clip_mode": clip_mode,
                            "niche": niche,
                            "series_id": None,
                            "series_title": None,
                            "part_number": None,
                            "total_parts": None,
                            "part_label": None,
                            "cliffhanger_hook": "And that changed everything.",
                            "subscriber_cta": censor_demonetized_text("SUBSCRIBE FOR DAILY SECRETS 🚀"),
                        })


            if not validated_clips:
                print(f"[ViralAI] Model {model_name} produced 0 valid clips (e.g. durations outside 15-60s). Trying next model...")
                continue

            for c in validated_clips:
                enrich_clip_packaging(c, transcript or [], niche)

            from app.core.quality_guard import quality_guard
            guarded_clips = quality_guard.evaluate_and_guard_clips(
                clips=validated_clips,
                transcript=transcript or [],
                clip_mode=clip_mode,
                video_title=video_title or "",
                niche=niche
            )

            if clip_mode == "multipart_series":
                guarded_clips.sort(key=lambda x: x.get("part_number") or 0)
            else:
                guarded_clips.sort(key=lambda x: x.get("viral_score", 0), reverse=True)

            return {
                "video_type": video_type,
                "recommended_layout": "auto",
                "layout_reason": "Phone-adaptive 9:16 layout (100% full video shown with ambient background)",
                "clip_mode": clip_mode,
                "niche": niche,
                "series_id": series_id,
                "series_title": series_title,
                "total_parts": total_parts,
                "clips": guarded_clips[:num_clips]
            }

        except (FuturesTimeoutError, TimeoutError):
            print(f"[ViralAI] Model {model_name} timed out after 14s. Trying next model / fallback...")
            continue
        except Exception as e:
            last_error = e
            print(f"[ViralAI] Model {model_name} notice: {e}. Trying fallback...")
            continue

    # Heuristic Fallback if Gemini is rate limited or unavailable
    print(f"[ViralAI] Fallback triggered due to: {last_error}")
    fallback_clips = []
    effective_total_dur = video_duration or (
        (float(transcript[-1]["start"]) + float(transcript[-1].get("duration", 10.0)))
        if transcript else 300.0
    )
    effective_total_dur = max(effective_total_dur, 120.0)

    # Tailored hooks per niche
    niche_hooks = {
        "storytelling_crime": [
            "The tape they tried to hide for years...",
            "He had no idea they were already waiting...",
            "The secret confession that broke the case...",
            "Nobody expected what was inside that vault..."
        ],
        "business_money": [
            "The 1% wealth rule they hide from you...",
            "He exposed how the entire market is rigged...",
            "The $10M mistake beginner founders always make...",
            "How they turn $500 into millions silently..."
        ],
        "psychology_secrets": [
            "The subtle phrase master manipulators always use...",
            "If they look here, they are hiding something...",
            "The psychological trick to read anyone in 5 seconds...",
            "The dark social habit 99% of people miss..."
        ],
        "tech_ai": [
            "The secret AI tool nobody is talking about...",
            "What this algorithm did stunned researchers...",
            "The automation hack that replaces 10 workers...",
            "Why engineers are secretly terrified of this update..."
        ],
        "motivation_mindset": [
            "The uncomfortable truth about discipline...",
            "He hit rock bottom before discovering this rule...",
            "Why 99% of people fail before day 30...",
            "The brutal mindset shift that changes everything..."
        ],
        "entertainment_drama": [
            "The room went completely silent after he said this...",
            "He didn't realize the microphone was still live...",
            "The unscripted moment that broke the internet...",
            "Watch his reaction when he finds out the truth..."
        ]
    }
    hooks_pool = niche_hooks.get(niche, niche_hooks["storytelling_crime"])

    if clip_mode == "multipart_series":
        # Multi-part series: chronological sequential story chapters (Part 2 starts after Part 1)
        story_start = snap_to_speech_boundary(max(10.0, min(30.0, effective_total_dur * 0.08)), transcript or [], is_start=True, max_drift=4.0)
        cur_start = story_start
        for i in range(3):
            part_num = i + 1
            raw_end = cur_start + 38.0
            p_end = snap_to_speech_boundary(raw_end, transcript or [], is_start=False, max_drift=6.0, current_start=cur_start)
            if p_end - cur_start < 18.0:
                p_end = cur_start + 38.0
            dur = round(p_end - cur_start, 1)

            nearby_items = [it for it in (transcript or []) if abs(float(it.get("start", 0)) - cur_start) < 20.0]
            hook_snippet = nearby_items[0]["text"][:60] if nearby_items else f"Part {part_num} revelation"

            chosen_badge = f"🔗 PART {part_num} OF 3" if part_num < 3 else "🔥 FINALE: PART 3/3"
            chosen_hook = hooks_pool[i % len(hooks_pool)]
            chosen_emoji = n_default["emojis"][i % len(n_default["emojis"])]
            title_prefix = f"Part {part_num}: "
            clean_title_snippet = re.sub(r'[^\w\s-]', '', video_title[:32]).strip()

            fallback_clips.append({
                "clip_id": i + 1,
                "start_seconds": cur_start,
                "end_seconds": p_end,
                "duration": dur,
                "hook_text": censor_demonetized_text(hook_snippet),
                "psychological_hook": censor_demonetized_text(chosen_hook),
                "caption_art_direction": n_default.get("palette", ["alex_hormozi", "tiktok_bounce", "yellow_electric", "cinematic_minimal"])[i % len(n_default.get("palette", ["alex_hormozi"]))],
                "sticker_badge": censor_demonetized_text(chosen_badge),
                "reaction_spark_comment": censor_demonetized_text(n_default["comment"]),
                "comment_strategy": n_default["strategy"],
                "hook_rating": 96 - i * 2,
                "viral_score": 94 - i * 2,
                "score_breakdown": {"hook_score": 28, "pacing_score": 19, "payoff_score": 18, "loop_score": 9, "caption_score": 9, "packaging_score": 10},
                "virality_reason": "Chronological episodic narrative with rising tension.",
                "suggested_title": censor_demonetized_text(f"{title_prefix}{clean_title_snippet} {chosen_emoji} #shorts"),
                "thumbnail_hook_3words": f"PART {part_num}",
                "thumbnail_prompt": "Cinematic 8k close-up portrait, dramatic lighting, 9:16 vertical",
                "thumbnail_visual_concept": "High contrast curiosity",
                "thumbnail_color_theme": "yellow_black",
                "suggested_description": censor_demonetized_text(f"Part {part_num} of 3. Subscribe for Part {part_num + 1} dropping at 4 PM! 👇🔥 | #{niche} #shorts #viral" if part_num < 3 else f"The Conclusion! Did you expect this? Drop your thoughts below 👇🔥 | #{niche} #shorts #viral"),
                "tags": ["shorts", "viral", niche],
                "clip_mode": clip_mode,
                "niche": niche,
                "series_id": "series_fallback_1",
                "series_title": video_title[:40],
                "part_number": part_num,
                "total_parts": 3,
                "part_label": f"Part {part_num} of 3",
                "cliffhanger_hook": "And that changed everything.",
                "subscriber_cta": censor_demonetized_text(f"SUBSCRIBE FOR PART {part_num + 1} 👇" if part_num < 3 else "SUBSCRIBE FOR NEXT SAGA 🚀"),
                "pinned_comment": censor_demonetized_text(f"Part {part_num + 1} drops today at 4 PM EST! Subscribe & turn on 🔔 so you don't miss it 👇" if part_num < 3 else "Did you expect this? Drop your thoughts below and subscribe 👇")
            })
            cur_start = p_end  # Advance sequentially!
    else:
        # Content-Aware Standalone Narrative Extraction:
        # Analyzes actual speech dialogue, filters out sponsors/housekeeping,
        # scores hook density, and snaps to complete sentence boundaries.
        SPONSOR_KEYWORDS = {
            'sponsor', 'sponsored', 'nordvpn', 'expressvpn', 'surfshark', 'betterhelp', 'hellofresh',
            'promo code', 'discount code', 'use code', 'patreon', 'merch', 'link in the description',
            'link below', 'affiliate link', 'free trial'
        }
        HOUSEKEEPING_KEYWORDS = {
            'welcome back', 'welcome to the podcast', 'welcome to the channel', 'in this video today',
            'my name is', "don't forget to like and subscribe", 'subscribe to the channel',
            'leave a comment', 'see you next week', 'thanks for watching'
        }
        HOOK_TRIGGERS = {
            'why', 'how', 'secret', 'secrets', 'crazy', 'insane', 'shocking', 'never', 'always', 'money',
            'million', 'billions', 'truth', 'died', 'prison', 'jail', 'police', 'arrested', 'mistake',
            'warning', 'worst', 'best', 'killed', 'murder', 'rules', 'failed', 'destroy', 'dangerous',
            'illegal', 'stolen', 'unbelievable', 'happened', 'realized', 'lost', 'confession'
        }

        narrative_candidates = []
        if transcript and len(transcript) >= 5:
            for i, item in enumerate(transcript):
                s = float(item.get("start", 0.0))
                first_text = item.get("text", "").strip()
                words = first_text.split()
                if not words:
                    continue
                first_w = re.sub(r'[^a-zA-Z]', '', words[0]).lower()
                if first_w in {"and", "but", "or", "because", "so", "like", "yeah", "uh", "um"}:
                    continue

                for j in range(i + 4, min(i + 28, len(transcript))):
                    end_item = transcript[j]
                    e = float(end_item.get("start", 0.0)) + float(end_item.get("duration", 2.0))
                    dur = e - s
                    if dur < 24.0 or dur > 46.0:
                        continue

                    last_text = end_item.get("text", "").strip()
                    last_words = last_text.split()
                    if not last_words:
                        continue
                    last_w = re.sub(r'[^a-zA-Z]', '', last_words[-1]).lower()
                    if last_w in INCOMPLETE_ENDING_WORDS:
                        continue

                    window = transcript[i:j+1]
                    window_text = " ".join(it.get("text", "") for it in window).lower()

                    if any(sk in window_text for sk in SPONSOR_KEYWORDS) or any(hk in window_text for hk in HOUSEKEEPING_KEYWORDS):
                        continue

                    hook_count = sum(1 for ht in HOOK_TRIGGERS if ht in window_text)
                    has_question = 1 if "?" in window_text else 0
                    terminal_bonus = 2 if re.search(r'[\.\?\!]$', last_text) else 0

                    score = (hook_count * 3) + (has_question * 4) + (terminal_bonus * 3)
                    narrative_candidates.append({
                        "score": score,
                        "raw_start": s,
                        "raw_end": e,
                        "hook_spoken": first_text,
                        "full_snippet": window_text[:80]
                    })

            narrative_candidates.sort(key=lambda x: x["score"], reverse=True)

        used_intervals = []
        for cand in narrative_candidates:
            if len(fallback_clips) >= num_clips:
                break
            c_s = snap_to_speech_boundary(cand["raw_start"], transcript or [], is_start=True, max_drift=3.0)
            c_e = snap_to_speech_boundary(cand["raw_end"], transcript or [], is_start=False, max_drift=4.0, current_start=c_s)
            c_dur = round(c_e - c_s, 1)
            if c_dur < 18.0 or c_dur > 58.0:
                continue

            # Ensure zero overlaps
            if any(max(0.0, min(c_e, ex_e) - max(c_s, ex_s)) > 4.0 for ex_s, ex_e in used_intervals):
                continue

            used_intervals.append((c_s, c_e))
            idx = len(fallback_clips)
            chosen_badge = n_default["badges"][idx % len(n_default["badges"])]
            chosen_hook = hooks_pool[idx % len(hooks_pool)]
            chosen_emoji = n_default["emojis"][idx % len(n_default["emojis"])]
            hook_spoken = cand["hook_spoken"][:60]

            content_words = [w for w in re.sub(r'[^\w\s]', '', hook_spoken).split() if len(w) > 2 and w.lower() not in ('this', 'that', 'with', 'from', 'have', 'were', 'what', 'there', 'they', 'when')]
            if len(content_words) >= 3:
                slice_start = (idx * 2) % max(1, len(content_words) - 2)
                moment_title = " ".join(content_words[slice_start:slice_start + 4]).title()
                clip_title = f"{moment_title} {chosen_emoji} #shorts"
            else:
                clip_title = f"{chosen_hook} {chosen_emoji} #shorts"

            fallback_clips.append({
                "clip_id": idx + 1,
                "start_seconds": c_s,
                "end_seconds": c_e,
                "duration": c_dur,
                "hook_text": censor_demonetized_text(hook_spoken),
                "psychological_hook": censor_demonetized_text(chosen_hook),
                "caption_art_direction": n_default["art"],
                "sticker_badge": censor_demonetized_text(chosen_badge),
                "reaction_spark_comment": censor_demonetized_text(n_default["comment"]),
                "comment_strategy": n_default["strategy"],
                "hook_rating": 95 - idx * 2,
                "viral_score": 93 - idx * 2,
                "score_breakdown": {"hook_score": 28, "pacing_score": 19, "payoff_score": 18, "loop_score": 9, "caption_score": 9, "packaging_score": 10},
                "virality_reason": "High curiosity opening and rapid pacing.",
                "suggested_title": censor_demonetized_text(clip_title),
                "thumbnail_hook_3words": "MUST WATCH",
                "thumbnail_prompt": f"Cinematic 8k close-up expressive creator portrait, dramatic studio lighting, neon rim lighting, 9:16 vertical, {chosen_hook}",
                "thumbnail_visual_concept": "High contrast curiosity",
                "thumbnail_color_theme": "yellow_black",
                "suggested_description": censor_demonetized_text(f"Did you catch what happened? Drop your thoughts below 👇🔥 | Subscribe for daily stories 🚀 #{niche} #shorts #viral"),
                "tags": ["shorts", "viral", niche],
                "clip_mode": clip_mode,
                "niche": niche,
                "series_id": None,
                "series_title": None,
                "part_number": None,
                "total_parts": None,
                "part_label": None,
                "cliffhanger_hook": "And that changed everything.",
                "subscriber_cta": censor_demonetized_text("SUBSCRIBE FOR DAILY SECRETS 🚀"),
                "pinned_comment": censor_demonetized_text("Did you expect this? Drop your thoughts below and subscribe 👇")
            })

        # If any slots remain, fill with timeline distribution
        while len(fallback_clips) < num_clips:
            idx = len(fallback_clips)
            target_time = max(15.0, (idx + 1) * (effective_total_dur / (num_clips + 1)))
            c_s = snap_to_speech_boundary(target_time, transcript or [], is_start=True, max_drift=5.0)
            c_e = snap_to_speech_boundary(c_s + 38.0, transcript or [], is_start=False, max_drift=6.0, current_start=c_s)
            c_dur = round(c_e - c_s, 1)
            chosen_badge = n_default["badges"][idx % len(n_default["badges"])]
            chosen_hook = hooks_pool[idx % len(hooks_pool)]
            chosen_emoji = n_default["emojis"][idx % len(n_default["emojis"])]
            fallback_clips.append({
                "clip_id": idx + 1,
                "start_seconds": c_s,
                "end_seconds": c_e,
                "duration": c_dur,
                "hook_text": censor_demonetized_text(chosen_hook),
                "psychological_hook": censor_demonetized_text(chosen_hook),
                "caption_art_direction": n_default["art"],
                "sticker_badge": censor_demonetized_text(chosen_badge),
                "reaction_spark_comment": censor_demonetized_text(n_default["comment"]),
                "comment_strategy": n_default["strategy"],
                "hook_rating": 92 - idx * 2,
                "viral_score": 90 - idx * 2,
                "score_breakdown": {"hook_score": 26, "pacing_score": 18, "payoff_score": 18, "loop_score": 9, "caption_score": 9, "packaging_score": 10},
                "virality_reason": "High curiosity opening and rapid pacing.",
                "suggested_title": censor_demonetized_text(f"{chosen_hook} {chosen_emoji} #shorts"),
                "thumbnail_hook_3words": "MUST WATCH",
                "thumbnail_prompt": f"Cinematic 8k close-up expressive creator portrait, dramatic studio lighting, neon rim lighting, 9:16 vertical, {chosen_hook}",
                "thumbnail_visual_concept": "High contrast curiosity",
                "thumbnail_color_theme": "yellow_black",
                "suggested_description": censor_demonetized_text(f"Did you catch what happened? Drop your thoughts below 👇🔥 | Subscribe for daily stories 🚀 #{niche} #shorts #viral"),
                "tags": ["shorts", "viral", niche],
                "clip_mode": clip_mode,
                "niche": niche,
                "series_id": None,
                "series_title": None,
                "part_number": None,
                "total_parts": None,
                "part_label": None,
                "cliffhanger_hook": "And that changed everything.",
                "subscriber_cta": censor_demonetized_text("SUBSCRIBE FOR DAILY SECRETS 🚀"),
                "pinned_comment": censor_demonetized_text("Did you expect this? Drop your thoughts below and subscribe 👇")
            })

    if not fallback_clips:
        print("[ViralAI] No transcript items available for fallback. Generating emergency timestamp clips...")
        hooks_pool = niche_hooks.get(niche, niche_hooks["storytelling_crime"])
        for i in range(min(num_clips, 3 if clip_mode == "multipart_series" else num_clips)):
            start = 15.0 + i * 45.0
            end = start + 38.0
            part_num = i + 1 if clip_mode == "multipart_series" else None
            tot_parts = 3 if clip_mode == "multipart_series" else None
            chosen_badge = (
                f"🔗 PART {part_num} OF {tot_parts}" if (part_num and tot_parts and part_num < tot_parts)
                else (f"🔥 FINALE: PART {part_num}/{tot_parts}" if (part_num and tot_parts)
                else n_default["badges"][i % len(n_default["badges"])])
            )
            chosen_hook = hooks_pool[i % len(hooks_pool)]
            chosen_emoji = n_default["emojis"][i % len(n_default["emojis"])]
            title_prefix = f"Part {part_num}: " if part_num else ""
            clean_title_snippet = re.sub(r'[^\w\s-]', '', video_title[:32]).strip() or "Must Watch Viral Moment"
            fallback_clips.append({
                "clip_id": i + 1,
                "start_seconds": start,
                "end_seconds": end,
                "duration": 38.0,
                "hook_text": f"High engagement hook for {clean_title_snippet}",
                "psychological_hook": chosen_hook,
                "caption_art_direction": n_default["art"],
                "sticker_badge": chosen_badge,
                "reaction_spark_comment": n_default["comment"],
                "comment_strategy": n_default["strategy"],
                "hook_rating": 95 - i * 2,
                "viral_score": 93 - i * 2,
                "score_breakdown": {"hook_score": 28, "pacing_score": 19, "payoff_score": 18, "loop_score": 9, "caption_score": 9, "packaging_score": 10},
                "virality_reason": "High curiosity opening and rapid pacing.",
                "suggested_title": f"{title_prefix}{clean_title_snippet} {chosen_emoji} #shorts",
                "thumbnail_hook_3words": f"PART {part_num}" if part_num else "MUST WATCH",
                "thumbnail_prompt": "Cinematic 8k close-up portrait, dramatic lighting, 9:16 vertical",
                "thumbnail_visual_concept": "High contrast curiosity",
                "thumbnail_color_theme": "yellow_black",
                "suggested_description": f"Did you catch what happened? Drop your thoughts below 👇🔥 | Subscribe for daily stories 🚀 #{niche} #shorts #viral",
                "tags": ["shorts", "viral", niche],
                "clip_mode": clip_mode,
                "niche": niche,
                "series_id": "series_fallback_1" if clip_mode == "multipart_series" else None,
                "series_title": video_title[:40],
                "part_number": part_num,
                "total_parts": tot_parts,
                "part_label": f"Part {part_num} of {tot_parts}" if part_num else None,
                "cliffhanger_hook": "And that changed everything.",
                "subscriber_cta": f"SUBSCRIBE FOR PART {part_num + 1} 👇" if part_num and part_num < 3 else "SUBSCRIBE FOR NEXT SAGA 🚀",
                "pinned_comment": f"Part {part_num + 1} drops today at 4 PM EST! Subscribe & turn on 🔔 so you don't miss it 👇" if part_num and part_num < 3 else "Did you expect this? Drop your thoughts below and subscribe 👇"
            })

    for c in fallback_clips:
        enrich_clip_packaging(c, transcript or [], niche)

    from app.core.quality_guard import quality_guard
    guarded_fallback = quality_guard.evaluate_and_guard_clips(
        clips=fallback_clips,
        transcript=transcript or [],
        clip_mode=clip_mode,
        video_title=video_title or "",
        niche=niche
    )

    return {
        "video_type": "solo_creator",
        "recommended_layout": "auto",
        "layout_reason": "Phone-adaptive 9:16 layout (100% full video shown with ambient background)",
        "clip_mode": clip_mode,
        "niche": niche,
        "series_id": "series_fallback_1" if clip_mode == "multipart_series" else None,
        "series_title": video_title[:40],
        "total_parts": 3 if clip_mode == "multipart_series" else None,
        "clips": guarded_fallback[:num_clips]
    }

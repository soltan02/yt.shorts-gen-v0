import os
import re
from typing import List, Dict, Optional, Tuple
from app.core.caption_bot import review_and_optimize_captions

CAPTION_ART_DIRECTIONS = {
    "yellow_electric": {
        "name": "Electric Yellow (MrBeast/Punchy)",
        "highlight_ass": "&H0000FFFF&",
        "font": "Impact",
        "outline_color": "&H00000000&",
        "shadow_color": "&H80000000&",
        "outline_size": 8,
        "sticker_bg": "&H30101010&",
        "sticker_accent": "&H0000FFFF&",
        "default_badge": "⚡ VIRAL SHORT"
    },
    "crimson_thriller": {
        "name": "Crimson Thriller (Crime/Mystery)",
        "highlight_ass": "&H002020FF&",
        "font": "Impact",
        "outline_color": "&H00050528&",
        "shadow_color": "&H801010A0&",
        "outline_size": 7,
        "sticker_bg": "&H30100520&",
        "sticker_accent": "&H002020FF&",
        "default_badge": "🚨 UNMASKED"
    },
    "cyber_cyan": {
        "name": "Cyber Cyan (Tech/AI/Future)",
        "highlight_ass": "&H00FFFF00&",
        "font": "Arial Black",
        "outline_color": "&H00201005&",
        "shadow_color": "&H80804000&",
        "outline_size": 7,
        "sticker_bg": "&H30201505&",
        "sticker_accent": "&H00FFFF00&",
        "default_badge": "🤖 AI BREAKTHROUGH"
    },
    "gold_luxury": {
        "name": "Gold Luxury (Business/Wealth)",
        "highlight_ass": "&H0000D7FF&",
        "font": "Impact",
        "outline_color": "&H00081420&",
        "shadow_color": "&H80002040&",
        "outline_size": 8,
        "sticker_bg": "&H300A1020&",
        "sticker_accent": "&H0000D7FF&",
        "default_badge": "💰 THE 1% SECRET"
    },
    "emerald_growth": {
        "name": "Emerald Growth (Finance/Hustle)",
        "highlight_ass": "&H0033FF33&",
        "font": "Arial Black",
        "outline_color": "&H00052005&",
        "shadow_color": "&H80104010&",
        "outline_size": 7,
        "sticker_bg": "&H30052005&",
        "sticker_accent": "&H0033FF33&",
        "default_badge": "💵 WEALTH HACK"
    },
    "sunset_orange": {
        "name": "Sunset Fire (Drama/Action)",
        "highlight_ass": "&H000080FF&",
        "font": "Impact",
        "outline_color": "&H00051530&",
        "shadow_color": "&H80003080&",
        "outline_size": 8,
        "sticker_bg": "&H300A1025&",
        "sticker_accent": "&H000080FF&",
        "default_badge": "🔥 MUST WATCH"
    },
    "hot_pink": {
        "name": "Neon Shock (Drama/Viral)",
        "highlight_ass": "&H00FF00FF&",
        "font": "Impact",
        "outline_color": "&H002A0520&",
        "shadow_color": "&H80600060&",
        "outline_size": 8,
        "sticker_bg": "&H30200515&",
        "sticker_accent": "&H00FF00FF&",
        "default_badge": "🤯 NO WAY"
    },
    "alex_hormozi": {
        "name": "Alex Hormozi (Bold Green Box / High Retention)",
        "highlight_ass": "&H0000FF00&",
        "font": "Impact",
        "outline_color": "&H00000000&",
        "shadow_color": "&H80000000&",
        "outline_size": 9,
        "sticker_bg": "&H30002000&",
        "sticker_accent": "&H0000FF00&",
        "default_badge": "📈 100M SECRETS"
    },
    "tiktok_bounce": {
        "name": "Dynamic Pop (High-Speed White & Yellow Punch)",
        "highlight_ass": "&H0000FFFF&",
        "font": "Arial Black",
        "outline_color": "&H00000000&",
        "shadow_color": "&H80202020&",
        "outline_size": 8,
        "sticker_bg": "&H30202020&",
        "sticker_accent": "&H0000FFFF&",
        "default_badge": "👀 WAIT FOR IT"
    },
    "cinematic_minimal": {
        "name": "Cinematic Minimal (Clean Podcast/Docu)",
        "highlight_ass": "&H00FFFFFF&",
        "font": "Arial",
        "outline_color": "&H00101010&",
        "shadow_color": "&H90000000&",
        "outline_size": 4,
        "sticker_bg": "&H40101010&",
        "sticker_accent": "&H00E0E0E0&",
        "default_badge": "🎙️ UNFILTERED"
    }
}

# ─── YouTube Demonetization & Profanity Censor ─────────────────────────────
# Automatically masks vulgarity & advertiser-unfriendly trigger words with asterisks
# so videos never get demonetized or yellow-flagged by YouTube's AdSense systems.
DEMONETIZED_WORDS_CENSOR = {
    # Heavy Profanity & Vulgarities
    "FUCK": "F*CK", "FUCKING": "F***ING", "FUCKER": "F***ER", "FUCKED": "F***ED", "FUCKS": "F*CKS",
    "MOTHERFUCKER": "M****RF***ER", "MOTHERFUCKING": "M****RF***ING",
    "SHIT": "SH*T", "SHITS": "SH*TS", "SHITTY": "SH*TTY", "BULLSHIT": "BULLSH*T",
    "BITCH": "B*TCH", "BITCHES": "B*TCHES",
    "ASSHOLE": "A**HOLE", "ASSHOLES": "A**HOLES", "ASS": "A**",
    "BASTARD": "B*STARD", "BASTARDS": "B*STARDS",
    "DICK": "D*CK", "DICKS": "D*CKS", "COCK": "C*CK", "COCKS": "C*CKS",
    "PUSSY": "P***Y", "PUSSIES": "P***IES", "CUNT": "C*NT", "CUNTS": "C*NTS",
    "DAMN": "D*MN", "DAMNED": "D*MNED",
    "SLUT": "SL*T", "SLUTS": "SL*TS", "WHORE": "WH*RE", "WHORES": "WH*RES",
    "NIGGER": "N****R", "NIGGA": "N***A", "NIGGERS": "N****RS", "NIGGAS": "N***AS",
    "FAGGOT": "F****T", "FAGGOTS": "F****TS", "FAG": "F*G", "RETARD": "R****D", "RETARDED": "R*****ED",
    
    # YouTube Demonetization Sensitivities (Violence / Crime / Explicit)
    "SUICIDE": "S***IDE", "SUICIDAL": "S***IDAL",
    "KILL": "K*LL", "KILLED": "K*LLED", "KILLING": "K*LLING", "KILLER": "K*LLER", "KILLERS": "K*LLERS", "KILLS": "K*LLS",
    "MURDER": "M*RDER", "MURDERED": "M*RDERED", "MURDERING": "M*RDERING", "MURDERER": "M*RDERER", "MURDERERS": "M*RDERERS", "MURDERS": "M*RDERS",
    "RAPE": "R*PE", "RAPED": "R*PED", "RAPING": "R*PING", "RAPIST": "R*PIST", "RAPISTS": "R*PISTS",
    "COCAINE": "C*CAINE", "HEROIN": "H*ROIN", "METH": "M*TH", "FENTANYL": "F*NTANYL",
    "PEDOPHILE": "P*DOPHILE", "PEDO": "P*DO", "PEDOPHILES": "P*DOPHILES",
    "PORN": "P*RN", "PORNO": "P*RNO", "PORNOGRAPHY": "P*RNOGRAPHY", "SEX": "S*X", "NAKED": "N*KED",
    "PENIS": "P*NIS", "VAGINA": "V*GINA", "BOOBS": "B**BS"
}

def censor_demonetized_text(text: str) -> str:
    """
    Censors profanity and YouTube demonetization trigger words with asterisks.
    Preserves casing so captions remain visually clean, natural, and advertiser-friendly.
    """
    if not text:
        return ""

    def _replace_word(match):
        raw = match.group(0)
        upper_w = raw.upper()
        if upper_w in DEMONETIZED_WORDS_CENSOR:
            censored = DEMONETIZED_WORDS_CENSOR[upper_w]
            if raw.isupper():
                return censored
            elif raw.islower():
                return censored.lower()
            elif raw.istitle():
                return censored.capitalize()
            return censored
        return raw

    return re.sub(r'\b[A-Za-z]+\b', _replace_word, text)


EMOJI_KEYWORDS = {
    # Money / Wealth / Cash
    "MONEY": "💰", "DOLLAR": "💵", "DOLLARS": "💵", "CASH": "💸", "RICH": "🤑",
    "MILLION": "💰", "MILLIONS": "💰", "BILLION": "💎", "BILLIONS": "💎", "PROFIT": "📈",
    "PAID": "💵", "PAY": "💵", "PRICE": "🏷️", "EXPENSIVE": "💎", "BUSINESS": "💼",
    # Death / Crime / Mystery / Danger
    "DEAD": "💀", "DIE": "💀", "DIED": "💀", "KILL": "💀", "KILLED": "💀", "MURDER": "💀",
    "SHOCK": "🤯", "SHOCKED": "🤯", "INSANE": "🤯", "CRAZY": "😱", "WHAT": "👀",
    "TRUTH": "🤫", "LIE": "🤥", "LIAR": "🤥", "LIED": "🤥", "EXPOSED": "🚨",
    "SECRET": "🤫", "SECRETS": "🤫", "HIDDEN": "🤫", "WHISPER": "🤫",
    "DANGER": "⚠️", "WARNING": "⚠️", "MISTAKE": "❌", "WRONG": "❌", "FAIL": "📉",
    "POLICE": "🚨", "ARREST": "🚨", "ARRESTED": "🚨", "JAIL": "⛓️", "PRISON": "⛓️",
    "CRIME": "🚨", "GUILTY": "⚖️", "COURT": "⚖️", "JUDGE": "⚖️", "LAWYER": "⚖️",
    # Emotions / Energy / Actions
    "FIRE": "🔥", "HOT": "🔥", "BURNING": "🔥", "LIT": "🔥",
    "RUN": "🏃‍♂️", "RUNNING": "🏃‍♂️", "ESCAPE": "🏃‍♂️", "FLEED": "🏃‍♂️",
    "FROZEN": "🥶", "FREEZE": "🥶", "COLD": "🥶", "ICE": "🧊",
    "STOP": "🛑", "NEVER": "🚫", "NO": "❌", "YES": "✅",
    "LOOK": "👀", "WATCH": "👀", "SEE": "👀", "CAUGHT": "📸", "TAPE": "📹",
    "WIN": "🏆", "WON": "🏆", "VICTORY": "🏆", "CHAMPION": "👑", "KING": "👑",
    "WAIT": "⏳", "TIME": "⏰", "HOURS": "⏳", "MINUTES": "⏱️", "YEARS": "📅",
    "FAST": "⚡", "SPEED": "⚡", "EXPLODED": "💥", "BOOM": "💥", "BOMB": "💣",
    "GHOST": "👻", "SCARY": "😱", "FEAR": "😨", "TRAP": "🪤", "HACK": "🧠",
}

def format_ass_time(seconds: float) -> str:
    """Format seconds into H:MM:SS.cc for ASS subtitles."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    centis = int((secs - int(secs)) * 100)
    return f"{hrs:d}:{mins:02d}:{int(secs):02d}.{centis:02d}"

def generate_dynamic_subtitles(
    transcript: List[Dict], 
    clip_start: float, 
    clip_end: float, 
    output_ass_path: str,
    api_key: Optional[str] = None,
    psychological_hook: Optional[str] = None,
    part_info: Optional[Dict] = None,
    subscriber_cta: Optional[str] = None,
    caption_art_direction: Optional[str] = None,
    sticker_badge: Optional[str] = None,
    show_top_hook: bool = False
) -> Tuple[str, Dict]:
    """
    Generate viral, punchy, fast-paced ASS subtitles verified by the Caption Review Bot.
    
    KEY VIRAL DESIGN RULES:
    1. REEL-MATCHING ART DIRECTION: Palette, fonts, and accents dynamically matched to the reel's mood.
    2. OPTIONAL CLEAN TOP HEADER: Only shown if show_top_hook is True; default is clean video without clutter.
    3. LOWER-THIRD SUBTITLE SAFE ZONE: Perfectly positioned at MarginV=640 to prevent collisions with UI.
    4. SEQUENCED OUTRO CTA: Sub-CTA appears cleanly in the final 3.0s window.
    """
    os.makedirs(os.path.dirname(output_ass_path), exist_ok=True)

    # Resolve Art Direction Theme
    theme_key = caption_art_direction if caption_art_direction in CAPTION_ART_DIRECTIONS else "yellow_electric"
    art = CAPTION_ART_DIRECTIONS[theme_key]
    hl_color = art["highlight_ass"]
    font_name = art["font"]
    sticker_accent = art["sticker_accent"]
    outline_color = art.get("outline_color", "&H00000000&")
    shadow_color = art.get("shadow_color", "&H80000000&")
    outline_size = min(art.get("outline_size", 6), 6)

    # Build Dynamic Header matching Art Direction style
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: ViralStyle,{font_name},62,&H00FFFFFF,{hl_color},{outline_color},{shadow_color},-1,0,0,0,100,100,1.8,0,1,{outline_size},3,2,65,65,640,1
Style: HighlightStyle,{font_name},66,{hl_color},&H00FFFFFF,{outline_color},{shadow_color},-1,0,0,0,104,104,2.0,0,1,{outline_size + 1},4,2,65,65,640,1
Style: TopPsychHook,Arial,36,&H00FFFFFF,{sticker_accent},&H00000000,&H60000000,-1,0,0,0,100,100,1.2,0,1,3,2,8,60,60,180,1
Style: SubCTA,Arial Black,54,&H00FFFFFF,{hl_color},{outline_color},&H00121212,-1,0,0,0,102,102,1.5,0,3,14,0,2,60,60,420,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    # 1. Run AI Caption Review Bot for human metrics verification and de-overlapping
    review_data = review_and_optimize_captions(transcript, clip_start, clip_end, api_key=api_key)
    optimized = review_data.get("optimized_subtitles", [])

    events = []
    prev_end = 0.0

    for item in optimized:
        s_time = max(prev_end, float(item.get("start", 0.0)))
        e_time = float(item.get("end", s_time + 0.8))

        if e_time <= s_time:
            e_time = s_time + 0.35

        prev_end = e_time

        # Automatically censor demonetized / profanity words with asterisks
        raw_text = item.get("text", "").upper().strip()
        text = censor_demonetized_text(raw_text)

        raw_hl = item.get("highlight_word", "").upper().strip()
        hl_word = censor_demonetized_text(raw_hl)

        words = text.split()
        if not words:
            continue

        # Smart Contextual Emoji Injection on punch words
        emoji_attached = False
        new_words = []
        for w in words:
            clean_w = re.sub(r'[^A-Z]', '', w)
            if not emoji_attached and clean_w in EMOJI_KEYWORDS:
                new_words.append(f"{w} {EMOJI_KEYWORDS[clean_w]}")
                emoji_attached = True
            else:
                new_words.append(w)
        words = new_words

        # Apply Kinetic Highlight Coloring with Elastic Scale Bounce
        if hl_word and any(hl_word in w for w in words):
            matched_idx = next(i for i, w in enumerate(words) if hl_word in w)
            words[matched_idx] = f"{{\\t(0,90,\\fscx120\\fscy120)\\t(90,190,\\fscx100\\fscy100)\\c{hl_color}}}{words[matched_idx]}{{\\r\\c&H00FFFFFF&}}"
            formatted_text = " ".join(words)
        else:
            # Clean modern white caption style without over-saturating neutral words
            formatted_text = " ".join(words)

        t_start = format_ass_time(s_time)
        t_end = format_ass_time(e_time)
        events.append(f"Dialogue: 0,{t_start},{t_end},ViralStyle,,0,0,0,,{formatted_text}")

    # 2. Add Top Header Sticker (Only if explicitly enabled via show_top_hook)
    clip_dur = max(1.0, clip_end - clip_start)

    hook_duration = 0.0
    badge_label = ""
    if show_top_hook:
        # Resolve sticker badge text
        if part_info:
            part_num = part_info.get("part_number", 1)
            total_parts = part_info.get("total_parts", 3)
            badge_label = f"PART {part_num}/{total_parts}"
        elif sticker_badge and sticker_badge.strip():
            badge_label = sticker_badge.strip().upper()
        else:
            badge_label = ""

        clean_hook = ""
        if psychological_hook and psychological_hook.strip():
            raw_hook = psychological_hook.strip().upper().replace('"', '').replace("'", "")
            clean_hook = censor_demonetized_text(raw_hook)
            words = clean_hook.split()
            if len(words) > 6:
                mid = len(words) // 2
                clean_hook = " ".join(words[:mid]) + "\\N" + " ".join(words[mid:])
            else:
                clean_hook = " ".join(words)

        hook_duration = min(3.8, max(2.0, clip_dur * 0.18))
        t_hook_end = format_ass_time(hook_duration)

        if badge_label and clean_hook:
            hook_banner_text = f"{{\\c{sticker_accent}}}{badge_label}{{\\c&H00FFFFFF&}} • {clean_hook}"
        elif clean_hook:
            hook_banner_text = f"{{\\c&H00FFFFFF&}}{clean_hook}"
        elif badge_label:
            hook_banner_text = f"{{\\c{sticker_accent}}}{badge_label}"
        else:
            hook_banner_text = ""

        if hook_banner_text:
            events.insert(0, f"Dialogue: 1,0:00:00.00,{t_hook_end},TopPsychHook,,0,0,0,,{hook_banner_text}")

    # 3. Add Subscriber Conversion CTA Banner (Sequential Timing: Final 3.0 seconds ONLY)
    cta_duration = min(3.0, clip_dur * 0.25)
    cta_start = max(hook_duration + 0.5, clip_dur - cta_duration)
    t_cta_start = format_ass_time(cta_start)
    t_cta_end = format_ass_time(clip_dur)

    cta_text = subscriber_cta
    if not cta_text or not cta_text.strip():
        if part_info:
            p_num = int(part_info.get("part_number", 1))
            t_num = int(part_info.get("total_parts", 3))
            if p_num < t_num:
                cta_text = f"👉 TO BE CONTINUED IN PART {p_num + 1} • SUBSCRIBE 🔔"
            else:
                cta_text = "🔥 THE END • SUBSCRIBE FOR NEXT SAGA 🚀"
        else:
            cta_text = "SUBSCRIBE FOR DAILY SECRETS 🚀"

    cta_clean = censor_demonetized_text(cta_text.strip().upper())
    if "🔔" not in cta_clean and "SUBSCRIBE" in cta_clean:
        cta_clean = f"🔔 {cta_clean}"
    if "SUBSCRIBE" in cta_clean:
        formatted_cta = cta_clean.replace("SUBSCRIBE", f"{{\\c{hl_color}}}SUBSCRIBE{{\\c&H00FFFFFF&}}")
    else:
        formatted_cta = f"{{\\c{hl_color}}}{cta_clean}{{\\c&H00FFFFFF&}}"

    # Only append CTA if clip is long enough to have distinct outro
    if cta_start < clip_dur:
        events.append(f"Dialogue: 2,{t_cta_start},{t_cta_end},SubCTA,,0,0,0,,{formatted_cta}")

    content = ass_header + "\n".join(events) + "\n"
    with open(output_ass_path, "w", encoding="utf-8") as f:
        f.write(content)

    clean_badge = badge_label.encode('ascii', 'ignore').decode('ascii')
    print(f"[Subtitles] Generated {len(events)} events (Theme: '{art['name']}', Badge: '{clean_badge}') -> {output_ass_path}")
    return output_ass_path, review_data

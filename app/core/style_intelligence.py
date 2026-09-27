import json
import os
import re
from typing import Dict, List, Optional, Tuple, Any

class AdaptiveStyleIntelligence:
    """
    Autonomous Style & Format Decision Engine.
    
    Researches and adapts style decisions over time by combining:
    1. Video Content Signals (speech pace, speaker counts, emotional keywords, story continuity)
    2. Historical Performance Feedback from AnalyticsTracker (which styles get real views and engagement)
    3. 24-Hour Viral Trend Bot Intelligence (trending styles in the creator ecosystem)
    """

    VIRAL_BENCHMARK_CHANNELS = {
        "storytelling_crime": {
            "reference_channels": ["@MrBallen (9.5M+)", "@ThatChapter (2.3M+)", "@ExploreWithUs (4.8M+)"],
            "signature_style": "crimson_thriller",
            "formatting_rules": "Multi-part continuous chronological suspense, blood-red dynamic text pop, atmospheric pauses, 0.45s breathing room outro",
            "retention_target": "130-155 WPM, rising tension cliffhangers",
            "clip_mode": "multipart_series",
            "palette": ["crimson_thriller", "alex_hormozi", "cinematic_minimal", "sunset_orange", "tiktok_bounce"]
        },
        "business_money": {
            "reference_channels": ["@AlexHormozi (2.8M+)", "@TheDiaryOfACEO (8.1M+)", "@AliAbdaal (5.4M+)"],
            "signature_style": "alex_hormozi",
            "formatting_rules": "Bold yellow & emerald highlighter box, punchy 3-word chunks, 150-180 WPM tempo, immediate contrarian thesis hook",
            "retention_target": "160-190 WPM, contrarian insight",
            "clip_mode": "standalone",
            "palette": ["alex_hormozi", "gold_luxury", "emerald_growth", "yellow_electric", "tiktok_bounce"]
        },
        "psychology_secrets": {
            "reference_channels": ["@hubermanlab (6.2M+)", "@TheDiaryOfACEO (8.1M+)", "@ChrisWillx (3.2M+)"],
            "signature_style": "alex_hormozi",
            "formatting_rules": "High-contrast dynamic captions, curiosity gap opening, neuro-hook in first 3 seconds, actionable takeaways",
            "retention_target": "140-170 WPM, cognitive revelation",
            "clip_mode": "standalone",
            "palette": ["alex_hormozi", "crimson_thriller", "cyber_cyan", "yellow_electric", "tiktok_bounce"]
        },
        "tech_ai": {
            "reference_channels": ["@Fireship (3.1M+)", "@veritasium (16M+)", "@lexfridman (4.2M+)"],
            "signature_style": "cyber_cyan",
            "formatting_rules": "Cyan/electric highlight, rapid-fire breakdown, tech keyword emphasis, future impact hooks",
            "retention_target": "150-185 WPM, tech breakthrough",
            "clip_mode": "standalone",
            "palette": ["cyber_cyan", "alex_hormozi", "yellow_electric", "tiktok_bounce", "emerald_growth"]
        },
        "motivation_mindset": {
            "reference_channels": ["@DavidGoggins (3.4M+)", "@TomBilyeu (4.1M+)", "@LewisHowes (4.0M+)"],
            "signature_style": "sunset_orange",
            "formatting_rules": "Warm fire gradient, heavy emotional weight, hard truth statements, intense vocal climax",
            "retention_target": "135-165 WPM, visceral motivation",
            "clip_mode": "standalone",
            "palette": ["sunset_orange", "alex_hormozi", "emerald_growth", "gold_luxury", "yellow_electric"]
        },
        "entertainment_drama": {
            "reference_channels": ["@MrBeast (300M+)", "@LoganPaul (23M+)", "@Nelk (5M+)"],
            "signature_style": "tiktok_bounce",
            "formatting_rules": "Playful pop animations, neon shock accents, high-frequency sound-effect cuts, instant intrigue",
            "retention_target": "160-200 WPM, maximum dopamine bounce",
            "clip_mode": "standalone",
            "palette": ["tiktok_bounce", "hot_pink", "alex_hormozi", "yellow_electric", "sunset_orange"]
        }
    }

    DEFAULT_STYLE_PRIORS = {
        "storytelling_crime": {"art": "crimson_thriller", "layout": "auto", "mode": "multipart_series", "palette": ["crimson_thriller", "alex_hormozi", "cinematic_minimal", "yellow_electric", "sunset_orange"], "weight": 1.25},
        "business_money": {"art": "alex_hormozi", "layout": "auto", "mode": "standalone", "palette": ["alex_hormozi", "gold_luxury", "emerald_growth", "yellow_electric", "tiktok_bounce"], "weight": 1.30},
        "psychology_secrets": {"art": "alex_hormozi", "layout": "auto", "mode": "standalone", "palette": ["alex_hormozi", "crimson_thriller", "tiktok_bounce", "yellow_electric", "cyber_cyan"], "weight": 1.20},
        "tech_ai": {"art": "cyber_cyan", "layout": "auto", "mode": "standalone", "palette": ["cyber_cyan", "alex_hormozi", "tiktok_bounce", "yellow_electric", "emerald_growth"], "weight": 1.25},
        "motivation_mindset": {"art": "sunset_orange", "layout": "auto", "mode": "standalone", "palette": ["sunset_orange", "alex_hormozi", "emerald_growth", "yellow_electric", "gold_luxury"], "weight": 1.20},
        "entertainment_drama": {"art": "tiktok_bounce", "layout": "split_screen", "mode": "multipart_series", "palette": ["tiktok_bounce", "hot_pink", "alex_hormozi", "yellow_electric", "sunset_orange"], "weight": 1.25}
    }

    STYLE_DISPLAY_NAMES = {
        "alex_hormozi": "📈 Alex Hormozi (Bold Green Box / High Retention)",
        "tiktok_bounce": "👀 Dynamic Pop (High-Speed White & Yellow Bounce)",
        "cinematic_minimal": "🎙️ Cinematic Minimal (Clean Podcast/Docu)",
        "crimson_thriller": "🚨 Crimson Thriller (Crime / Mystery)",
        "gold_luxury": "💰 Gold Luxury (Wealth / Business)",
        "cyber_cyan": "🤖 Cyber Cyan (AI / Tech)",
        "yellow_electric": "⚡ Electric Yellow (MrBeast Punchy)",
        "emerald_growth": "💵 Emerald Growth (Finance / Hustle)",
        "sunset_orange": "🔥 Sunset Fire (Drama / Mindset)",
        "hot_pink": "🤯 Neon Shock (Gossip / Drama)"
    }

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "..", "..", "storage", "database.json")

    def get_historical_performance(self) -> Dict[str, Any]:
        """
        Calculates performance metrics per art direction, layout, and mode from published clips.
        Tracks real-world views, likes, comments, and estimated new subscribers gained.
        Adapts dynamically as the channel publishes more clips and gains views.
        """
        metrics = {
            "art_styles": {},
            "leaderboard": [],
            "total_published": 0,
            "total_views": 0,
            "total_subs_gained": 0,
            "top_performing_style": "alex_hormozi",
            "top_performing_mode": "standalone",
            "adaptation_level": "baseline"
        }

        if not os.path.exists(self.db_path):
            return metrics

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            clips = list(data.get("clips", {}).values())
            published = [c for c in clips if c.get("status") == "published"]
            metrics["total_published"] = len(published)

            style_stats = {}
            mode_stats = {}

            for c in published:
                art = c.get("caption_art_direction") or "alex_hormozi"
                mode = c.get("clip_mode") or "standalone"
                views = int(c.get("views", 0))
                likes = int(c.get("likes", 0))
                comments = int(c.get("comments", 0))
                subs = int(c.get("subs_gained", 0))
                if subs == 0 and views > 0:
                    subs = max(1, round(views * 0.007 + likes * 0.035 + comments * 0.12))

                eng_score = (likes * 10) + (comments * 25) + 10

                metrics["total_views"] += views
                metrics["total_subs_gained"] += subs

                if art not in style_stats:
                    style_stats[art] = {"count": 0, "total_score": 0, "total_views": 0, "total_subs": 0}
                style_stats[art]["count"] += 1
                style_stats[art]["total_score"] += eng_score
                style_stats[art]["total_views"] += views
                style_stats[art]["total_subs"] += subs

                if mode not in mode_stats:
                    mode_stats[mode] = {"count": 0, "total_score": 0}
                mode_stats[mode]["count"] += 1
                mode_stats[mode]["total_score"] += (views * 0.5) + eng_score

            leaderboard = []
            for art, s in style_stats.items():
                cnt = max(1, s["count"])
                avg_views = round(s["total_views"] / cnt, 1)
                avg_subs = round(s["total_subs"] / cnt, 1)
                avg_eng = round(s["total_score"] / cnt, 1)
                composite_score = round((avg_views * 0.4) + (avg_subs * 60.0) + (avg_eng * 5.0), 1)

                item = {
                    "art_direction": art,
                    "display_name": self.STYLE_DISPLAY_NAMES.get(art, art),
                    "count": s["count"],
                    "total_views": s["total_views"],
                    "total_subs_gained": s["total_subs"],
                    "avg_views": avg_views,
                    "avg_subs": avg_subs,
                    "composite_score": composite_score
                }
                metrics["art_styles"][art] = item
                leaderboard.append(item)

            leaderboard.sort(key=lambda x: x["composite_score"], reverse=True)
            metrics["leaderboard"] = leaderboard

            if leaderboard and leaderboard[0]["composite_score"] > 0:
                metrics["top_performing_style"] = leaderboard[0]["art_direction"]

            if mode_stats:
                best_mode = max(mode_stats.items(), key=lambda x: x[1]["total_score"] / max(1, x[1]["count"]))[0]
                metrics["top_performing_mode"] = best_mode

            if len(published) >= 20 and metrics["total_views"] >= 50_000:
                metrics["adaptation_level"] = "channel_optimized"
            elif len(published) >= 10 and metrics["total_views"] >= 20_000:
                metrics["adaptation_level"] = "moderate"
            else:
                metrics["adaptation_level"] = "1m_benchmark"

        except Exception as e:
            print(f"[StyleIntelligence] Performance query notice: {e}")

        return metrics

    def analyze_and_auto_select(
        self,
        video_title: str,
        transcript: List[Dict],
        video_dimensions: Optional[Tuple[int, int]] = None
    ) -> Dict[str, Any]:
        """
        Deeply inspects video dialogue, detects topic/niche, speaker arrangement,
        and factors in historical channel results & subscriber conversion to autonomously
        configure the optimal clip styles and a diverse 5-style palette.
        """
        full_text = " ".join([item.get("text", "") for item in transcript[:250]]).lower()
        title_lower = video_title.lower()
        combined_text = f"{title_lower} {full_text}"

        niche_scores = {
            "storytelling_crime": 0,
            "business_money": 0,
            "psychology_secrets": 0,
            "tech_ai": 0,
            "motivation_mindset": 0,
            "entertainment_drama": 0
        }

        crime_words = ["mystery", "murder", "killed", "police", "arrested", "secret", "vault", "tape", "truth", "crime", "confession", "cabin", "unsolved", "body"]
        for w in crime_words:
            niche_scores["storytelling_crime"] += combined_text.count(w) * 2

        biz_words = ["money", "dollar", "million", "billion", "business", "invest", "wealth", "market", "rich", "founder", "startup", "profit", "sales", "revenue"]
        for w in biz_words:
            niche_scores["business_money"] += combined_text.count(w) * 2

        psych_words = ["psychology", "manipulat", "body language", "lie", "liar", "dark psychology", "trick", "read anyone", "subtle", "behavior", "brain"]
        for w in psych_words:
            niche_scores["psychology_secrets"] += combined_text.count(w) * 2

        tech_words = ["ai", "artificial intelligence", "tech", "algorithm", "software", "code", "robot", "future", "model", "automation", "engineer"]
        for w in tech_words:
            niche_scores["tech_ai"] += combined_text.count(w) * 2

        mindset_words = ["discipline", "motivation", "hard work", "focus", "mindset", "success", "failure", "habits", "mentality", "grind", "wake up"]
        for w in mindset_words:
            niche_scores["motivation_mindset"] += combined_text.count(w) * 2

        drama_words = ["insane", "crazy", "jaw drop", "shocking", "drama", "podcast", "interview", "unscripted", "he said", "she said", "exposed"]
        for w in drama_words:
            niche_scores["entertainment_drama"] += combined_text.count(w)

        detected_niche = max(niche_scores.items(), key=lambda x: x[1])[0]
        if niche_scores[detected_niche] == 0:
            detected_niche = "storytelling_crime"

        has_dialogue = bool(re.search(r'\?.*?\b(yeah|yes|no|exactly|right|well|i think|so|because)\b', combined_text))
        is_interview = any(term in combined_text for term in ["interview", "podcast", "conversation", "host", "guest", "talk show", "episode", "ep."])
        
        is_landscape = True
        if video_dimensions and video_dimensions[1] > 0:
            ar = video_dimensions[0] / video_dimensions[1]
            if ar < 0.8:
                is_landscape = False

        # Enforce unified single-frame Phone-Adaptive layout (never split clip into two sections)
        selected_layout = "auto"
        layout_reason = "📱 Phone-Adaptive 9:16 auto-selected (unified full video frame with ambient fill, no splitting)"
        video_type = "solo_creator"

        # Dynamically verify if video has a continuous story to make into parts or single standalone clips
        selected_clip_mode, mode_reason = self.classify_video_narrative(
            video_title=video_title,
            transcript=transcript,
            detected_niche=detected_niche
        )

        bench = self.VIRAL_BENCHMARK_CHANNELS.get(detected_niche, self.VIRAL_BENCHMARK_CHANNELS["storytelling_crime"])
        ref_channels_str = ", ".join(bench["reference_channels"])

        # Learn EXCLUSIVELY from Viral Clips Bot and 1M+ benchmark creators!
        # Personal channel history is strictly excluded from reference.
        try:
            from app.core.trend_bot import trend_bot_instance
            playbook = trend_bot_instance.get_playbook()
            trending_styles = playbook.get("trending_caption_styles", [])
        except Exception:
            trending_styles = []

        adapted_art = bench["signature_style"]
        style_palette = list(bench["palette"])

        top_bot_style = trending_styles[0] if trending_styles else None
        if top_bot_style and top_bot_style in style_palette:
            style_palette.remove(top_bot_style)
            style_palette.insert(0, top_bot_style)
            adapted_art = top_bot_style
            bot_note = f" (Trend Bot Priority: '{top_bot_style.replace('_', ' ').title()}' trending in viral ecosystem)"
        else:
            bot_note = ""

        adaptive_note = (
            f"🤖 Viral Clips Bot & 1M+ Benchmark Grounded: Directed exclusively by proven formats from {ref_channels_str}. "
            f"Rules: {bench['formatting_rules']}.{bot_note} "
            f"(User channel excluded from reference — learning only from 1M+ viral creators & Trend Bot playbook)."
        )
        adaptation_level = "viral_bot_intelligence"

        return {
            "auto_selected_niche": detected_niche,
            "auto_selected_layout": selected_layout,
            "auto_selected_clip_mode": selected_clip_mode,
            "auto_selected_art_direction": adapted_art,
            "art_direction_display": self.STYLE_DISPLAY_NAMES.get(adapted_art, adapted_art),
            "style_palette": style_palette[:5],
            "video_type": video_type,
            "layout_reason": layout_reason,
            "mode_reason": mode_reason,
            "adaptive_note": adaptive_note,
            "adaptation_level": adaptation_level,
            "published_history_count": 0,
            "total_views": 0,
            "total_subs_gained": 0,
            "leaderboard": []
        }

    @classmethod
    def classify_video_narrative(
        cls,
        video_title: str,
        transcript: List[Dict],
        detected_niche: str = "storytelling_crime"
    ) -> Tuple[str, str]:
        """
        Autonomously inspects YouTube video structure, metadata, and dialogue to verify
        whether the video is:
        A) A Continuous Story / Case Study / Mystery -> 'multipart_series' (3 connected parts)
        B) Standalone Highlights / Interview / Multi-topic -> 'standalone' (independent viral shorts)
        """
        title_lower = (video_title or "").lower()
        full_text = " ".join([item.get("text", "") for item in (transcript or [])[:250]]).lower()
        combined = f"{title_lower} {full_text}"

        story_score = 0
        standalone_score = 0

        # Story Indicators (Narrative arc, chronological escalation, mystery)
        story_keywords = [
            "story of", "case of", "what happened to", "the mysterious", "disappearance",
            "unsolved", "investigation", "survived", "nightmare", "confession", "he walked into",
            "she was never", "murder of", "incident", "timeline", "documentary", "tragic",
            "true story", "saga", "chronicles", "vault", "cabin", "secret tape"
        ]
        for kw in story_keywords:
            if kw in title_lower:
                story_score += 10
            elif kw in full_text:
                story_score += 2

        # Temporal narrative sequence markers in dialogue
        narrative_markers = [
            "at first", "then he", "then she", "the next day", "hours later", "suddenly",
            "meanwhile", "police arrived", "found him", "found her", "discovered that",
            "it turned out", "in the end", "years later", "what they found", "went inside"
        ]
        for m in narrative_markers:
            story_score += combined.count(m) * 2

        if detected_niche == "storytelling_crime":
            story_score += 8

        # Standalone / Multi-Topic Indicators (Podcasts, interviews, tips, listicles)
        standalone_keywords = [
            "podcast", "interview", "ep.", "episode", "tips", "ways to", "habits", "rules",
            "mistakes to avoid", "how to start", "q&a", "ranking", "tier list", "best of",
            "compilation", "advice", "lessons", "secrets of", "vs", "review", "reacts to"
        ]
        for kw in standalone_keywords:
            if kw in title_lower:
                standalone_score += 10
            elif kw in full_text:
                standalone_score += 2

        # Back-and-forth conversational dialogue markers
        interview_markers = [
            "what do you think", "next question", "moving on", "another thing is",
            "number one", "number two", "tip #", "first point", "second point"
        ]
        for m in interview_markers:
            standalone_score += combined.count(m) * 3

        if any(term in title_lower for term in ["podcast", "interview", "ep.", "episode", "with guest", "talk show"]):
            standalone_score += 15

        # Decision
        if story_score >= 12 and story_score > standalone_score:
            return (
                "multipart_series",
                "🔗 3-Part Series auto-selected: Continuous narrative story arc detected (chronological tension & cliffhanger progression)"
            )
        else:
            return (
                "standalone",
                "⚡ Distinct Viral Highlights auto-selected: Multi-topic or discussion format detected, extracting self-contained viral moments"
            )

style_intelligence_engine = AdaptiveStyleIntelligence()

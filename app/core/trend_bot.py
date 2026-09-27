"""
trend_bot.py — 24-Hour Viral Trend Intelligence Bot.
Captures trending and famous viral YouTube Shorts every 24 hours, deconstructs
what makes them go viral (3-second hook structure, psychological curiosity triggers,
top caption pill stickers, pacing, payoff), and compiles an active Viral Playbook
that is automatically injected into every clip generation.
"""
import os
import json
import time
import threading
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from google import genai
from google.genai import types

PLAYBOOK_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage", "viral_playbook.json")

DEFAULT_PLAYBOOK = {
    "last_scanned": None,
    "total_famous_clips_analyzed": 0,
    "top_hook_archetypes": [
        "The Negative Confession: 'He didn't mean to say this out loud...'",
        "The High-Stakes Curiosity Gap: 'Nobody was supposed to see this tape...'",
        "The Counter-Intuitive Truth: 'Everything you have been told about X is a lie.'",
        "The Social Tension Freeze: 'The room went completely silent when he said this.'",
        "The Direct Warning: 'Stop doing this before it ruins your career.'"
    ],
    "psychological_triggers": [
        "He had no idea they were recording...",
        "Watch his face the exact second he realizes...",
        "Did he really just admit this on camera?",
        "Wait... he was not supposed to say that.",
        "The moment everyone froze in disbelief..."
    ],
    "top_sticker_phrases": [
        "[WAIT FOR IT]",
        "[EXPOSED]",
        "[DON'T MISS THIS]",
        "[SECRET REVEALED]",
        "[WATCH TILL END]"
    ],
    "trending_caption_styles": [
        "Alex Hormozi Green: Bold Montserrat/Impact with neon green highlight box for maximum watch-time.",
        "Dynamic Pop: High-speed white/yellow bounce captions with contextual emoji pop.",
        "Crimson Thriller: Deep crimson emphasis for crime, mystery, and shocking disclosures.",
        "Gold Luxury: Metallic gold highlights for business, money, and billionaire secrets.",
        "Cyber Cyan: Luminous cyan text for AI, science, and technological breakthroughs."
    ],
    "winning_hook_methods": [
        "The Negative Confession: 'He didn't mean to say this out loud...'",
        "The Split-Second Pattern Interrupt: Start mid-sentence on high vocal pitch.",
        "The High-Stakes Curiosity Gap: 'Nobody was supposed to see this tape...'",
        "The Subconscious Identity Question: 'If you do this daily, you are in the 1%...'",
        "The Shock Freeze: 'The room went completely silent when he said this.'"
    ],
    "retention_tactics": [
        "Cut conversational pleasantries; start at emotional peak.",
        "Pattern interrupt every 2-3 seconds with bold keywords.",
        "Deliver a complete punchline or revelation before 40s.",
        "End on a statement that seamlessly loops into the hook."
    ],
    "title_formulas": [
        "The 1 Truth About [Topic] Nobody Admits #shorts",
        "He Said WHAT? (Watch Till End) #shorts",
        "Why 99% Of People Fail At [Topic] #shorts"
    ],
    "prompt_injection_text": """
24-HOUR VIRAL TREND INTELLIGENCE (LEARNED FROM RECENT MULTI-MILLION VIEW SHORTS):
- HOOK REQUIREMENT: Open with pattern interrupts (disbelief, exposed secret, high stakes).
- CAPTION ART DIRECTION: Diversify across winning styles (Alex Hormozi green box, Crimson Thriller, Gold Luxury, Cyber Cyan). NEVER default all clips to a single style.
- PSYCHOLOGICAL HOOK: Never summarize facts. Use psychological tension (e.g. 'He didn't mean to say this out loud...').
- CAPTION STICKER: Use punchy 2-4 word curiosity triggers in upper safe zone.
- DURATION & PACING: Target 30-42s with energy rising to a conclusive payoff.
"""
}

class ViralTrendBot:
    def __init__(self, playbook_path: str = PLAYBOOK_FILE):
        self.playbook_path = playbook_path
        self._lock = threading.Lock()
        self._is_running = False
        self._init_playbook()

    def _init_playbook(self):
        os.makedirs(os.path.dirname(self.playbook_path), exist_ok=True)
        if not os.path.exists(self.playbook_path):
            with open(self.playbook_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_PLAYBOOK, f, indent=2, ensure_ascii=False)

    def get_playbook(self) -> Dict:
        try:
            with open(self.playbook_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return DEFAULT_PLAYBOOK

    def _save_playbook(self, data: Dict):
        with self._lock:
            with open(self.playbook_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    def fetch_trending_shorts_metadata(self, max_results: int = 15) -> List[Dict]:
        """Fetch real metadata of famous trending YouTube Shorts using yt-dlp."""
        query = 'ytsearch15:#shorts #viral (podcast OR interview OR mindset OR story OR business)'
        cmd = [
            'yt-dlp',
            '--dump-single-json',
            '--flat-playlist',
            '--no-warnings',
            query
        ]
        clips = []
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if res.returncode == 0 and res.stdout:
                data = json.loads(res.stdout)
                entries = data.get("entries", [])
                for e in entries:
                    if not e:
                        continue
                    views = e.get("view_count") or 0
                    title = e.get("title", "")
                    if title:
                        clips.append({
                            "title": title,
                            "uploader": e.get("uploader", "Creator"),
                            "views": views,
                            "duration": e.get("duration", 30),
                            "description": (e.get("description") or "")[:200]
                        })
        except Exception as err:
            print(f"[TrendBot] Error fetching trending shorts metadata: {err}")

        # Fallback curated famous shorts if offline or rate-limited
        if not clips:
            clips = [
                {"title": "He Had No Idea The Mic Was Still On... #shorts", "views": 4200000, "duration": 34},
                {"title": "The $10,000,000 Mistake Nobody Talks About #shorts", "views": 2800000, "duration": 39},
                {"title": "He Actually Said This To Alex Hormozi #shorts", "views": 6100000, "duration": 29},
                {"title": "Never Say This In An Interview (Instantly Rejected) #shorts", "views": 3500000, "duration": 38},
                {"title": "The Brutal Truth About Why You Are Still Broke #shorts", "views": 5100000, "duration": 42}
            ]
        return clips[:max_results]

    def analyze_trends_with_gemini(self, clips: List[Dict], api_key: str) -> Dict:
        """Deconstruct winning viral mechanics using Gemini AI."""
        if not api_key:
            return DEFAULT_PLAYBOOK

        client = genai.Client(api_key=api_key)
        clips_summary = "\n".join([
            f"- Title: \"{c['title']}\" | Views: {c.get('views', '1M+')} | Duration: {c.get('duration', 30)}s"
            for c in clips
        ])

        prompt = f"""
You are the world's top YouTube Shorts Algorithm & Retention Analyst.
Analyze these {len(clips)} top-performing famous viral shorts:

{clips_summary}

Deconstruct what makes these specific clips perform at the 1M to 10M+ view level for US/UK audiences.
Return a valid JSON object matching this schema:
{{
  "top_hook_archetypes": [
    "5 specific hook structure formulas that create irresistible open loops in 0-3 seconds"
  ],
  "psychological_triggers": [
    "5 psychological curiosity phrases for top sticker banners (e.g. 'He didn't mean to say this out loud...')"
  ],
  "top_sticker_phrases": [
    "[5 punchy 2-3 word urgency badges in brackets like [WAIT FOR IT], [EXPOSED], [DON'T MISS THIS]]"
  ],
  "trending_caption_styles": [
    "3-4 current high-performing visual caption styles (e.g. Alex Hormozi neon green, Dynamic Pop, Crimson Thriller, Cyber Cyan)"
  ],
  "winning_hook_methods": [
    "4-5 specific editing tactics for the first 3 seconds (e.g. The Negative Confession, The Split-Second Pattern Interrupt)"
  ],
  "retention_tactics": [
    "4 actionable editing & pacing rules extracted from these winners"
  ],
  "title_formulas": [
    "3 high-CTR title templates based on these winners"
  ],
  "prompt_injection_text": "A dense 5-sentence instruction paragraph summarizing the core viral rules that every AI generator must strictly implement."
}}
Only return valid JSON. Do not include markdown code fence formatting.
"""
        models_to_try = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]
        for model in models_to_try:
            try:
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json")
                )
                if resp.text:
                    parsed = json.loads(resp.text)
                    parsed["last_scanned"] = datetime.utcnow().isoformat()
                    parsed["total_famous_clips_analyzed"] = len(clips)
                    return parsed
            except Exception as e:
                print(f"[TrendBot] Model {model} failed: {e}")
                continue

        return DEFAULT_PLAYBOOK

    def run_trend_analysis(self, force: bool = False, api_key: Optional[str] = None) -> Dict:
        """Execute full scan & intelligence compilation."""
        current = self.get_playbook()
        last_scanned = current.get("last_scanned")

        if not force and last_scanned:
            try:
                last_dt = datetime.fromisoformat(last_scanned)
                if datetime.utcnow() - last_dt < timedelta(hours=24):
                    print(f"[TrendBot] Playbook is fresh (scanned {last_scanned}). Skipping.")
                    return current
            except Exception:
                pass

        print("[TrendBot] Capturing famous viral clips & compiling 24h Playbook...")
        clips = self.fetch_trending_shorts_metadata(max_results=15)

        effective_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not effective_key:
            from app.core.tracker import AnalyticsTracker
            tracker_db = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "storage", "database.json")
            effective_key = AnalyticsTracker(tracker_db).get_settings().get("gemini_api_key", "")

        analyzed = self.analyze_trends_with_gemini(clips, effective_key)
        self._save_playbook(analyzed)
        print(f"[TrendBot] Viral Playbook successfully compiled! Learned from {len(clips)} viral clips.")
        return analyzed

    def research_online_trends(self, api_key: Optional[str] = None) -> Dict:
        """
        Forces an on-demand online research cycle: scrapes top viral Shorts,
        evaluates current trends in caption typography, pacing, and 3-second hook edits,
        and saves an updated playbook immediately.
        """
        return self.run_trend_analysis(force=True, api_key=api_key)

    def start_background_daemon(self, interval_hours: int = 24):
        """Start a background daemon thread that refreshes the playbook every 24 hours."""
        if self._is_running:
            return

        def _worker():
            self._is_running = True
            while self._is_running:
                try:
                    self.run_trend_analysis(force=False)
                except Exception as err:
                    print(f"[TrendBot Background Worker Error] {err}")
                time.sleep(interval_hours * 3600)

        t = threading.Thread(target=_worker, daemon=True, name="ViralTrendBotDaemon")
        t.start()
        print("[TrendBot] 24-Hour Viral Trend Bot Daemon started.")

# Singleton instance
trend_bot_instance = ViralTrendBot()

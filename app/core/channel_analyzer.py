import os
import re
import json
import subprocess
from typing import Dict, List, Any, Optional

KNOWN_BENCHMARKS = {
    "mrbeast": {"handle": "@MrBeast", "name": "MrBeast"},
    "alex hormozi": {"handle": "@AlexHormozi", "name": "Alex Hormozi"},
    "alexhormozi": {"handle": "@AlexHormozi", "name": "Alex Hormozi"},
    "the diary of a ceo": {"handle": "@TheDiaryOfACEO", "name": "The Diary Of A CEO"},
    "diary of a ceo": {"handle": "@TheDiaryOfACEO", "name": "The Diary Of A CEO"},
    "steven bartlett": {"handle": "@TheDiaryOfACEO", "name": "The Diary Of A CEO"},
    "stevenbartlett": {"handle": "@TheDiaryOfACEO", "name": "The Diary Of A CEO"},
    "huberman lab": {"handle": "@hubermanlab", "name": "Huberman Lab"},
    "hubermanlab": {"handle": "@hubermanlab", "name": "Huberman Lab"},
    "andrew huberman": {"handle": "@hubermanlab", "name": "Huberman Lab"},
    "mrballen": {"handle": "@MrBallen", "name": "MrBallen"},
    "lex fridman": {"handle": "@lexfridman", "name": "Lex Fridman"},
    "lexfridman": {"handle": "@lexfridman", "name": "Lex Fridman"},
    "joe rogan": {"handle": "@joerogan", "name": "Joe Rogan"},
    "powerfuljre": {"handle": "@joerogan", "name": "Joe Rogan"},
    "veritasium": {"handle": "@veritasium", "name": "Veritasium"},
    "tom bilyeu": {"handle": "@TomBilyeu", "name": "Tom Bilyeu"},
    "impact theory": {"handle": "@TomBilyeu", "name": "Tom Bilyeu"},
    "ali abdaal": {"handle": "@aliabdaal", "name": "Ali Abdaal"},
    "aliabdaal": {"handle": "@aliabdaal", "name": "Ali Abdaal"},
    "iman gadzhi": {"handle": "@ImanGadzhi", "name": "Iman Gadzhi"},
    "imangadzhi": {"handle": "@ImanGadzhi", "name": "Iman Gadzhi"},
    "chris williamson": {"handle": "@ChrisWillx", "name": "Chris Williamson"},
    "modern wisdom": {"handle": "@ChrisWillx", "name": "Modern Wisdom"},
    "david goggins": {"handle": "@DavidGoggins", "name": "David Goggins"},
}

def normalize_channel_url(input_str: str) -> str:
    """
    Normalizes handles, plain creator names, and URLs to target the YouTube popular videos stream.
    """
    s = input_str.strip()
    if not s:
        return ""

    low = s.lower().strip()
    if low in KNOWN_BENCHMARKS:
        h = KNOWN_BENCHMARKS[low]["handle"]
        return f"https://www.youtube.com/{h}/videos?view=0&sort=p&flow=grid"

    # Already a full URL
    if "youtube.com" in s or "youtu.be" in s:
        # Strip trailing slash or existing tab suffix
        base = re.sub(r'/(videos|shorts|streams|featured|community).*$', '', s).rstrip('/')
        return f"{base}/videos?view=0&sort=p&flow=grid"

    # Begins with @ handle
    if s.startswith("@"):
        clean_handle = s.split()[0]
        return f"https://www.youtube.com/{clean_handle}/videos?view=0&sort=p&flow=grid"

    # Plain name without @
    no_space = re.sub(r'\s+', '', s)
    return f"https://www.youtube.com/@{no_space}/videos?view=0&sort=p&flow=grid"

def format_view_count(views: Optional[int]) -> str:
    if not views:
        return "N/A"
    if views >= 1_000_000_000:
        return f"{views / 1_000_000_000:.1f}B views"
    if views >= 1_000_000:
        return f"{views / 1_000_000:.1f}M views"
    if views >= 1_000:
        return f"{views / 1_000:.1f}K views"
    return f"{views} views"

def format_duration(seconds: Optional[int]) -> str:
    if not seconds:
        return "Unknown"
    m = seconds // 60
    s = seconds % 60
    if m >= 60:
        h = m // 60
        m = m % 60
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def calculate_clipping_score(view_count: Optional[int], duration_sec: Optional[int], title: str) -> int:
    views = view_count or 0
    duration = duration_sec or 600

    score = 0
    # View component (max 50)
    if views >= 10_000_000:
        score += 50
    elif views >= 5_000_000:
        score += 45
    elif views >= 2_000_000:
        score += 40
    elif views >= 1_000_000:
        score += 35
    elif views >= 500_000:
        score += 25
    else:
        score += max(5, int((views / 1_000_000) * 25))

    # Duration component (max 30) - ideal 12 to 55 minutes
    if 720 <= duration <= 3300:
        score += 30
    elif 480 <= duration <= 5400:
        score += 24
    else:
        score += 15

    # Title Curiosity (max 20)
    t_lower = title.lower()
    curiosity_words = ["why", "how", "secret", "truth", "never", "insane", "real", "what", "revealed", "billion", "scariest", "explained"]
    matches = sum(1 for w in curiosity_words if w in t_lower)
    score += min(20, matches * 7)

    return min(99, max(50, score))

def _parse_entries_to_videos(raw_entries: List[Dict], min_views: int) -> List[Dict[str, Any]]:
    all_videos = []
    for it in raw_entries:
        if not it or not isinstance(it, dict):
            continue
        v_id = it.get("id")
        if not v_id:
            continue
        title = it.get("title") or "Untitled Video"
        views = it.get("view_count")
        duration = it.get("duration")

        thumb_url = f"https://img.youtube.com/vi/{v_id}/maxresdefault.jpg"
        if it.get("thumbnails") and len(it["thumbnails"]) > 0:
            thumb_url = it["thumbnails"][-1].get("url") or thumb_url

        score = calculate_clipping_score(views, duration, title)
        is_1m_plus = bool(views and views >= min_views)

        all_videos.append({
            "video_id": v_id,
            "url": f"https://www.youtube.com/watch?v={v_id}",
            "title": title,
            "view_count": views or 0,
            "view_count_formatted": format_view_count(views),
            "duration": duration or 0,
            "duration_formatted": format_duration(duration),
            "thumbnail": thumb_url,
            "clipping_score": score,
            "is_1m_plus": is_1m_plus,
            "recommendation_badge": "🔥 1M+ VIRAL CERTIFIED" if is_1m_plus else ("⚡ HIGH POTENTIAL" if score >= 80 else "POTENTIAL CLIP")
        })
    return all_videos


def extract_channel_viral_videos(
    channel_input: str,
    min_views: int = 1_000_000,
    max_scan: int = 30
) -> Dict[str, Any]:
    """
    Scans a YouTube channel URL or handle, finds videos with > 1M views,
    evaluates viral clipping potential, and returns them sorted by views and score.
    Includes fast ytsearch fallback and benchmark cache if YouTube tab 404s.
    """
    raw_query = channel_input.strip()
    if not raw_query:
        return {"error": "Invalid channel link or handle provided."}

    clean_url = normalize_channel_url(raw_query)

    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "-J",
        "--playlist-end", str(max_scan),
        clean_url
    ]

    uploader = "YouTube Channel"
    channel_url = clean_url
    all_videos = []

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=50,
            check=False
        )

        stdout_valid = bool(proc.stdout and proc.stdout.strip() not in ("", "null"))
        data = None
        if stdout_valid:
            try:
                data = json.loads(proc.stdout)
            except Exception:
                data = None

        # If direct URL failed or returned null/404, attempt ytsearch fallback
        if not data or not isinstance(data, dict) or proc.returncode != 0:
            search_query = re.sub(r'https?://[^\s]+', '', raw_query).strip() or raw_query
            search_query = search_query.lstrip('@')
            search_cmd = [
                "yt-dlp",
                "--flat-playlist",
                "-J",
                f"ytsearch{max_scan}:{search_query}"
            ]
            fallback_proc = subprocess.run(search_cmd, capture_output=True, text=True, timeout=25, check=False)
            if fallback_proc.stdout and fallback_proc.stdout.strip() not in ("", "null"):
                try:
                    data = json.loads(fallback_proc.stdout)
                except Exception:
                    data = None

        if data and isinstance(data, dict):
            uploader = data.get("uploader") or data.get("channel") or data.get("title") or uploader
            channel_url = data.get("channel_url") or data.get("webpage_url") or channel_url
            raw_entries = data.get("entries") or []
            all_videos = _parse_entries_to_videos(raw_entries, min_views)

    except subprocess.TimeoutExpired:
        # Timeout occurred; attempt quick ytsearch fallback
        try:
            search_query = raw_query.lstrip('@')
            search_cmd = ["yt-dlp", "--flat-playlist", "-J", f"ytsearch15:{search_query}"]
            f_proc = subprocess.run(search_cmd, capture_output=True, text=True, timeout=20, check=False)
            if f_proc.stdout and f_proc.stdout.strip() not in ("", "null"):
                data = json.loads(f_proc.stdout)
                uploader = data.get("uploader") or data.get("title") or uploader
                all_videos = _parse_entries_to_videos(data.get("entries") or [], min_views)
        except Exception:
            pass

    except Exception as e:
        print(f"[ChannelAnalyzer Notice] Scan error: {e}")

    # If still empty, check benchmark catalog fallback
    low_input = raw_query.lower().strip()
    if not all_videos and (low_input in KNOWN_BENCHMARKS or any(k in low_input for k in KNOWN_BENCHMARKS)):
        matched_key = next((k for k in KNOWN_BENCHMARKS if k in low_input), "alex hormozi")
        bench_info = KNOWN_BENCHMARKS[matched_key]
        uploader = bench_info["name"]
        channel_url = f"https://www.youtube.com/{bench_info['handle']}"
        try:
            b_cmd = ["yt-dlp", "--flat-playlist", "-J", f"ytsearch20:{bench_info['name']} podcast"]
            b_proc = subprocess.run(b_cmd, capture_output=True, text=True, timeout=25, check=False)
            if b_proc.stdout and b_proc.stdout.strip() not in ("", "null"):
                b_data = json.loads(b_proc.stdout)
                all_videos = _parse_entries_to_videos(b_data.get("entries") or [], min_views)
        except Exception:
            pass

    if not all_videos:
        return {"error": f"No videos found for '{channel_input}'. Please check the channel handle or URL and try again."}

    # Separate 1M+ videos
    million_plus = [v for v in all_videos if v["is_1m_plus"]]
    million_plus.sort(key=lambda x: (x["view_count"], x["clipping_score"]), reverse=True)

    other_videos = [v for v in all_videos if not v["is_1m_plus"]]
    other_videos.sort(key=lambda x: (x["view_count"], x["clipping_score"]), reverse=True)

    # Final list: 1M+ videos first, followed by top other videos
    combined_results = million_plus + other_videos

    return {
        "success": True,
        "channel_title": uploader,
        "channel_url": channel_url,
        "total_scanned": len(all_videos),
        "count_1m_plus": len(million_plus),
        "videos": combined_results[:20]
    }

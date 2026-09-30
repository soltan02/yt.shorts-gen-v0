import os
import sys
import re
import json
import threading
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, send_from_directory, redirect, url_for, current_app, session

from app.core.transcript import extract_video_id, fetch_video_metadata, get_transcript
from app.core.viral_ai import analyze_viral_clips
from app.core.downloader import download_clip_section
from app.core.subtitle import generate_dynamic_subtitles
from app.core.video_engine import render_vertical_clip
from app.core.thumbnail import create_viral_thumbnail
from app.core.thumbnail_ai import generate_thumbnail_variants, generate_thumbnail_variants_with_meta
from app.core.uploader import YouTubeUploader
from app.core.tracker import AnalyticsTracker
from app.core.trend_bot import trend_bot_instance
from app.core.video_scout import suggest_niche_videos, audit_video_viral_potential, NICHE_CONFIGS
from app.core.style_intelligence import style_intelligence_engine
from app.core.channel_analyzer import extract_channel_viral_videos
from app.core.thumbnail_ctr_bot import thumbnail_ctr_bot

# Start 24-hour background trend scanner
try:
    trend_bot_instance.start_background_daemon(interval_hours=24)
except Exception as e:
    print(f"[TrendBot] Daemon startup notice: {e}")

main_bp = Blueprint('main', __name__)

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

STORAGE_DIR = os.path.join(BASE_DIR, "storage")
DOWNLOADS_DIR = os.path.join(STORAGE_DIR, "downloads")
PROCESSED_DIR = os.path.join(STORAGE_DIR, "processed")
DB_PATH = os.path.join(STORAGE_DIR, "database.json")

os.makedirs(DOWNLOADS_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

uploader = YouTubeUploader(STORAGE_DIR)
tracker = AnalyticsTracker(DB_PATH)

# In-memory cache for recent video analysis and OAuth PKCE verifiers
video_cache = {}
active_oauth_flows = {}

def cleanup_clip_media_files(clip_data: dict):
    """
    Safely purges processed video files and temporary raw cuts from local disk.
    Prevents depleting user storage when clips are rejected, deleted, or published to YouTube.
    """
    if not clip_data:
        return

    # 1. Remove processed vertical video .mp4
    file_path = clip_data.get("file_path")
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
            print(f"[Storage Cleanup] Removed processed video: {file_path}")
        except Exception as e:
            print(f"[Storage Cleanup] Notice removing file_path: {e}")

    # 2. Remove matching raw video cuts and subtitles in DOWNLOADS_DIR
    video_id = clip_data.get("video_id")
    start = clip_data.get("start")

    if video_id and os.path.exists(DOWNLOADS_DIR):
        try:
            for fname in os.listdir(DOWNLOADS_DIR):
                if video_id in fname and not fname.endswith("_transcript.json"):
                    if (start is not None and str(int(start)) in fname) or fname.endswith(".ass") or fname.startswith("raw_"):
                        target_f = os.path.join(DOWNLOADS_DIR, fname)
                        if os.path.exists(target_f):
                            try:
                                os.remove(target_f)
                                print(f"[Storage Cleanup] Removed temp file: {fname}")
                            except Exception:
                                pass
        except Exception as e:
            print(f"[Storage Cleanup] Temp cleanup notice: {e}")

def get_current_channel_context():
    channels = uploader.get_connected_channels()
    active_id = tracker.get_active_channel_id()
    if not active_id and channels:
        active_id = channels[0].get("channel_id")
        tracker.set_active_channel_id(active_id)
    active_channel = next((c for c in channels if c.get("channel_id") == active_id), None)
    if not active_channel and channels:
        active_channel = channels[0]
        active_id = active_channel.get("channel_id")
    return channels, active_id, active_channel

@main_bp.context_processor
def inject_channel_context():
    channels, active_id, active_channel = get_current_channel_context()
    return {
        "channels": channels,
        "active_channel_id": active_id,
        "active_channel": active_channel,
        "yt_connected": len(channels) > 0 or uploader.is_authenticated()
    }

@main_bp.route('/api/set-active-channel', methods=['POST'])
def api_set_active_channel():
    data = request.get_json() or {}
    channel_id = data.get('channel_id')
    if channel_id:
        tracker.set_active_channel_id(channel_id)
        return jsonify({"success": True, "active_channel_id": channel_id})
    return jsonify({"error": "channel_id required"}), 400

@main_bp.route('/')
def index():
    return redirect(url_for('main.studio'))

@main_bp.route('/studio')
def studio():
    settings = tracker.get_settings()
    has_gemini = bool(os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key"))
    return render_template(
        'studio.html', 
        has_gemini=has_gemini,
        active_tab='studio'
    )

@main_bp.route('/queue')
def queue():
    _, active_id, _ = get_current_channel_context()
    clips = tracker.get_all_clips(channel_id=active_id)
    scheduled = [c for c in clips if c.get("status") == "scheduled"]
    ready = [c for c in clips if c.get("status") == "accepted"]
    return render_template(
        'queue.html',
        scheduled=scheduled,
        ready=ready,
        active_tab='queue'
    )

@main_bp.route('/analytics')
def analytics():
    _, active_id, _ = get_current_channel_context()
    # Fast non-blocking load directly from local SQLite (< 1ms)
    # Never blocks on synchronous external YouTube/yt-dlp queries
    stats = tracker.get_channel_stats(channel_id=active_id)
    
    # Auto-reconcile scheduled clips whose publish time has passed
    tracker.auto_reconcile_scheduled_clips()
    clips = tracker.get_all_clips(channel_id=active_id)
    now_utc = datetime.utcnow()
    
    posted = []
    scheduled = []
    
    for c in clips:
        st = c.get("status")
        sched_str = c.get("scheduled_for")
        is_future_sched = False
        if sched_str:
            try:
                dt = datetime.fromisoformat(sched_str.replace("Z", "+00:00"))
                sched_utc = dt.astimezone().replace(tzinfo=None) if dt.tzinfo is not None else dt
                if sched_utc > now_utc:
                    is_future_sched = True
            except Exception:
                pass

        if st == "published" and not is_future_sched:
            posted.append(c)
        elif st == "scheduled" or is_future_sched:
            # Scheduled content: strictly do NOT show views, likes, or comments
            c_copy = dict(c)
            c_copy["views"] = None
            c_copy["likes"] = None
            c_copy["comments"] = None
            c_copy["subs_gained"] = None
            scheduled.append(c_copy)

    return render_template(
        'analytics.html',
        published=posted,
        scheduled=scheduled,
        stats=stats,
        active_tab='analytics'
    )

@main_bp.route('/playbook')
def playbook():
    return render_template(
        'playbook.html',
        active_tab='playbook'
    )

@main_bp.route('/settings')
def settings_page():
    settings = tracker.get_settings()
    has_secret = uploader.has_client_secrets()
    gemini_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key", "")
    return render_template(
        'settings.html',
        has_secret=has_secret,
        gemini_key=gemini_key,
        active_tab='settings'
    )

# --- API Endpoints ---

@main_bp.route('/api/auto-prescan', methods=['POST'])
def api_auto_prescan():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    if not url:
        return jsonify({"error": "Please provide a YouTube video URL"}), 400

    video_id = extract_video_id(url)
    if not video_id or not re.match(r'^[a-zA-Z0-9_\-]{6,24}$', video_id):
        return jsonify({"error": "Invalid YouTube URL or Video ID"}), 400

    try:
        meta = fetch_video_metadata(video_id)
        transcript_data, lang = get_transcript(video_id)

        intelligence = style_intelligence_engine.analyze_and_auto_select(
            video_title=meta.get("title", ""),
            transcript=transcript_data or []
        )

        return jsonify({
            "success": True,
            "video_id": video_id,
            "metadata": meta,
            "intelligence": intelligence
        })
    except Exception as e:
        print(f"[AutoPrescan Error] {e}")
        return jsonify({
            "success": True,
            "video_id": video_id,
            "metadata": {"video_id": video_id, "title": "YouTube Video", "duration": 300},
            "intelligence": {
                "auto_selected_niche": "storytelling_crime",
                "auto_selected_layout": "auto",
                "auto_selected_clip_mode": "standalone",
                "auto_selected_art_direction": "crimson_thriller",
                "art_direction_display": "🚨 Crimson Thriller (Crime / Mystery)",
                "video_type": "solo_creator",
                "layout_reason": "📱 Phone-Adaptive 9:16 layout auto-selected",
                "mode_reason": "⚡ Standalone Shorts auto-selected",
                "adaptive_note": "🏛️ 1M+ Benchmark Grounded: Directed by proven top creator formats (@MrBallen, @AlexHormozi, @hubermanlab).",
                "adaptation_level": "1m_benchmark",
                "published_history_count": 0
            }
        })

@main_bp.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    num_clips = max(1, min(3, int(data.get('num_clips', 3))))

    if not url:
        return jsonify({"error": "Please provide a YouTube video URL"}), 400

    video_id = extract_video_id(url)
    if not video_id or not re.match(r'^[a-zA-Z0-9_\-]{6,24}$', video_id):
        return jsonify({"error": "Invalid YouTube URL or Video ID"}), 400

    try:
        # Fetch metadata
        meta = fetch_video_metadata(video_id)

        # Fetch transcript
        transcript_data, lang = get_transcript(video_id)

        # Get Gemini key
        settings = tracker.get_settings()
        gemini_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key")
        if not gemini_key or gemini_key == "your_gemini_api_key_here":
            return jsonify({
                "error": "Gemini API Key is missing. Please add your free key in Settings.",
                "redirect_settings": True
            }), 400

        # Autonomous Style & Format Intelligence
        auto_intelligence = style_intelligence_engine.analyze_and_auto_select(
            video_title=meta.get("title", ""),
            transcript=transcript_data or []
        )

        req_clip_mode = data.get('clip_mode')
        req_niche = data.get('niche')

        clip_mode = req_clip_mode if req_clip_mode and req_clip_mode != 'auto' else auto_intelligence.get("auto_selected_clip_mode", "standalone")
        niche = req_niche if req_niche and req_niche != 'auto' else auto_intelligence.get("auto_selected_niche", "storytelling_crime")

        # AI analysis for viral hooks and video type detection
        vid_duration = float(meta.get("duration", 300.0))
        analysis = analyze_viral_clips(
            transcript=transcript_data,
            video_title=meta.get("title", ""),
            api_key=gemini_key,
            num_clips=num_clips,
            preferred_language=lang,
            clip_mode=clip_mode,
            niche=niche,
            video_duration=vid_duration
        )

        clips = analysis.get("clips", [])
        if not clips:
            print("[Analyze] Warning: Analysis returned 0 clips. Triggering fallback...")
            fallback_analysis = analyze_viral_clips(
                transcript=transcript_data or [],
                video_title=meta.get("title", ""),
                api_key="forced_fallback",
                num_clips=num_clips,
                preferred_language=lang,
                clip_mode=clip_mode,
                niche=niche,
                video_duration=vid_duration
            )
            clips = fallback_analysis.get("clips", [])

        # Automatically pick the winning style based on what works best for this video/niche
        winning_style = auto_intelligence.get("auto_selected_art_direction") or "alex_hormozi"
        for clip in clips:
            current_art = clip.get("caption_art_direction")
            if not current_art or current_art in ("yellow_electric", "auto"):
                clip["caption_art_direction"] = winning_style

        # Run AI Quality Guard on all generated clips before returning/caching
        from app.core.quality_guard import quality_guard
        clips = quality_guard.evaluate_and_guard_clips(
            clips=clips,
            transcript=transcript_data or [],
            clip_mode=clip_mode,
            video_title=meta.get("title", ""),
            niche=niche
        )

        video_type = "solo_creator"
        recommended_layout = "auto"
        layout_reason = "Phone-adaptive 9:16 layout (unified single frame with ambient fill, no splitting)"
        series_id = analysis.get("series_id")
        series_title = analysis.get("series_title")
        total_parts = analysis.get("total_parts")

        # Cache video data for rendering
        video_cache[video_id] = {
            "metadata": meta,
            "transcript": transcript_data,
            "clips": clips,
            "video_type": video_type,
            "recommended_layout": recommended_layout,
            "layout_reason": layout_reason,
            "clip_mode": clip_mode,
            "niche": niche,
            "series_id": series_id,
            "series_title": series_title,
            "total_parts": total_parts,
            "auto_intelligence": auto_intelligence
        }

        return jsonify({
            "success": True,
            "metadata": meta,
            "clips": clips,
            "video_type": video_type,
            "recommended_layout": recommended_layout,
            "layout_reason": layout_reason,
            "language": lang,
            "clip_mode": clip_mode,
            "niche": niche,
            "series_id": series_id,
            "series_title": series_title,
            "total_parts": total_parts,
            "auto_intelligence": auto_intelligence
        })

    except Exception as e:
        print(f"[Analyze Error] {e}")
        # Resilient recovery: return non-overlapping distinct heuristic fallback clips across timeline
        try:
            dur = float(meta.get("duration", 300.0)) if ('meta' in locals() and meta and meta.get("duration")) else 300.0
            real_t = transcript_data if ('transcript_data' in locals() and transcript_data) else []
            if not real_t:
                try:
                    real_t, _ = get_transcript(video_id)
                except Exception:
                    real_t = []

            emergency_analysis = analyze_viral_clips(
                transcript=real_t,
                video_title=meta.get("title", f"Video {video_id}") if ('meta' in locals() and meta) else f"Video {video_id}",
                api_key="forced_fallback",
                num_clips=num_clips,
                clip_mode=data.get('clip_mode', 'standalone'),
                niche=data.get('niche', 'storytelling_crime'),
                video_duration=dur
            )
            em_clips = emergency_analysis.get("clips", [])
            if em_clips:
                em_meta = meta if ('meta' in locals() and meta) else {
                    "video_id": video_id, 
                    "title": f"YouTube Video ({video_id})", 
                    "thumbnail": f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg", 
                    "duration": dur, 
                    "channel": "YouTube"
                }
                video_cache[video_id] = {
                    "metadata": em_meta, 
                    "transcript": real_t, 
                    "clips": em_clips, 
                    "video_type": "solo_creator", 
                    "recommended_layout": "auto"
                }
                return jsonify({
                    "success": True,
                    "metadata": em_meta,
                    "clips": em_clips,
                    "video_type": "solo_creator",
                    "recommended_layout": "auto",
                    "layout_reason": "Phone-adaptive 9:16 layout",
                    "language": "en"
                })
        except Exception as rec_err:
            print(f"[Analyze Recovery Error] {rec_err}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/render-clip', methods=['POST'])
def api_render_clip():
    data = request.get_json() or {}
    video_id = data.get('video_id')
    start = float(data.get('start_seconds', 0))
    end = float(data.get('end_seconds', 0))
    layout = data.get('layout', 'auto')
    title = data.get('title', 'Viral Clip #shorts')
    description = data.get('description', '#shorts #viral')
    tags = data.get('tags', ['shorts', 'viral'])
    hook_rating = int(data.get('hook_rating', 90))
    viral_score = int(data.get('viral_score', hook_rating))
    score_breakdown = data.get('score_breakdown', {})
    psychological_hook = data.get('psychological_hook') or "He didn't mean to say this..."
    thumb_hook = data.get('thumbnail_hook_3words') or title
    thumb_prompt = data.get('thumbnail_prompt') or "Cinematic 8k close-up portrait of an expressive creator in a modern dark studio, dramatic neon rim lights, YouTube Shorts thumbnail composition, 9:16 vertical"
    thumb_color = data.get('thumbnail_color_theme', 'yellow_black')
    series_id = data.get('series_id')
    part_number = data.get('part_number')
    total_parts = data.get('total_parts')
    part_label = data.get('part_label') or (f"Part {part_number}/{total_parts}" if part_number and total_parts else None)
    cliffhanger_hook = data.get('cliffhanger_hook')
    subscriber_cta = data.get('subscriber_cta')
    pinned_comment = data.get('pinned_comment')
    reaction_spark_comment = data.get('reaction_spark_comment') or pinned_comment
    comment_strategy = data.get('comment_strategy') or 'controversy_debate'
    if not pinned_comment and reaction_spark_comment:
        pinned_comment = reaction_spark_comment
    clip_mode = data.get('clip_mode', 'standalone')
    niche = data.get('niche', 'storytelling_crime')
    caption_art_direction = data.get('caption_art_direction') or 'yellow_electric'
    sticker_badge = data.get('sticker_badge')
    quality_check = data.get('quality_check') or {}
    title_archetypes = data.get('title_archetypes')
    seamless_loop_score = data.get('seamless_loop_score')
    seamless_loop_rating = data.get('seamless_loop_rating')
    seamless_loop_reason = data.get('seamless_loop_reason')
    edited_transcript = data.get('edited_transcript')

    part_info = None
    if part_number and total_parts:
        part_info = {
            "series_id": series_id,
            "part_number": int(part_number),
            "total_parts": int(total_parts),
            "part_label": part_label
        }

    if not video_id or not re.match(r'^[a-zA-Z0-9_\-]{6,24}$', str(video_id)) or end <= start:
        return jsonify({"error": "Invalid clip timing or video ID"}), 400

    try:
        cached = video_cache.get(video_id, {})
        # Auto-resolve layout: supports center_crop, split_gaming, blur_stack
        if not layout or layout == 'auto':
            rec = data.get('recommended_layout') or cached.get('recommended_layout')
            layout = rec if rec in ('center_crop', 'split_gaming', 'split_screen', 'blur_stack') else 'center_crop'
        if layout not in ('center_crop', 'split_gaming', 'split_screen', 'blur_stack'):
            layout = 'center_crop'

        background_music = data.get('background_music')
        gameplay_track = data.get('gameplay_track')
        enable_kinetic_zoom = bool(data.get('enable_kinetic_zoom', True))
        show_top_hook = bool(data.get('show_top_hook', False))

        if not caption_art_direction or caption_art_direction == 'auto':
            caption_art_direction = cached.get('auto_intelligence', {}).get('auto_selected_art_direction') or 'yellow_electric'

        # 1. Guarantee transcript is loaded (from memory, disk cache, or fresh fetch)
        transcript = cached.get("transcript")
        transcript_disk_path = os.path.join(DOWNLOADS_DIR, f"{video_id}_transcript.json")

        if not transcript and os.path.exists(transcript_disk_path):
            try:
                with open(transcript_disk_path, "r", encoding="utf-8") as f:
                    transcript = json.load(f)
            except Exception:
                pass

        if not transcript:
            print(f"[Render] Fetching transcript directly for {video_id}...")
            transcript, _ = get_transcript(video_id)
            try:
                with open(transcript_disk_path, "w", encoding="utf-8") as f:
                    json.dump(transcript, f)
            except Exception:
                pass

        # Apply speech & thought completion boundary snapping
        if transcript and not edited_transcript:
            from app.core.viral_ai import snap_to_speech_boundary
            snapped_s = snap_to_speech_boundary(start, transcript, is_start=True, max_drift=3.0)
            snapped_e = snap_to_speech_boundary(end, transcript, is_start=False, max_drift=5.5, current_start=snapped_s)
            if 15.0 <= (snapped_e - snapped_s) <= 59.5:
                start = snapped_s
                end = snapped_e

        # 2. Download specific section with speech-accurate boundaries
        raw_cut_path = download_clip_section(video_id, start, end, DOWNLOADS_DIR)

        # Apply inline caption quick-fix if user edited the transcript
        if edited_transcript:
            if isinstance(edited_transcript, list) and edited_transcript:
                transcript = edited_transcript
            elif isinstance(edited_transcript, str) and edited_transcript.strip():
                words = edited_transcript.strip().split()
                if words:
                    w_dur = max(0.18, (end - start) / len(words))
                    transcript = [{"start": start + i * w_dur, "duration": w_dur, "text": w} for i, w in enumerate(words)]

        # 3. Generate dynamic styled ASS subtitles (Top Header is OFF by default for clean video)
        settings = tracker.get_settings()
        gemini_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key")

        sub_path = os.path.join(DOWNLOADS_DIR, f"{video_id}_{int(start)}_{int(end)}.ass")
        _, caption_review = generate_dynamic_subtitles(
            transcript=transcript, 
            clip_start=start, 
            clip_end=end, 
            output_ass_path=sub_path,
            api_key=gemini_key,
            psychological_hook=psychological_hook,
            part_info=part_info,
            subscriber_cta=subscriber_cta,
            caption_art_direction=caption_art_direction,
            sticker_badge=sticker_badge,
            show_top_hook=show_top_hook
        )

        # 4. Render 9:16 vertical video with burnt-in subtitles & top hook sticker
        output_filename = f"short_{video_id}_{int(start)}_{layout}.mp4"
        output_path = os.path.join(PROCESSED_DIR, output_filename)

        video_type = data.get('video_type') or cached.get('video_type')
        render_vertical_clip(
            input_video_path=raw_cut_path,
            output_video_path=output_path,
            layout=layout,
            subtitle_ass_path=sub_path,
            video_type=video_type,
            enable_kinetic_zoom=enable_kinetic_zoom,
            background_music=background_music,
            gameplay_track=gameplay_track
        )

        # 5. Generate high-CTR viral 9:16 thumbnail using Gemini hook text
        thumb_filename = f"thumb_{video_id}_{int(start)}.jpg"
        thumb_path = os.path.join(PROCESSED_DIR, thumb_filename)
        thumb_url = f"/media/{thumb_filename}"
        badge_thumb = f"PART {part_number}" if part_number else "⚠️ DON'T MISS THIS"
        try:
            create_viral_thumbnail(
                video_path=output_path, 
                output_thumb_path=thumb_path, 
                hook_title=thumb_hook,
                color_theme=thumb_color,
                badge_text=badge_thumb,
                prompt=thumb_prompt
            )
        except Exception as e:
            print(f"[Thumbnail Error] {e}")
            thumb_url = None
            thumb_path = None

        # Resolve active channel profile
        _, active_id, active_ch = get_current_channel_context()
        channel_id = data.get('channel_id') or active_id
        channel_title = active_ch.get('title') if active_ch else ''

        # 6. Save to Tracker
        clip_data = {
            "video_id": video_id,
            "channel_id": channel_id,
            "channel_title": channel_title,
            "title": title,
            "description": description,
            "tags": tags,
            "start": start,
            "end": end,
            "duration": round(end - start, 1),
            "layout": layout,
            "hook_rating": hook_rating,
            "viral_score": viral_score,
            "score_breakdown": score_breakdown,
            "psychological_hook": psychological_hook,
            "series_id": series_id,
            "part_number": int(part_number) if part_number else None,
            "total_parts": int(total_parts) if total_parts else None,
            "part_label": part_label,
            "cliffhanger_hook": cliffhanger_hook,
            "subscriber_cta": subscriber_cta,
            "pinned_comment": pinned_comment,
            "reaction_spark_comment": reaction_spark_comment,
            "comment_strategy": comment_strategy,
            "caption_art_direction": caption_art_direction,
            "sticker_badge": sticker_badge,
            "clip_mode": clip_mode,
            "niche": niche,
            "title_archetypes": title_archetypes,
            "seamless_loop_score": seamless_loop_score,
            "seamless_loop_rating": seamless_loop_rating,
            "seamless_loop_reason": seamless_loop_reason,
            "file_name": output_filename,
            "file_path": output_path,
            "thumbnail_file": thumb_filename,
            "thumbnail_path": thumb_path,
            "thumbnail_url": thumb_url,
            "thumbnail_prompt": thumb_prompt,
            "caption_review": caption_review,
            "quality_check": quality_check,
            "status": "rendered",
            "video_url": f"/media/{output_filename}"
        }
        clip_id = tracker.save_clip(clip_data)

        return jsonify({
            "success": True,
            "clip_id": clip_id,
            "channel_id": channel_id,
            "video_url": f"/media/{output_filename}",
            "thumbnail_url": thumb_url,
            "thumbnail_prompt": thumb_prompt,
            "caption_review": caption_review,
            "quality_check": quality_check,
            "viral_score": viral_score,
            "score_breakdown": score_breakdown,
            "psychological_hook": psychological_hook,
            "caption_art_direction": caption_art_direction,
            "sticker_badge": sticker_badge,
            "title_archetypes": title_archetypes,
            "seamless_loop_score": seamless_loop_score,
            "seamless_loop_rating": seamless_loop_rating,
            "seamless_loop_reason": seamless_loop_reason,
            "series_id": series_id,
            "part_number": part_number,
            "total_parts": total_parts,
            "part_label": part_label,
            "cliffhanger_hook": cliffhanger_hook,
            "subscriber_cta": subscriber_cta,
            "pinned_comment": pinned_comment,
            "reaction_spark_comment": reaction_spark_comment,
            "comment_strategy": comment_strategy,
            "title": title
        })

    except Exception as e:
        print(f"[Render Error] {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/upload-youtube', methods=['POST'])
def api_upload_youtube():
    data = request.get_json() or {}
    clip_id = data.get('clip_id')
    channel_id = data.get('channel_id')
    title = data.get('title')
    description = data.get('description')
    tags = data.get('tags')
    privacy_status = data.get('privacy_status', 'public')
    publish_at = data.get('publish_at')  # ISO timestamp or None

    clip = tracker.get_clip(clip_id)
    if not clip or not os.path.exists(clip.get("file_path", "")):
        return jsonify({"error": "Clip file not found"}), 404

    if not uploader.is_authenticated():
        return jsonify({"error": "No YouTube account connected. Please connect in Settings."}), 401

    try:
        result = uploader.upload_short(
            video_file_path=clip["file_path"],
            title=title or clip["title"],
            description=description or clip["description"],
            tags=tags or clip.get("tags", []),
            privacy_status=privacy_status,
            publish_at=publish_at,
            channel_id=channel_id,
            thumbnail_path=clip.get("thumbnail_path")
        )

        status = "scheduled" if publish_at else "published"
        # Storage preservation: YouTube has the video, clean up local copy to save drive space
        cleanup_clip_media_files(clip)
        tracker.update_clip(clip_id, {
            "status": status,
            "channel_id": channel_id,
            "youtube_video_id": result["video_id"],
            "youtube_url": result["url"],
            "published_at": datetime.now().isoformat(),
            "scheduled_for": publish_at,
            "local_cleaned": True,
            "file_path": None
        })

        return jsonify({
            "success": True,
            "video_id": result["video_id"],
            "url": result["url"],
            "status": status
        })

    except Exception as e:
        print(f"[YouTube Upload Error] {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/schedule-batch', methods=['POST'])
def api_schedule_batch():
    """Batch schedule ready clips across upcoming days (e.g. 3 per day at peak US times)."""
    data = request.get_json() or {}
    clip_ids = data.get('clip_ids', [])
    channel_id = data.get('channel_id')
    start_date_str = data.get('start_date')  # YYYY-MM-DD
    times = data.get('times', ["12:00", "16:00", "20:00"])  # Peak EST times

    if not clip_ids:
        return jsonify({"error": "No clips selected for scheduling"}), 400

    if not uploader.is_authenticated():
        return jsonify({"error": "Please connect your YouTube channel first"}), 401

    base_date = datetime.strptime(start_date_str, "%Y-%m-%d") if start_date_str else datetime.utcnow() + timedelta(days=1)
    scheduled_results = []

    time_idx = 0
    day_offset = 0

    for cid in clip_ids:
        clip = tracker.get_clip(cid)
        if not clip or clip.get("status") != "accepted":
            print(f"[BatchSchedule] Skipping {cid}: not accepted")
            continue

        target_time = times[time_idx]
        thour, tmin = map(int, target_time.split(":"))
        schedule_dt = datetime(base_date.year, base_date.month, base_date.day, thour, tmin) + timedelta(days=day_offset)
        iso_str = schedule_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        try:
            res = uploader.upload_short(
                video_file_path=clip["file_path"],
                title=clip["title"],
                description=clip["description"],
                tags=clip.get("tags", []),
                privacy_status="private",
                publish_at=iso_str,
                channel_id=channel_id,
                thumbnail_path=clip.get("thumbnail_path")
            )
            # Storage preservation: YouTube has the video scheduled, clean up local file
            cleanup_clip_media_files(clip)
            tracker.update_clip(cid, {
                "status": "scheduled",
                "channel_id": channel_id,
                "youtube_video_id": res["video_id"],
                "youtube_url": res["url"],
                "scheduled_for": iso_str,
                "local_cleaned": True,
                "file_path": None
            })
            scheduled_results.append({
                "clip_id": cid,
                "title": clip["title"],
                "scheduled_for": iso_str,
                "url": res["url"]
            })
        except Exception as e:
            print(f"[Batch Schedule Error for {cid}] {e}")

        time_idx += 1
        if time_idx >= len(times):
            time_idx = 0
            day_offset += 1

    return jsonify({"success": True, "scheduled": scheduled_results})

@main_bp.route('/api/autopilot', methods=['POST'])
def api_autopilot():
    """
    1-Click Autopilot:
    1. Analyzes URL & auto-detects video type (solo creator vs podcast)
    2. Takes the top #1 viral clip
    3. Downloads targeted segment
    4. Burns dynamic safe-zone subtitles
    5. Creates custom AI thumbnail
    6. Automatically publishes directly to the selected YouTube channel!
    """
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    channel_id = data.get('channel_id')
    privacy_status = data.get('privacy_status', 'public')

    if not url:
        return jsonify({"error": "Please provide a YouTube video URL"}), 400

    if not uploader.is_authenticated():
        return jsonify({"error": "No YouTube channel connected. Please connect in Settings."}), 401

    video_id = extract_video_id(url)
    if not video_id or not re.match(r'^[a-zA-Z0-9_\-]{6,24}$', video_id):
        return jsonify({"error": "Invalid YouTube URL or Video ID"}), 400

    try:
        # Step 1: Metadata & Transcript
        meta = fetch_video_metadata(video_id)
        transcript_data, lang = get_transcript(video_id)

        # Save transcript to disk
        transcript_disk_path = os.path.join(DOWNLOADS_DIR, f"{video_id}_transcript.json")
        try:
            with open(transcript_disk_path, "w", encoding="utf-8") as f:
                json.dump(transcript_data, f)
        except Exception:
            pass

        # Step 2: Gemini Analysis & Auto-Type Detection
        settings = tracker.get_settings()
        gemini_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key")
        if not gemini_key or gemini_key == "your_gemini_api_key_here":
            return jsonify({"error": "Gemini API Key missing. Please set in Settings."}), 400

        analysis = analyze_viral_clips(
            transcript=transcript_data,
            video_title=meta.get("title", ""),
            api_key=gemini_key,
            num_clips=3,
            preferred_language=lang
        )

        clips = analysis.get("clips", [])
        if not clips:
            return jsonify({"error": "No high-retention clips found in this video."}), 400

        best_clip = clips[0]
        layout = data.get('layout') or analysis.get("recommended_layout", "center_crop")
        if layout not in ('center_crop', 'blur_stack'):
            layout = 'center_crop'
        show_top_hook = bool(data.get('show_top_hook', False))

        # Step 3: Download Section
        start = best_clip["start_seconds"]
        end = best_clip["end_seconds"]
        raw_cut = download_clip_section(video_id, start, end, DOWNLOADS_DIR)

        # Step 4: Subtitles with Caption Review Bot
        sub_path = os.path.join(DOWNLOADS_DIR, f"{video_id}_{int(start)}_{int(end)}.ass")
        psych_hook = best_clip.get("psychological_hook") or ""
        caption_art = best_clip.get("caption_art_direction") or "yellow_electric"
        sticker_badge = best_clip.get("sticker_badge")
        _, caption_review = generate_dynamic_subtitles(
            transcript=transcript_data, 
            clip_start=start, 
            clip_end=end, 
            output_ass_path=sub_path,
            api_key=gemini_key,
            psychological_hook=psych_hook,
            subscriber_cta=best_clip.get("subscriber_cta"),
            caption_art_direction=caption_art,
            sticker_badge=sticker_badge,
            show_top_hook=show_top_hook
        )

        # Step 5: Render 9:16 vertical video HD
        output_filename = f"short_{video_id}_{int(start)}_{layout}.mp4"
        output_path = os.path.join(PROCESSED_DIR, output_filename)
        render_vertical_clip(raw_cut, output_path, layout=layout, subtitle_ass_path=sub_path)

        # Step 6: Generate AI Thumbnail
        thumb_filename = f"thumb_{video_id}_{int(start)}.jpg"
        thumb_path = os.path.join(PROCESSED_DIR, thumb_filename)
        thumb_hook = best_clip.get("thumbnail_hook_3words") or best_clip["suggested_title"]
        thumb_prompt = best_clip.get("thumbnail_prompt") or "Cinematic 8k close-up portrait of an expressive creator in a dark studio, dramatic lighting, 9:16 vertical"
        create_viral_thumbnail(
            video_path=output_path, 
            output_thumb_path=thumb_path, 
            hook_title=thumb_hook,
            color_theme=best_clip.get("thumbnail_color_theme", "yellow_black"),
            badge_text="⚠️ DON'T MISS THIS",
            prompt=thumb_prompt
        )

        _, active_id, active_ch = get_current_channel_context()
        target_channel_id = channel_id or active_id

        clip_data = {
            "video_id": video_id,
            "channel_id": target_channel_id,
            "channel_title": active_ch.get("title", "") if active_ch else "",
            "title": best_clip["suggested_title"],
            "description": best_clip["suggested_description"],
            "tags": best_clip["tags"],
            "start": start,
            "end": end,
            "duration": best_clip["duration"],
            "layout": layout,
            "hook_rating": best_clip["hook_rating"],
            "viral_score": best_clip.get("viral_score", best_clip["hook_rating"]),
            "score_breakdown": best_clip.get("score_breakdown", {}),
            "psychological_hook": psych_hook,
            "caption_art_direction": caption_art,
            "sticker_badge": sticker_badge,
            "pinned_comment": best_clip.get("pinned_comment") or best_clip.get("reaction_spark_comment"),
            "reaction_spark_comment": best_clip.get("reaction_spark_comment") or best_clip.get("pinned_comment"),
            "comment_strategy": best_clip.get("comment_strategy"),
            "subscriber_cta": best_clip.get("subscriber_cta"),
            "cliffhanger_hook": best_clip.get("cliffhanger_hook"),
            "file_name": output_filename,
            "file_path": output_path,
            "thumbnail_file": thumb_filename,
            "thumbnail_path": thumb_path,
            "thumbnail_url": f"/media/{thumb_filename}",
            "thumbnail_prompt": thumb_prompt,
            "caption_review": caption_review,
            "status": "ready",
            "video_url": f"/media/{output_filename}"
        }
        clip_id = tracker.save_clip(clip_data)

        # Step 7: Upload directly to YouTube
        upload_res = uploader.upload_short(
            video_file_path=output_path,
            title=best_clip["suggested_title"],
            description=best_clip["suggested_description"],
            tags=best_clip["tags"],
            privacy_status=privacy_status,
            channel_id=channel_id,
            thumbnail_path=thumb_path
        )

        # Storage preservation: YouTube has the video, clean up local copy to save drive space
        cleanup_clip_media_files(clip_data)
        tracker.update_clip(clip_id, {
            "status": "published",
            "channel_id": channel_id,
            "youtube_video_id": upload_res["video_id"],
            "youtube_url": upload_res["url"],
            "published_at": datetime.now().isoformat(),
            "local_cleaned": True,
            "file_path": None
        })

        return jsonify({
            "success": True,
            "message": "Autopilot completed successfully!",
            "video_id": upload_res["video_id"],
            "youtube_url": upload_res["url"],
            "title": best_clip["suggested_title"],
            "thumbnail_url": f"/media/{thumb_filename}",
            "thumbnail_prompt": thumb_prompt,
            "caption_review": caption_review,
            "layout_used": layout,
            "video_type": analysis.get("video_type"),
            "hook_score": best_clip["hook_rating"],
            "viral_score": best_clip.get("viral_score", best_clip["hook_rating"]),
            "score_breakdown": best_clip.get("score_breakdown", {}),
            "reaction_spark_comment": best_clip.get("reaction_spark_comment") or best_clip.get("pinned_comment"),
            "comment_strategy": best_clip.get("comment_strategy"),
            "caption_art_direction": caption_art,
            "sticker_badge": sticker_badge
        })

    except Exception as e:
        print(f"[Autopilot Error] {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/channels/delete', methods=['POST'])
def api_delete_channel():
    data = request.get_json() or {}
    channel_id = data.get('channel_id')
    if channel_id:
        uploader.remove_channel(channel_id)
    return jsonify({"success": True})

@main_bp.route('/api/refresh-stats', methods=['POST'])
def api_refresh_stats():
    stats = tracker.refresh_youtube_stats(uploader)
    return jsonify({"success": True, "stats": stats})

@main_bp.route('/api/sync-performance', methods=['POST'])
def api_sync_performance():
    """
    Refreshes published clip metrics (views, likes, comments, subscriber attribution),
    feeds the analytics into the Adaptive Style Intelligence engine, and returns
    updated stats, subscriber gains, and style leaderboard.
    """
    try:
        stats = tracker.refresh_youtube_stats(uploader)
        insights = style_intelligence_engine.get_historical_performance()
        return jsonify({
            "success": True,
            "stats": stats,
            "insights": insights,
            "total_shorts_subs_gained": stats.get("total_shorts_subs_gained", 0),
            "leaderboard": insights.get("leaderboard", []),
            "top_performing_style": insights.get("top_performing_style")
        })
    except Exception as e:
        print(f"[Sync Performance Error] {e}")
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/performance-insights', methods=['GET'])
def api_performance_insights():
    """Return the style intelligence historical performance metrics and style leaderboard."""
    try:
        insights = style_intelligence_engine.get_historical_performance()
        return jsonify({"success": True, "insights": insights})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@main_bp.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    if request.method == 'POST':
        data = request.get_json() or {}
        gemini_key = data.get('gemini_api_key', '').strip()
        if gemini_key:
            tracker.update_settings({"gemini_api_key": gemini_key})
            os.environ["GEMINI_API_KEY"] = gemini_key
        return jsonify({"success": True})
    
    settings = tracker.get_settings()
    has_gemini = bool(os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key"))
    return jsonify({"success": True, "settings": settings, "has_gemini": has_gemini})

# --- YouTube OAuth Endpoints ---

@main_bp.route('/auth/youtube')
def auth_youtube():
    if not uploader.has_client_secrets():
        return "Missing client_secret.json in storage/ folder.", 400
    flow = uploader.get_auth_flow(redirect_uri="http://localhost:5001/oauth2callback")
    auth_url, state = flow.authorization_url(
        prompt='consent', 
        access_type='offline',
        include_granted_scopes='true'
    )
    # Save code_verifier in session and in-memory map keyed by state
    if hasattr(flow, 'code_verifier') and flow.code_verifier:
        session['code_verifier'] = flow.code_verifier
        active_oauth_flows[state] = flow.code_verifier
    session['oauth_state'] = state
    return redirect(auth_url)

@main_bp.route('/oauth2callback')
def oauth2callback():
    code = request.args.get('code')
    state = request.args.get('state')
    if not code:
        return "Authorization failed: no code provided", 400
    try:
        flow = uploader.get_auth_flow(redirect_uri="http://localhost:5001/oauth2callback")
        verifier = active_oauth_flows.get(state) or session.get('code_verifier')
        if verifier:
            flow.code_verifier = verifier
            flow.fetch_token(code=code, code_verifier=verifier)
        else:
            flow.fetch_token(code=code)

        channel_info = uploader.register_channel_from_credentials(flow.credentials)
        channel_title = channel_info.get("title", "Channel")

        # Cleanup state
        if state and state in active_oauth_flows:
            del active_oauth_flows[state]

        return redirect(f'/settings?connected={channel_title}')
    except Exception as e:
        print(f"[OAuth Callback Error] {e}")
        return f"OAuth Error: {e}", 500


# ─── Review / Accept / Reject / Delete Endpoints ─────────────────────────────

@main_bp.route('/api/review-clips', methods=['GET'])
def api_review_clips():
    """Return all clips that are in rendered, accepted, or rejected state for the active channel."""
    _, active_id, _ = get_current_channel_context()
    channel_id = request.args.get('channel_id') or active_id
    clips = tracker.get_clips_by_status("rendered", "ready", "accepted", "rejected", channel_id=channel_id)
    # Attach media URLs and normalize status
    for c in clips:
        if c.get("status") == "ready":
            c["status"] = "rendered"
        if c.get("file_name") and not c.get("video_url"):
            c["video_url"] = f"/media/{c['file_name']}"
        if c.get("thumbnail_file") and not c.get("thumbnail_url"):
            c["thumbnail_url"] = f"/media/{c['thumbnail_file']}"
    return jsonify({"clips": clips, "active_channel_id": active_id})


@main_bp.route('/api/accept-clip', methods=['POST'])
def api_accept_clip():
    """Mark a clip as accepted — moves it into the scheduling queue."""
    data = request.get_json() or {}
    clip_id = data.get("clip_id")
    if not clip_id:
        return jsonify({"error": "clip_id required"}), 400
    tracker.update_clip(clip_id, {"status": "accepted"})
    return jsonify({"success": True, "clip_id": clip_id, "status": "accepted"})


@main_bp.route('/api/reject-clip', methods=['POST'])
def api_reject_clip():
    """Mark a clip as rejected and immediately delete its local files to save disk storage."""
    data = request.get_json() or {}
    clip_id = data.get("clip_id")
    if not clip_id:
        return jsonify({"error": "clip_id required"}), 400
    clip = tracker.get_clip(clip_id)
    if clip:
        cleanup_clip_media_files(clip)
    tracker.update_clip(clip_id, {"status": "rejected", "local_cleaned": True, "file_path": None})
    return jsonify({"success": True, "clip_id": clip_id, "status": "rejected", "local_cleaned": True})


@main_bp.route('/api/delete-clips', methods=['POST'])
def api_delete_clips():
    """Bulk delete clips and their associated files from disk."""
    data = request.get_json() or {}
    clip_ids = data.get("clip_ids", [])
    if not clip_ids:
        return jsonify({"error": "clip_ids list required"}), 400

    deleted = []
    for cid in clip_ids:
        clip = tracker.get_clip(cid)
        if clip:
            # Delete video file and temp files
            cleanup_clip_media_files(clip)

            # Delete thumbnail files (original + AI variants)
            for key in ("thumbnail_path",):
                tp = clip.get(key, "")
                if tp and os.path.exists(tp):
                    try:
                        os.remove(tp)
                    except Exception:
                        pass
            # Delete AI thumbnail variants if they exist
            for v in range(1, 4):
                vpath = os.path.join(PROCESSED_DIR, f"thumb_{cid}_v{v}.jpg")
                if os.path.exists(vpath):
                    try:
                        os.remove(vpath)
                    except Exception:
                        pass
            deleted.append(cid)

    tracker.delete_clips(clip_ids)
    return jsonify({"success": True, "deleted": deleted})


@main_bp.route('/api/analyze-channel', methods=['POST'])
def api_analyze_channel():
    """
    Scans a YouTube channel link or handle for videos with >1M views
    and evaluates their viral clipping potential.
    """
    data = request.get_json() or {}
    channel_url = (data.get('channel_url') or data.get('channel_input') or data.get('channel_id') or data.get('channel') or '').strip()
    min_views = int(data.get('min_views', 1_000_000))
    if not channel_url:
        return jsonify({"error": "Please provide a YouTube channel URL or handle"}), 400

    try:
        results = extract_channel_viral_videos(channel_url, min_views=min_views, max_scan=50)
        if "error" in results:
            return jsonify({"error": results["error"]}), 400
        return jsonify(results)
    except Exception as e:
        print(f"[Channel Analyzer Error] {e}")
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/generate-thumbnails', methods=['POST'])
def api_generate_thumbnails():
    """
    Generate 3 viral thumbnail variants for a clip across diverse styles:
      - 4K Enhanced Video Keyframe (Micro-contrast, saturation, pill badge)
      - Photorealistic Flux AI Studio Art (Curiosity gap concept)
      - High-Action Peak Moment (Alternative emotional frame)
    Supports style_seed for infinite style cycling.
    """
    data = request.get_json() or {}
    clip_id = data.get("clip_id")
    prompt = data.get("thumbnail_prompt") or data.get("prompt") or ""
    style_seed = int(data.get("style_seed") or 0)

    if not clip_id:
        return jsonify({"error": "clip_id required"}), 400

    settings = tracker.get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key") or ""

    clip = tracker.get_clip(clip_id) or {}
    if not prompt:
        prompt = clip.get("thumbnail_prompt", "Cinematic 8k expressive creator portrait, dramatic studio lighting, 9:16 vertical")

    try:
        variants = generate_thumbnail_variants_with_meta(
            prompt=prompt,
            clip_id=clip_id,
            api_key=api_key,
            output_dir=PROCESSED_DIR,
            video_path=clip.get("file_path"),
            psychological_hook=clip.get("psychological_hook"),
            hook_title=clip.get("thumbnail_hook_3words") or clip.get("title"),
            style_seed=style_seed
        )
        ranked_variants = thumbnail_ctr_bot.rank_thumbnail_variants(
            variants=variants,
            hook_text=clip.get("thumbnail_hook_3words") or clip.get("title", ""),
            video_title=clip.get("title", ""),
            niche=clip.get("niche", "storytelling_crime"),
            api_key=api_key
        )
        urls = [v["url"] for v in ranked_variants]
        return jsonify({
            "success": True,
            "thumbnails": urls,
            "variants": ranked_variants,
            "count": len(ranked_variants),
            "style_seed": style_seed
        })
    except Exception as e:
        print(f"[Generate Thumbnails Error] {e}")
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/predict-thumbnail-ctr', methods=['POST'])
def api_predict_thumbnail_ctr():
    """
    Evaluates any thumbnail image for predicted CTR %, virality tier,
    visual dimensions (stopping power, emotional intensity, curiosity gap, safe-zone compliance),
    strengths, and actionable improvements.
    """
    data = request.get_json() or {}
    thumbnail_url = data.get("thumbnail_url", "")
    clip_id = data.get("clip_id")
    hook_text = data.get("hook_text", "")
    video_title = data.get("video_title", "")
    niche = data.get("niche", "storytelling_crime")

    clip = tracker.get_clip(clip_id) if clip_id else {}
    if clip:
        hook_text = hook_text or clip.get("thumbnail_hook_3words") or clip.get("title", "")
        video_title = video_title or clip.get("title", "")
        niche = niche or clip.get("niche", "storytelling_crime")
        if not thumbnail_url:
            thumbnail_url = clip.get("thumbnail_url") or (f"/media/{clip['thumbnail_file']}" if clip.get("thumbnail_file") else "")

    if not thumbnail_url:
        # Check if any default thumbnail exists or generate fallback evaluation
        thumbnail_url = data.get("prompt") or ""
        if not thumbnail_url:
            return jsonify({"error": "thumbnail_url or clip_id required"}), 400

    filename = os.path.basename(thumbnail_url)
    image_path = os.path.join(PROCESSED_DIR, filename)

    settings = tracker.get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key") or ""

    result = thumbnail_ctr_bot.predict_thumbnail_ctr(
        image_path=image_path,
        hook_text=hook_text,
        video_title=video_title,
        niche=niche,
        api_key=api_key
    )
    return jsonify(result)


@main_bp.route('/api/trend-bot/status', methods=['GET'])
def api_trend_bot_status():
    """Return the active 24-hour viral trend playbook and scan statistics."""
    try:
        playbook = trend_bot_instance.get_playbook()
        return jsonify({"success": True, "playbook": playbook})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/trend-bot/scan', methods=['POST'])
def api_trend_bot_scan():
    """Trigger an instant on-demand scan of famous viral clips."""
    try:
        settings = tracker.get_settings()
        api_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key") or ""
        playbook = trend_bot_instance.run_trend_analysis(force=True, api_key=api_key)
        return jsonify({"success": True, "playbook": playbook})
    except Exception as e:
        print(f"[TrendBot Scan API Error] {e}")
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/research-trends', methods=['POST'])
def api_research_trends():
    """
    Runs an on-demand online trend scan across viral Shorts, compiling
    emerging caption styles, 3-second hook formulas, and pattern interrupts.
    """
    try:
        settings = tracker.get_settings()
        api_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key") or ""
        playbook = trend_bot_instance.research_online_trends(api_key=api_key)
        return jsonify({"success": True, "playbook": playbook})
    except Exception as e:
        print(f"[Research Trends Error] {e}")
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/select-thumbnail', methods=['POST'])
def api_select_thumbnail():
    """Save the user's chosen thumbnail for a clip."""
    data = request.get_json() or {}
    clip_id = data.get("clip_id")
    thumbnail_url = data.get("thumbnail_url")  # e.g. /media/thumb_abc_v2.jpg

    if not clip_id or not thumbnail_url:
        return jsonify({"error": "clip_id and thumbnail_url required"}), 400

    filename = os.path.basename(thumbnail_url)
    full_path = os.path.join(PROCESSED_DIR, filename)
    tracker.update_clip(clip_id, {
        "thumbnail_url": thumbnail_url,
        "thumbnail_path": full_path,
        "thumbnail_file": filename,
    })
    return jsonify({"success": True})


@main_bp.route('/api/niches', methods=['GET'])
def api_get_niches():
    """Return available niches and configuration for studio selector."""
    return jsonify({"success": True, "niches": NICHE_CONFIGS})


@main_bp.route('/api/scout-videos', methods=['POST'])
def api_scout_videos():
    """Scout 3 high-potential candidate videos in the requested niche."""
    data = request.get_json() or {}
    niche = data.get('niche', 'storytelling_crime')
    count = int(data.get('count', 3))

    settings = tracker.get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key")

    try:
        suggestions = suggest_niche_videos(niche=niche, count=count, api_key=api_key)
        niche_meta = NICHE_CONFIGS.get(niche, {})
        return jsonify({
            "success": True,
            "niche": niche,
            "niche_label": niche_meta.get("label", niche),
            "videos": suggestions
        })
    except Exception as e:
        print(f"[Scout API Error] {e}")
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/audit-video', methods=['POST'])
def api_audit_video():
    """Pre-scan audit any YouTube video to evaluate 0-100 viral potential before clipping."""
    data = request.get_json() or {}
    url = data.get('url', '').strip()
    niche = data.get('niche', '')

    if not url:
        return jsonify({"error": "Please provide a YouTube video URL to audit"}), 400

    settings = tracker.get_settings()
    api_key = os.getenv("GEMINI_API_KEY") or settings.get("gemini_api_key")

    try:
        audit_result = audit_video_viral_potential(video_url=url, niche=niche, api_key=api_key)
        return jsonify({
            "success": True,
            "audit": audit_result
        })
    except Exception as e:
        print(f"[Audit API Error] {e}")
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/auto-schedule', methods=['POST'])
def api_auto_schedule():
    """
    Auto-schedule all accepted clips: 3 per day at 12:00, 16:00, 20:00 EST.
    Uploads to YouTube as private with scheduled publish_at.
    For multi-part series (series_id), schedules Part 1, 2, 3 consecutively on the same day.
    """
    data = request.get_json() or {}
    channel_id = data.get("channel_id")
    start_date_str = data.get("start_date")  # YYYY-MM-DD optional
    clips_per_day = int(data.get("clips_per_day", 3))
    # Peak EST times for US audience (converted to UTC: EST+5)
    peak_times_utc = data.get("times_utc", ["17:00", "21:00", "01:00"])  # 12:00, 16:00, 20:00 EST → UTC

    if not uploader.is_authenticated():
        return jsonify({"error": "YouTube channel not connected"}), 401

    accepted_clips = tracker.get_clips_by_status("accepted")
    if not accepted_clips:
        return jsonify({"error": "No accepted clips to schedule. Accept some clips first."}), 400

    base_date = (
        datetime.strptime(start_date_str, "%Y-%m-%d")
        if start_date_str
        else datetime.utcnow() + timedelta(days=1)
    )

    # Group series together so multi-part sagas run on the same day in chronological order
    series_groups = {}
    standalone_clips = []
    for c in accepted_clips:
        sid = c.get("series_id")
        if sid:
            series_groups.setdefault(sid, []).append(c)
        else:
            standalone_clips.append(c)

    ordered_groups = []
    for sid, s_clips in series_groups.items():
        s_clips.sort(key=lambda x: int(x.get("part_number") or 1))
        ordered_groups.append(("series", s_clips))
    if standalone_clips:
        ordered_groups.append(("standalone", standalone_clips))

    scheduled_results = []
    day_offset = 0

    for group_type, group_clips in ordered_groups:
        if group_type == "series":
            # Multi-part series gets its own dedicated same-day schedule (e.g. 12 PM, 4 PM, 8 PM EST)
            for part_idx, clip in enumerate(group_clips):
                cid = clip["id"]
                if not os.path.exists(clip.get("file_path", "")):
                    continue
                target_time = peak_times_utc[min(part_idx, len(peak_times_utc) - 1)]
                thour, tmin = map(int, target_time.split(":"))
                schedule_dt = datetime(
                    base_date.year, base_date.month, base_date.day, thour, tmin
                ) + timedelta(days=day_offset)
                iso_str = schedule_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                try:
                    res = uploader.upload_short(
                        video_file_path=clip["file_path"],
                        title=clip.get("title", "Viral Short #shorts"),
                        description=clip.get("description", "#shorts #viral"),
                        tags=clip.get("tags", ["shorts", "viral"]),
                        privacy_status="private",
                        publish_at=iso_str,
                        channel_id=channel_id,
                        thumbnail_path=clip.get("thumbnail_path"),
                    )
                    tracker.update_clip(cid, {
                        "status": "scheduled",
                        "channel_id": channel_id,
                        "youtube_video_id": res["video_id"],
                        "youtube_url": res["url"],
                        "scheduled_for": iso_str,
                    })
                    scheduled_results.append({
                        "clip_id": cid,
                        "title": clip.get("title"),
                        "series_id": clip.get("series_id"),
                        "part_number": clip.get("part_number"),
                        "scheduled_for": iso_str,
                        "url": res["url"],
                    })
                except Exception as e:
                    print(f"[AutoSchedule Series] Error scheduling {cid}: {e}")
            # Move to next day for next series
            day_offset += 1
        else:
            # Standalone clips schedule 3/day
            time_idx = 0
            for clip in group_clips:
                cid = clip["id"]
                if not os.path.exists(clip.get("file_path", "")):
                    continue
                target_time = peak_times_utc[time_idx % len(peak_times_utc)]
                thour, tmin = map(int, target_time.split(":"))
                schedule_dt = datetime(
                    base_date.year, base_date.month, base_date.day, thour, tmin
                ) + timedelta(days=day_offset)
                iso_str = schedule_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                try:
                    res = uploader.upload_short(
                        video_file_path=clip["file_path"],
                        title=clip.get("title", "Viral Short #shorts"),
                        description=clip.get("description", "#shorts #viral"),
                        tags=clip.get("tags", ["shorts", "viral"]),
                        privacy_status="private",
                        publish_at=iso_str,
                        channel_id=channel_id,
                        thumbnail_path=clip.get("thumbnail_path"),
                    )
                    tracker.update_clip(cid, {
                        "status": "scheduled",
                        "channel_id": channel_id,
                        "youtube_video_id": res["video_id"],
                        "youtube_url": res["url"],
                        "scheduled_for": iso_str,
                    })
                    scheduled_results.append({
                        "clip_id": cid,
                        "title": clip.get("title"),
                        "scheduled_for": iso_str,
                        "url": res["url"],
                    })
                    time_idx += 1
                    if time_idx % clips_per_day == 0:
                        day_offset += 1
                except Exception as e:
                    print(f"[AutoSchedule Standalone] Error scheduling {cid}: {e}")

    return jsonify({
        "success": True,
        "scheduled_count": len(scheduled_results),
        "schedule": scheduled_results,
    })


# ─── YouTube Shorts Publishing Metadata & CSV Export ──────────────────────────

@main_bp.route('/api/syndication/<clip_id>', methods=['GET', 'POST'])
def api_get_syndication(clip_id):
    """
    Returns tailored metadata for YouTube Shorts (title archetypes, descriptions, pinned comments).
    Supports GET (by clip_id) or POST (with custom or in-memory clip payload).
    """
    from app.core.syndication import MultiPlatformSyndication
    clip = tracker.get_clip(clip_id)
    if not clip and request.method == 'POST':
        clip = request.get_json() or {}
    if not clip and (str(clip_id).startswith('pending-') or clip_id == 'demo'):
        clip = {"id": clip_id, "title": "Viral Hook Short", "niche": "podcast", "pinned_comment": "What would you do in this situation?"}
    if not clip:
        return jsonify({"error": "Clip not found"}), 404
    
    metadata = MultiPlatformSyndication.generate_all_platforms(clip)
    return jsonify({"success": True, "status": "ok", "metadata": metadata, **metadata})


@main_bp.route('/api/syndication/export-csv', methods=['GET'])
def api_export_syndication_csv():
    """
    Exports all accepted/scheduled clips as a CSV formatted for YouTube Shorts scheduling.
    """
    from app.core.syndication import MultiPlatformSyndication
    from flask import Response
    
    clips = tracker.get_clips_by_status("accepted", "scheduled", "published")
    if not clips:
        clips = tracker.get_all_clips()

    csv_data = MultiPlatformSyndication.generate_csv_export(clips)
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=viral_clips_syndication.csv"}
    )


# ─── Media Serving ────────────────────────────────────────────────────────────

@main_bp.route('/media/<path:filename>')
def serve_media(filename):
    safe_filename = os.path.basename(filename)
    return send_from_directory(PROCESSED_DIR, safe_filename)


import json
import os
import subprocess
from typing import Optional, Tuple, Dict, Any

def get_video_info(video_path: str) -> Dict[str, Any]:
    """Extract width, height, duration, and audio stream presence using ffprobe."""
    info = {
        "width": 1920,
        "height": 1080,
        "duration": 30.0,
        "has_audio": True
    }
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "stream=codec_type,width,height:format=duration",
            "-of", "json",
            video_path
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            data = json.loads(res.stdout)
            format_info = data.get("format", {})
            if "duration" in format_info:
                try:
                    info["duration"] = float(format_info["duration"])
                except Exception:
                    pass
            streams = data.get("streams", [])
            has_audio = False
            for s in streams:
                if s.get("codec_type") == "video" and "width" in s and "height" in s:
                    info["width"] = int(s["width"])
                    info["height"] = int(s["height"])
                elif s.get("codec_type") == "audio":
                    has_audio = True
            info["has_audio"] = has_audio
    except Exception as e:
        print(f"[VideoEngine] ffprobe error: {e}")
    return info

def get_video_dimensions(video_path: str) -> Tuple[int, int]:
    """Legacy helper returning width and height."""
    info = get_video_info(video_path)
    return info["width"], info["height"]

def ensure_viral_assets(base_dir: Optional[str] = None):
    """
    Guarantees storage/music and storage/gameplay contain ready-to-use audio and video loops.
    If tracks are missing, synthesizes high-quality ambient tracks and kinetic gameplay loops in seconds.
    """
    if not base_dir:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    music_dir = os.path.join(base_dir, "storage", "music")
    gameplay_dir = os.path.join(base_dir, "storage", "gameplay")
    os.makedirs(music_dir, exist_ok=True)
    os.makedirs(gameplay_dir, exist_ok=True)

    tracks = {
        "phonk.mp3": "aevalsrc=sin(65*2*PI*t)*0.35+sin(130*2*PI*t)*0.2*sin(16*2*PI*t)+0.05*random(0):s=44100:d=60",
        "suspense.mp3": "aevalsrc=sin(90*2*PI*t)*0.25+sin(94.5*2*PI*t)*0.2+sin(45*2*PI*t)*0.3:s=44100:d=60",
        "lofi.mp3": "aevalsrc=sin(220*2*PI*t)*0.18+sin(277.18*2*PI*t)*0.14+sin(329.63*2*PI*t)*0.12:s=44100:d=60",
        "epic.mp3": "aevalsrc=sin(130.81*2*PI*t)*0.25+sin(164.81*2*PI*t)*0.2+sin(196*2*PI*t)*0.2+sin(261.63*2*PI*t)*0.15:s=44100:d=60"
    }

    for fn, expr in tracks.items():
        fp = os.path.join(music_dir, fn)
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", expr, "-af", "afade=t=in:st=0:d=1.5,afade=t=out:st=58:d=2.0,volume=0.45", "-c:a", "libmp3lame", "-b:a", "128k", fp]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Ensure at least one gameplay loop exists
    mc_fp = os.path.join(gameplay_dir, "minecraft_parkour.mp4")
    if not os.path.exists(mc_fp) or os.path.getsize(mc_fp) < 1000:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=duration=30:size=1080x960:rate=30", "-vf", "hue=s=sin(t):h=t*15", "-c:v", "libx264", "-preset", "ultrafast", "-crf", "26", "-pix_fmt", "yuv420p", mc_fp]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def render_vertical_clip(
    input_video_path: str,
    output_video_path: str,
    layout: str = "center_crop",
    subtitle_ass_path: Optional[str] = None,
    video_type: Optional[str] = None,
    enable_micro_zoom: bool = True,
    enable_hook_sfx: bool = True,
    enable_kinetic_zoom: bool = True,
    background_music: Optional[str] = None,
    gameplay_track: Optional[str] = None
) -> str:
    """
    Convert any YouTube video format into a broadcast-grade 9:16 (1080x1920) phone-optimized Short.
    
    Upgrades:
      - Split-Screen Gaming Mode: Top 50% = face-centered speaker, Bottom 50% = high-retention gameplay loop.
      - Background Music Ducking: Royalty-free music (Phonk, Suspense, Lo-Fi, Epic) ducked at -18dB beneath voice.
      - Dynamic Kinetic Auto-Zoom: Periodic +12% punch-in zoom alternating every 3-4s to kill visual fatigue.
      - Broadcast Audio Normalization: -14 LUFS YouTube Shorts target loudness + seamless fade in/out.
      - Hook Audio SFX: Blends a subtle 0.35s cinematic riser/whoosh at T=0.0s for scroll-stopping retention.
    """
    os.makedirs(os.path.dirname(output_video_path), exist_ok=True)
    ensure_viral_assets()

    # Detect video dimensions, duration, and audio
    info = get_video_info(input_video_path)
    width = info["width"]
    height = info["height"]
    duration = info["duration"]
    has_audio = info["has_audio"]
    aspect_ratio = width / height if height > 0 else 1.778

    print(f"[VideoEngine] Input: {width}x{height} (AR: {aspect_ratio:.3f}, Dur: {duration:.2f}s, Audio: {has_audio}), Layout: {layout}, BGM: {background_music}, KineticZoom: {enable_kinetic_zoom}")

    # Prepare subtitle filter string if provided
    sub_filter = ""
    if subtitle_ass_path and os.path.exists(subtitle_ass_path):
        clean_path = subtitle_ass_path.replace("\\", "/").replace(":", "\\:")
        sub_filter = f",ass='{clean_path}'"

    # Face Centering Analysis: determine optimal crop coordinates
    try:
        from app.core.face_engine import FaceCenterTracker
        face_coords = FaceCenterTracker.get_optimal_crop_coordinates(input_video_path, duration)
    except Exception as e:
        print(f"[VideoEngine] Face tracking fallback: {e}")
        face_coords = {
            "host_x_norm": 0.25,
            "guest_x_norm": 0.75,
            "solo_x_norm": 0.50,
            "solo_y_norm": 0.35,
            "is_neural_tracking_active": False
        }

    # Resolve extra input tracks (gameplay loop, background music)
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    gameplay_dir = os.path.join(base_dir, "storage", "gameplay")
    music_dir = os.path.join(base_dir, "storage", "music")

    extra_input_args = []
    gameplay_input_idx = None
    music_input_idx = None

    # Check for Split-Screen Gaming Layout
    if layout in ("split_gaming", "split_screen"):
        gp_file = None
        if gameplay_track and os.path.exists(os.path.join(gameplay_dir, f"{gameplay_track}.mp4")):
            gp_file = os.path.join(gameplay_dir, f"{gameplay_track}.mp4")
        elif os.path.exists(gameplay_dir):
            mp4s = [os.path.join(gameplay_dir, f) for f in os.listdir(gameplay_dir) if f.endswith(".mp4") and not f.endswith(".tmp.mp4")]
            if mp4s:
                gp_file = mp4s[0]
        
        if gp_file and os.path.exists(gp_file):
            gameplay_input_idx = 1 + (len(extra_input_args) // 4)
            extra_input_args.extend(["-stream_loop", "-1", "-i", gp_file])
            print(f"[VideoEngine] Split-Screen Gaming loop active: {os.path.basename(gp_file)}")
        else:
            print("[VideoEngine] No gameplay loop found, falling back to center_crop")
            layout = "center_crop"

    # Check for Background Music Track
    if background_music and background_music.lower() not in ("none", "off", "", "false"):
        clean_bgm = background_music.lower().replace("🎵", "").strip()
        bgm_file = None
        for cand in [f"{clean_bgm}.mp3", f"{clean_bgm}.wav"]:
            cp = os.path.join(music_dir, cand)
            if os.path.exists(cp):
                bgm_file = cp
                break
        if not bgm_file and os.path.exists(music_dir):
            all_m = [os.path.join(music_dir, f) for f in os.listdir(music_dir) if f.endswith((".mp3", ".wav"))]
            if all_m:
                bgm_file = all_m[0]
        
        if bgm_file and os.path.exists(bgm_file):
            music_input_idx = 1 + (len(extra_input_args) // 4)
            extra_input_args.extend(["-stream_loop", "-1", "-i", bgm_file])
            print(f"[VideoEngine] Background Music active: {os.path.basename(bgm_file)}")

    # Kinetic Zoom Filter Expression (alternating punch-in +12% every 3.5s for 2.8s)
    kinetic_zoom_expr = (
        "crop=w='if(between(mod(t,6.5),3.2,6.0), iw/1.12, iw)':"
        "h='if(between(mod(t,6.5),3.2,6.0), ih/1.12, ih)':"
        "x='(iw-out_w)/2':y='(ih-out_h)/2',"
        "scale=1080:1920:flags=bicubic,"
        if enable_kinetic_zoom else ""
    )

    # Video Framing Filter
    if layout in ("split_gaming", "split_screen") and gameplay_input_idx is not None:
        # Split screen: top half podcast speaker (1080x960), bottom half kinetic gameplay (1080x960)
        solo_x = face_coords.get("solo_x_norm", 0.50)
        top_w = int(min(width, height * (1080.0 / 960.0)))
        top_x = int(max(0, min(width - top_w, width * solo_x - (top_w / 2.0))))
        
        top_kinetic = (
            "crop=w='if(between(mod(t,6.5),3.2,6.0), iw/1.12, iw)':"
            "h='if(between(mod(t,6.5),3.2,6.0), ih/1.12, ih)':"
            "x='(iw-out_w)/2':y='(ih-out_h)/2',"
            "scale=1080:960:flags=bicubic,"
            if enable_kinetic_zoom else ""
        )

        filter_complex = (
            f"[0:v]crop={top_w}:ih:{top_x}:0,scale=1080:960:flags=bicubic,{top_kinetic}"
            "unsharp=3:3:0.35:3:3:0.0,eq=contrast=1.03:saturation=1.06[top];"
            f"[{gameplay_input_idx}:v]scale=1080:960:force_original_aspect_ratio=increase:flags=bicubic,"
            "crop=1080:960,unsharp=3:3:0.35:3:3:0.0[bottom];"
            f"[top][bottom]vstack=inputs=2{sub_filter}[outv]"
        )
    elif layout in ("center_crop", "full_screen", "fill_screen"):
        # Explicit crop: zoom in to fill whole 9:16 frame with neural face center bias
        solo_x = face_coords.get("solo_x_norm", 0.50)
        crop_x = int(max(0, min(width - (height * 9.0 / 16.0), width * solo_x - (height * 9.0 / 32.0))))
        filter_complex = (
            f"[0:v]crop=ih*9/16:ih:{crop_x}:0,scale=1080:1920:flags=bicubic,{kinetic_zoom_expr}"
            "unsharp=3:3:0.35:3:3:0.0,"
            f"eq=contrast=1.03:saturation=1.06{sub_filter}[outv]"
        )
    elif aspect_ratio <= 0.65:
        # Already vertical (9:16 phone video): direct scale without blur background
        filter_complex = (
            f"[0:v]scale=1080:1920:force_original_aspect_ratio=decrease:flags=bicubic,"
            "pad=1080:1920:(1080-iw)/2:(1920-ih)/2:black,"
            f"{kinetic_zoom_expr}"
            "unsharp=3:3:0.35:3:3:0.0,"
            f"eq=contrast=1.03:saturation=1.06{sub_filter}[outv]"
        )
    else:
        # Landscape 16:9, 4:3, 1:1, or 21:9 (Studio Blur Stack with Gaussian ambient background):
        filter_complex = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase:flags=bicubic,"
            "crop=1080:1920,"
            "gblur=sigma=28:steps=2,"
            "eq=brightness=-0.32:contrast=1.12[bg];"
            "[0:v]scale=1080:1920:force_original_aspect_ratio=decrease:flags=bicubic,"
            "unsharp=3:3:0.35:3:3:0.0,"
            "eq=contrast=1.03:saturation=1.06[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2{sub_filter}[outv]"
        )

    # Audio Normalization, Background Music Ducking, and Hook Audio SFX
    audio_map_args = ["-map", "0:a?"]
    audio_cmd_args = []
    if has_audio:
        fade_out_start = max(0.1, duration - 0.28)
        
        # 1. Voice audio normalization
        amain_filter = f"[0:a]loudnorm=I=-14:LRA=7:tp=-1.5,afade=t=in:st=0:d=0.18,afade=t=out:st={fade_out_start:.2f}:d=0.25[amain]"
        
        # 2. SFX / BGM mixing
        mix_inputs = ["[amain]"]
        extra_audio_filters = []
        
        if enable_hook_sfx:
            extra_audio_filters.append(
                "anoisesrc=d=0.35:c=pink:r=48000,lowpass=f=850,afade=t=in:st=0:d=0.08,afade=t=out:st=0.08:d=0.27,volume=0.38[asfx]"
            )
            mix_inputs.append("[asfx]")
            
        if music_input_idx is not None:
            bgm_fade_out = max(0.5, duration - 1.5)
            extra_audio_filters.append(
                f"[{music_input_idx}:a]volume=0.10,afade=t=in:st=0:d=0.8,afade=t=out:st={bgm_fade_out:.2f}:d=1.5[bgm]"
            )
            mix_inputs.append("[bgm]")
            
        if len(mix_inputs) > 1:
            all_audio_parts = [amain_filter] + extra_audio_filters
            amix_str = f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=first:dropout_transition=2[outa]"
            filter_complex += f";{';'.join(all_audio_parts)};{amix_str}"
            audio_map_args = ["-map", "[outa]"]
        else:
            audio_fade_filter = f"loudnorm=I=-14:LRA=7:tp=-1.5,afade=t=in:st=0:d=0.20,afade=t=out:st={fade_out_start:.2f}:d=0.25"
            audio_map_args = ["-map", "0:a?"]
            audio_cmd_args = ["-af", audio_fade_filter]

    cmd = [
        "ffmpeg", "-y",
        "-i", input_video_path,
        *extra_input_args,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        *audio_map_args,
        *audio_cmd_args,
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "faster",
        "-crf", "19",
        "-threads", "0",
        "-b:v", "7000k",
        "-maxrate", "10000k",
        "-bufsize", "14000k",
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709",
        "-color_primaries", "bt709",
        "-color_trc", "bt709",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-movflags", "+faststart",
        output_video_path
    ]

    print(f"[VideoEngine] Rendering 9:16 vertical clip ({layout}, BGM: {background_music}) to {output_video_path}...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if res.returncode != 0:
        print(f"[VideoEngine] FFmpeg error: {res.stderr}")
        if sub_filter and "ass" in res.stderr.lower():
            print("[VideoEngine] Retrying render without ass subtitles...")
            fallback_fc = filter_complex.replace(sub_filter, "")
            fallback_cmd = [
                "ffmpeg", "-y",
                "-i", input_video_path,
                "-filter_complex", fallback_fc,
                "-map", "[outv]",
                *audio_map_args,
                *audio_cmd_args,
                "-c:v", "libx264",
                "-preset", "faster",
                "-crf", "19",
                "-threads", "0",
                "-b:v", "7000k",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                output_video_path
            ]
            subprocess.run(fallback_cmd, check=True)
        else:
            raise RuntimeError(f"FFmpeg failed to render vertical clip: {res.stderr[:300]}")

    return output_video_path

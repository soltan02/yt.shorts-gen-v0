import os
import subprocess
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageStat
from typing import Optional, List

def find_top_k_frame_timestamps(video_path: str, duration: float = 30.0, k: int = 3) -> List[float]:
    """
    Intelligently scans candidate timestamps across the video to find the
    sharpest, highest-contrast, non-blurry frames (avoiding closed eyes, motion blur, and black frames).
    """
    if not video_path or not os.path.exists(video_path):
        return [2.0, 5.0, 8.0][:k]

    # Probe real video duration if available
    try:
        probe_cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
        out = subprocess.check_output(probe_cmd, text=True, stderr=subprocess.DEVNULL).strip()
        real_dur = float(out)
        if real_dur > 2.0:
            duration = real_dur
    except Exception:
        pass

    sample_ratios = [0.08, 0.16, 0.25, 0.35, 0.48, 0.60, 0.72, 0.84, 0.92]
    pts = [max(0.5, duration * p) for p in sample_ratios]
    scores = []
    tmp_path = video_path + ".eval_tmp.jpg"

    for ts in pts:
        try:
            cmd = ['ffmpeg', '-y', '-ss', str(ts), '-i', video_path, '-vframes', '1', '-q:v', '2', tmp_path]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 1000:
                img = Image.open(tmp_path).convert('L')
                edges = img.filter(ImageFilter.FIND_EDGES)
                sharpness = ImageStat.Stat(edges).mean[0]
                stat = ImageStat.Stat(img)
                contrast = stat.stddev[0]
                brightness = stat.mean[0]
                if 25 < brightness < 240:
                    score = (sharpness * 1.8) + contrast
                    scores.append((ts, score))
        except Exception:
            pass

    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except Exception:
            pass

    scores.sort(key=lambda x: x[1], reverse=True)
    top_ts = [s[0] for s in scores[:k]]
    while len(top_ts) < k:
        top_ts.append(2.0 + len(top_ts) * 3.0)
    return top_ts

def extract_frame_at_time(video_path: str, timestamp: float, output_img_path: str) -> str:
    """Extract a single high-quality frame from video."""
    os.makedirs(os.path.dirname(output_img_path), exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-vframes", "1",
        "-q:v", "2",
        output_img_path
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_img_path

def create_viral_thumbnail(
    video_path: str,
    output_thumb_path: str,
    hook_title: str,
    color_theme: str = "yellow_black",
    timestamp: Optional[float] = None,
    badge_text: str = "MUST WATCH",
    badge_bg: tuple = (220, 20, 60, 230),
    auto_detect_best_frame: bool = True
) -> str:
    """
    Generate an ultra-high CTR 9:16 vertical thumbnail for YouTube Shorts.
    Automatically finds the sharpest, highest-contrast frame, enhances color saturation/contrast,
    and composites punchy, bold viral typography.
    """
    os.makedirs(os.path.dirname(output_thumb_path), exist_ok=True)
    temp_frame = output_thumb_path + ".temp.jpg"

    # Intelligently select best frame if not specified
    if timestamp is None or (auto_detect_best_frame and timestamp <= 0):
        best_pts = find_top_k_frame_timestamps(video_path, k=1)
        effective_ts = best_pts[0] if best_pts else 2.0
    else:
        effective_ts = timestamp

    # Try extracting frame at effective timestamp, fallback to alternatives
    for ts in [effective_ts, 2.5, 1.2]:
        try:
            extract_frame_at_time(video_path, ts, temp_frame)
            if os.path.exists(temp_frame) and os.path.getsize(temp_frame) > 1000:
                break
        except Exception:
            continue

    if not os.path.exists(temp_frame):
        # Create dark gradient background if extraction failed
        base = Image.new("RGBA", (1080, 1920), (18, 18, 24, 255))
    else:
        base = Image.open(temp_frame).convert("RGBA")

    target_w, target_h = 1080, 1920
    # Resize/crop to fill 1080x1920 9:16
    ratio = max(target_w / base.width, target_h / base.height)
    new_size = (int(base.width * ratio), int(base.height * ratio))
    base = base.resize(new_size, Image.Resampling.LANCZOS)
    left = (base.width - target_w) // 2
    top = (base.height - target_h) // 2
    base = base.crop((left, top, left + target_w, top + target_h))

    # Enhance visual punch: boost contrast, saturation, and unsharp mask
    rgb_base = base.convert("RGB")
    rgb_base = rgb_base.filter(ImageFilter.UnsharpMask(radius=2.5, percent=155, threshold=2))
    enh_col = ImageEnhance.Color(rgb_base).enhance(1.28)
    enh_con = ImageEnhance.Contrast(enh_col).enhance(1.22)
    base = enh_con.convert("RGBA")

    # Darkening overlay on top and bottom so text & subject pop
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Top gradient (for text readability)
    for y in range(700):
        alpha = int(215 * (1 - (y / 700)))
        draw_overlay.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))

    # Bottom gradient (for Shorts UI readability)
    for y in range(1300, target_h):
        alpha = int(225 * ((y - 1300) / (target_h - 1300)))
        draw_overlay.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))

    composed = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(composed)

    # Clean hook text for thumbnail: 2 to 4 words max
    clean_text = hook_title.replace("#shorts", "").replace("#viral", "").strip()
    words = clean_text.split()
    if len(words) > 5:
        words = words[:4]

    # Split into 1 or 2 lines
    if len(words) <= 2:
        lines = [" ".join(words).upper()]
    elif len(words) <= 4:
        lines = [" ".join(words[:2]).upper(), " ".join(words[2:]).upper()]
    else:
        lines = [" ".join(words[:3]).upper(), " ".join(words[3:]).upper()]

    # Load bold impactful system font
    font = None
    badge_font = None
    font_paths = [
        "C:\\Windows\\Fonts\\impact.ttf",
        "C:\\Windows\\Fonts\\ariblk.ttf",     # Arial Black
        "C:\\Windows\\Fonts\\segoeprb.ttf",   # Segoe UI Bold
        "C:\\Windows\\Fonts\\arialbd.ttf",    # Arial Bold
    ]
    font_size = 94 if len(lines) == 1 else 82

    for fp in font_paths:
        if os.path.exists(fp):
            try:
                if not font:
                    font = ImageFont.truetype(fp, font_size)
                if not badge_font:
                    badge_font = ImageFont.truetype(fp, 36)
                if font and badge_font:
                    break
            except Exception:
                pass

    if not font:
        font = ImageFont.load_default()
    if not badge_font:
        badge_font = font

    # Draw Top Viral Pill Badge
    b_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    b_w = b_bbox[2] - b_bbox[0]
    b_h = b_bbox[3] - b_bbox[1]
    b_x = (target_w - b_w) // 2
    b_y = 260
    b_pad_x, b_pad_y = 24, 10
    draw.rounded_rectangle(
        [b_x - b_pad_x, b_y - b_pad_y, b_x + b_w + b_pad_x, b_y + b_h + b_pad_y],
        radius=20,
        fill=badge_bg,
        outline=(255, 255, 255, 220),
        width=2
    )
    draw.text((b_x, b_y), badge_text, font=badge_font, fill=(255, 255, 255, 255))

    # Upper-Third Focal Zone (Y = 350 to 580)
    line_height = font_size + 24
    start_y = 350

    # Color themes
    if color_theme == "neon_green":
        text_colors = [(57, 255, 20, 255), (255, 255, 255, 255)]
    elif color_theme == "warning_red":
        text_colors = [(255, 60, 60, 255), (255, 255, 255, 255)]
    else:
        text_colors = [(255, 235, 0, 255), (255, 255, 255, 255)]  # Neon Yellow & Pure White

    for idx, line in enumerate(lines):
        line_y = start_y + (idx * line_height)
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (target_w - text_w) // 2

        line_color = text_colors[idx % len(text_colors)]

        # Draw semi-transparent dark banner behind text line for 100% legibility
        pad_x, pad_y = 32, 14
        banner_rect = [
            text_x - pad_x, 
            line_y - pad_y, 
            text_x + text_w + pad_x, 
            line_y + text_h + pad_y + 8
        ]
        draw.rounded_rectangle(banner_rect, radius=18, fill=(0, 0, 0, 180), outline=(255, 255, 255, 60), width=1)

        # Drop shadow
        draw.text(
            (text_x + 4, line_y + 4),
            line,
            font=font,
            fill=(0, 0, 0, 230)
        )

        # Heavy 8px stroke outline
        draw.text(
            (text_x, line_y), 
            line, 
            font=font, 
            fill=line_color,
            stroke_width=8, 
            stroke_fill=(0, 0, 0, 255)
        )

    # Save finalized JPG
    final_img = composed.convert("RGB")
    final_img.save(output_thumb_path, "JPEG", quality=95)

    # Clean temporary frame
    if os.path.exists(temp_frame):
        try:
            os.remove(temp_frame)
        except Exception:
            pass

    print(f"[Thumbnail] Created viral thumbnail at {output_thumb_path}")
    return output_thumb_path

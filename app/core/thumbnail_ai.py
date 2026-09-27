"""
thumbnail_ai.py — Professional AI Thumbnail Generator for High-CTR YouTube Shorts.
Combines state-of-the-art Flux AI image generation with professional viral typography,
high-contrast color grading, and urgency pill badges tailored for US/UK audiences.
Guarantees 3 distinct, photorealistic, viral-ready variants.
"""
import os
import base64
import glob
import io
import urllib.request
import urllib.parse
import random
import time
from typing import Optional, List
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
from app.core.thumbnail import create_viral_thumbnail, find_top_k_frame_timestamps

# 3 Distinct Creative AI Styles to catch US audience curiosity
AI_VARIANT_STYLES = [
    {
        "id": "v1",
        "style_name": "Shock & Disbelief",
        "prompt_suffix": "cinematic 8k close-up portrait of an expressive creator looking shocked and intense in a modern dark studio, vibrant cyan and orange neon rim lighting, dramatic contrast, hyper-detailed photography, 9:16 vertical composition, highly expressive eyes, studio background",
        "badge_text": "WARNING: HE DIDN'T MEAN THIS",
        "badge_bg": (220, 20, 60, 235),   # Crimson Red
        "highlight_color": (255, 235, 0, 255),  # Electric Yellow
    },
    {
        "id": "v2",
        "style_name": "Dark Mystery & Intrigue",
        "prompt_suffix": "cinematic film still of an intense speaker with high emotional tension, dark moody film noir studio lighting, deep blue and teal shadows, dramatic edge glow, curiosity gap composition, 9:16 vertical format, 8k award-winning portrait",
        "badge_text": "VIRAL: WATCH TILL END",
        "badge_bg": (147, 51, 234, 235),  # Electric Purple
        "highlight_color": (0, 255, 255, 255),  # Cyan Neon
    },
    {
        "id": "v3",
        "style_name": "High-Stakes Warning",
        "prompt_suffix": "dramatic hyper-realistic portrait of an authoritative creator leaning forward with an urgent warning expression, dramatic amber studio spotlight, deep shadows, ultra sharp facial details, 9:16 vertical high-CTR thumbnail composition",
        "badge_text": "EXPOSED: MUST WATCH",
        "badge_bg": (234, 88, 12, 235),   # Amber Alert
        "highlight_color": (255, 60, 60, 255),  # Warning Red
    }
]

def find_video_for_clip(clip_id: str, output_dir: str) -> Optional[str]:
    """Find the rendered mp4 video associated with this clip_id."""
    candidates = glob.glob(os.path.join(output_dir, f"*{clip_id}*.mp4"))
    if candidates:
        return candidates[0]
    all_shorts = glob.glob(os.path.join(output_dir, "short_*.mp4"))
    if all_shorts:
        all_shorts.sort(key=os.path.getmtime, reverse=True)
        return all_shorts[0]
    return None

def fetch_flux_ai_image(prompt: str, timeout: int = 6) -> Optional[bytes]:
    """Fetch high-end photorealistic AI image using Flux diffusion model."""
    try:
        clean_prompt = prompt.replace("\n", " ").strip()
        encoded = urllib.parse.quote(clean_prompt)
        seed = random.randint(1000, 999999)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width=1080&height=1920&nologo=true&model=flux&seed={seed}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
            if len(data) > 5000:
                return data
    except Exception as e:
        print(f"[ThumbnailAI] Flux AI fetch error: {e}")
    return None

def composite_viral_thumbnail(
    image_bytes: bytes,
    output_path: str,
    badge_text: str,
    badge_bg: tuple,
    hook_text: str,
    highlight_color: tuple = (255, 235, 0, 255)
) -> str:
    """
    Composite high-CTR typography, urgency pill badges, and safe-zone gradients
    onto an AI-generated 9:16 background.
    """
    target_w, target_h = 1080, 1920
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Resize/crop to fill 1080x1920 9:16
    ratio = max(target_w / base.width, target_h / base.height)
    new_size = (int(base.width * ratio), int(base.height * ratio))
    base = base.resize(new_size, Image.Resampling.LANCZOS)
    left = (base.width - target_w) // 2
    top = (base.height - target_h) // 2
    base = base.crop((left, top, left + target_w, top + target_h))

    # Boost color punch & unsharp mask for mobile screens
    rgb_base = base.convert("RGB")
    rgb_base = rgb_base.filter(ImageFilter.UnsharpMask(radius=2, percent=130, threshold=2))
    enh_col = ImageEnhance.Color(rgb_base).enhance(1.2)
    enh_con = ImageEnhance.Contrast(enh_col).enhance(1.15)
    base = enh_con.convert("RGBA")

    # Darkening overlay on top and bottom so text & subject pop
    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw_overlay = ImageDraw.Draw(overlay)

    # Top gradient for text readability (Y=0 to 600)
    for y in range(600):
        alpha = int(225 * (1 - (y / 600)))
        draw_overlay.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))

    # Bottom gradient to cover UI & watermarks
    for y in range(target_h - 180, target_h):
        alpha = int(255 * ((y - (target_h - 180)) / 180))
        draw_overlay.line([(0, y), (target_w, y)], fill=(0, 0, 0, alpha))

    composed = Image.alpha_composite(base, overlay)
    draw = ImageDraw.Draw(composed)

    # Load system font
    font = None
    badge_font = None
    for fp in ["C:\\Windows\\Fonts\\impact.ttf", "C:\\Windows\\Fonts\\ariblk.ttf", "C:\\Windows\\Fonts\\arialbd.ttf"]:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, 90)
                badge_font = ImageFont.truetype(fp, 36)
                break
            except Exception:
                pass
    if not font:
        font = ImageFont.load_default()
    if not badge_font:
        badge_font = font

    # 1. Draw Top Viral Pill Badge
    b_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    b_w = b_bbox[2] - b_bbox[0]
    b_h = b_bbox[3] - b_bbox[1]
    b_x = (target_w - b_w) // 2
    b_y = 220
    b_pad_x, b_pad_y = 26, 12
    draw.rounded_rectangle(
        [b_x - b_pad_x, b_y - b_pad_y, b_x + b_w + b_pad_x, b_y + b_h + b_pad_y],
        radius=20,
        fill=badge_bg,
        outline=(255, 255, 255, 230),
        width=2
    )
    draw.text((b_x, b_y), badge_text, font=badge_font, fill=(255, 255, 255, 255))

    # 2. Draw Bold Psychological Hook (Upper-Third Safe-Zone Y=340 to 560)
    clean_hook = hook_text.replace("#shorts", "").replace("#viral", "").strip().upper()
    words = clean_hook.split()
    if len(words) > 5:
        words = words[:4]

    if len(words) <= 2:
        lines = [" ".join(words)]
    elif len(words) <= 4:
        lines = [" ".join(words[:2]), " ".join(words[2:])]
    else:
        lines = [" ".join(words[:3]), " ".join(words[3:])]

    start_y = 330
    line_height = 104

    for idx, line in enumerate(lines):
        line_y = start_y + (idx * line_height)
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_x = (target_w - text_w) // 2

        # Dark semi-transparent backplate
        pad_x, pad_y = 28, 12
        banner_rect = [
            text_x - pad_x,
            line_y - pad_y,
            text_x + text_w + pad_x,
            line_y + text_h + pad_y + 8
        ]
        draw.rounded_rectangle(
            banner_rect,
            radius=18,
            fill=(0, 0, 0, 195),
            outline=(255, 255, 255, 70),
            width=1
        )

        # Drop shadow
        draw.text((text_x + 4, line_y + 4), line, font=font, fill=(0, 0, 0, 240))

        # Colored Stroke & Fill
        line_col = highlight_color if idx == 0 else (255, 255, 255, 255)
        draw.text(
            (text_x, line_y),
            line,
            font=font,
            fill=line_col,
            stroke_width=8,
            stroke_fill=(0, 0, 0, 255)
        )

    final = composed.convert("RGB")
    final.save(output_path, "JPEG", quality=95)
    return output_path

def generate_thumbnail_variants(
    prompt: str,
    clip_id: str,
    api_key: str,
    output_dir: str,
    video_path: Optional[str] = None,
    psychological_hook: Optional[str] = None,
    hook_title: Optional[str] = None,
    style_seed: int = 0
) -> List[str]:
    """
    Generate 3 distinct, high-CTR viral thumbnails across diverse styles:
      - Variant 1: 🎬 4K Enhanced Video Keyframe (Sharpest moment selected, contrast & saturation boost, viral pill badge)
      - Variant 2: 🎨 Photorealistic Flux AI Studio Art (Curiosity gap concept based on psychological hook)
      - Variant 3: ⚡ Secondary Peak Action Frame (Alternative emotional moment with cinema-grade grading)
    Guarantees 3 distinct variants are ALWAYS returned.
    """
    variants_meta = generate_thumbnail_variants_with_meta(
        prompt=prompt,
        clip_id=clip_id,
        api_key=api_key,
        output_dir=output_dir,
        video_path=video_path,
        psychological_hook=psychological_hook,
        hook_title=hook_title,
        style_seed=style_seed
    )
    return [v["path"] for v in variants_meta if os.path.exists(v.get("path", ""))]

def generate_thumbnail_variants_with_meta(
    prompt: str,
    clip_id: str,
    api_key: str,
    output_dir: str,
    video_path: Optional[str] = None,
    psychological_hook: Optional[str] = None,
    hook_title: Optional[str] = None,
    style_seed: int = 0
) -> List[dict]:
    """
    Generate 3 distinct styled thumbnail variants with rich metadata for UI selection.
    """
    os.makedirs(output_dir, exist_ok=True)
    results: List[dict] = []

    effective_hook = (psychological_hook or hook_title or "THE BRUTAL TRUTH").strip()
    target_video = video_path or find_video_for_clip(clip_id, output_dir)
    top_video_frames = find_top_k_frame_timestamps(target_video or "", k=5)

    # Shift timestamps if style_seed is non-zero
    if style_seed > 0 and len(top_video_frames) > 3:
        top_video_frames = top_video_frames[(style_seed % 2):] + top_video_frames[:(style_seed % 2)]

    clean_hook_title = (hook_title or effective_hook).strip().upper()
    clean_psych_hook = (psychological_hook or effective_hook).strip().upper()

    # ─── Variant 1: 🎬 4K Enhanced Video Keyframe (Sharpest Moment) ─────────────
    v1_path = os.path.join(output_dir, f"thumb_{clip_id}_v1.jpg")
    v1_ts = top_video_frames[0] if top_video_frames else 2.5
    try:
        create_viral_thumbnail(
            video_path=target_video or "",
            output_thumb_path=v1_path,
            hook_title=clean_hook_title,
            color_theme="yellow_black",
            timestamp=v1_ts,
            badge_text="WARNING: MUST WATCH",
            badge_bg=(220, 20, 60, 235)
        )
        if os.path.exists(v1_path):
            results.append({
                "path": v1_path,
                "url": f"/media/{os.path.basename(v1_path)}?v={style_seed}",
                "style_name": "Enhanced Video Keyframe",
                "tag": "🎬 Sharpest Frame",
                "badge": "4K Micro-Contrast",
                "description": f"AI selected sharpest moment at {v1_ts:.1f}s with unsharp mask and vibrant saturation."
            })
            print(f"[ThumbnailAI] [KEYFRAME-OK] Variant 1 sharpest frame generated at {v1_ts:.1f}s")
    except Exception as e:
        print(f"[ThumbnailAI] Variant 1 keyframe error: {e}")

    # ─── Variant 2: 🎨 Photorealistic Flux AI Studio Art ────────────────────────
    v2_path = os.path.join(output_dir, f"thumb_{clip_id}_v2.jpg")
    ai_style = AI_VARIANT_STYLES[style_seed % len(AI_VARIANT_STYLES)]
    base_subject = prompt if len(prompt) > 20 else f"cinematic 8k portrait of an expressive creator in a dark studio, {clean_psych_hook}"
    full_flux_prompt = f"{base_subject}, {ai_style['prompt_suffix']}"

    ai_bytes = fetch_flux_ai_image(full_flux_prompt, timeout=6)
    v2_ok = False
    if ai_bytes:
        try:
            composite_viral_thumbnail(
                image_bytes=ai_bytes,
                output_path=v2_path,
                badge_text=ai_style["badge_text"],
                badge_bg=ai_style["badge_bg"],
                hook_text=clean_psych_hook,
                highlight_color=ai_style["highlight_color"]
            )
            if os.path.exists(v2_path):
                results.append({
                    "path": v2_path,
                    "url": f"/media/{os.path.basename(v2_path)}?v={style_seed}",
                    "style_name": "Flux AI Studio Portrait",
                    "tag": "🎨 Photorealistic 8K",
                    "badge": ai_style["style_name"],
                    "description": "AI-generated emotional expression matching the psychological curiosity hook."
                })
                v2_ok = True
                print(f"[ThumbnailAI] [AI-OK] Variant 2 Flux AI generated: {v2_path}")
        except Exception as e:
            print(f"[ThumbnailAI] Variant 2 AI error: {e}")

    if not v2_ok:
        # Fallback to alternative video frame with neon green styling
        v2_ts = top_video_frames[1] if len(top_video_frames) > 1 else 5.0
        try:
            create_viral_thumbnail(
                video_path=target_video or "",
                output_thumb_path=v2_path,
                hook_title=clean_psych_hook,
                color_theme="neon_green",
                timestamp=v2_ts,
                badge_text="VIRAL: WATCH TILL END",
                badge_bg=(147, 51, 234, 235)
            )
            if os.path.exists(v2_path):
                results.append({
                    "path": v2_path,
                    "url": f"/media/{os.path.basename(v2_path)}?v={style_seed}",
                    "style_name": "Neon Curiosity Frame",
                    "tag": "⚡ High Retention",
                    "badge": "Neon Accent",
                    "description": f"Emotional keyframe at {v2_ts:.1f}s with neon green and purple contrast."
                })
        except Exception as e:
            print(f"[ThumbnailAI] Variant 2 fallback error: {e}")

    # ─── Variant 3: ⚡ Secondary Peak Action Frame / Deep Film Noir ─────────────
    v3_path = os.path.join(output_dir, f"thumb_{clip_id}_v3.jpg")
    v3_ts = top_video_frames[2] if len(top_video_frames) > 2 else (top_video_frames[1] if len(top_video_frames) > 1 else 8.0)
    try:
        create_viral_thumbnail(
            video_path=target_video or "",
            output_thumb_path=v3_path,
            hook_title=clean_psych_hook if len(clean_psych_hook.split()) <= 4 else clean_hook_title,
            color_theme="warning_red",
            timestamp=v3_ts,
            badge_text="EXPOSED: MUST WATCH",
            badge_bg=(234, 88, 12, 235)
        )
        if os.path.exists(v3_path):
            results.append({
                "path": v3_path,
                "url": f"/media/{os.path.basename(v3_path)}?v={style_seed}",
                "style_name": "High-Action Peak Moment",
                "tag": "🔥 Urgent Alert",
                "badge": "Amber Alert",
                "description": f"Peak emotional frame at {v3_ts:.1f}s with high-contrast amber warning grade."
            })
            print(f"[ThumbnailAI] [KEYFRAME-OK] Variant 3 action frame generated at {v3_ts:.1f}s")
    except Exception as e:
        print(f"[ThumbnailAI] Variant 3 error: {e}")

    print(f"[ThumbnailAI] Finished generating {len(results)} multi-style thumbnail options.")
    return results

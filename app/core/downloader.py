import os
import subprocess
from typing import Optional
import yt_dlp

def seconds_to_hhmmss(seconds: float) -> str:
    """Format seconds into HH:MM:SS.mmm for ffmpeg/yt-dlp."""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hrs:02d}:{mins:02d}:{secs:06.3f}"

def download_clip_section(
    video_id: str, 
    start_seconds: float, 
    end_seconds: float, 
    output_dir: str
) -> str:
    """
    Download only the specific time section of a YouTube video using yt-dlp.
    Bypasses YouTube 403 Forbidden using tv/android player client fallbacks.
    Returns path to downloaded .mp4 file.
    """
    os.makedirs(output_dir, exist_ok=True)
    start_fmt = seconds_to_hhmmss(start_seconds)
    end_fmt = seconds_to_hhmmss(end_seconds)

    start_int = int(start_seconds)
    end_int = int(end_seconds)
    filename = f"{video_id}_{start_int}_{end_int}.mp4"
    output_path = os.path.join(output_dir, filename)

    if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
        print(f"[Downloader] Cache hit: {output_path} already exists.")
        return output_path

    url = f"https://www.youtube.com/watch?v={video_id}"
    section = f"*{start_fmt}-{end_fmt}"
    print(f"[Downloader] Downloading section {section} for {video_id}...")

    # Strategy 1: tv & android player clients with download_ranges
    ydl_opts_list = [
        # Option A: TV + Android player client (most reliable against 403)
        {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best/18',
            'download_ranges': yt_dlp.utils.download_range_func(None, [(start_seconds, end_seconds)]),
            'force_keyframes_at_cuts': True,
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': True,
            'force_overwrites': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['tv', 'android', 'web']
                }
            }
        },
        # Option B: Android alone
        {
            'format': '18/best[ext=mp4]/best',
            'download_ranges': yt_dlp.utils.download_range_func(None, [(start_seconds, end_seconds)]),
            'force_keyframes_at_cuts': True,
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': True,
            'force_overwrites': True,
            'extractor_args': {
                'youtube': {
                    'player_client': ['android']
                }
            }
        },
        # Option C: Web client standard
        {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'download_ranges': yt_dlp.utils.download_range_func(None, [(start_seconds, end_seconds)]),
            'force_keyframes_at_cuts': True,
            'outtmpl': output_path,
            'merge_output_format': 'mp4',
            'quiet': False,
            'no_warnings': True,
            'force_overwrites': True,
        }
    ]

    for idx, opts in enumerate(ydl_opts_list):
        try:
            print(f"[Downloader] Attempting download strategy #{idx+1}...")
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            if os.path.exists(output_path) and os.path.getsize(output_path) > 10000:
                print(f"[Downloader] Download succeeded with strategy #{idx+1}!")
                return output_path
        except Exception as e:
            print(f"[Downloader] Strategy #{idx+1} failed: {e}")

    raise RuntimeError(f"Failed to download clip section {start_seconds}-{end_seconds} for video {video_id}")

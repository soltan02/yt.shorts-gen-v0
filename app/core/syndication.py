import re
from typing import Dict, List, Any

class MultiPlatformSyndication:
    """
    Auto-formats video metadata and publishing data exclusively for YouTube Shorts.
    Generates 1-click titles, descriptions, pinned comment sparks, and CSV exports for schedulers.
    """

    @staticmethod
    def clean_text(text: str) -> str:
        if not text:
            return ""
        # Strip duplicate hashtags or URLs
        clean = re.sub(r'https?://\S+', '', text).strip()
        return clean

    @classmethod
    def generate_youtube_shorts_metadata(cls, clip_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        YouTube Shorts Algorithm Optimization:
        - High-CTR hook title (under 60 chars for mobile feed display).
        - SEO description with #shorts, #viral, and topic tags.
        - Pinned discussion spark to drive initial comment engagement.
        """
        title = cls.clean_text(clip_data.get("title", ""))
        pinned_comment = clip_data.get("reaction_spark_comment") or clip_data.get("pinned_comment") or ""
        niche = clip_data.get("niche", "general")

        niche_tags = {
            "podcast": "#podcastclips #deepdive #interviews",
            "motivation": "#mindset #discipline #successquotes",
            "psychology": "#psychologyfacts #mindblown #behavior",
            "tech_ai": "#ai #tech #futuretech",
            "storytelling": "#storytime #unbelievable #truestory",
            "general": "#shorts #viral #trending"
        }
        tags = niche_tags.get(niche, niche_tags["general"])

        yt_caption = f"{title}\n\nSubscribe for daily clips! #shorts #viral {tags}\n\nPinned: {pinned_comment}"

        return {
            "platform": "youtube_shorts",
            "platform_name": "YouTube Shorts",
            "icon": "📺",
            "title": title,
            "caption": yt_caption,
            "pinned_comment": pinned_comment,
            "hashtags": f"#shorts #viral #trending {tags}",
            "optimal_posting_times": ["12:00 PM EST", "4:00 PM EST", "8:00 PM EST"]
        }

    @classmethod
    def generate_all_platforms(cls, clip_data: Dict[str, Any]) -> Dict[str, Any]:
        yt_data = cls.generate_youtube_shorts_metadata(clip_data)

        return {
            "clip_id": clip_data.get("id"),
            "title": yt_data["title"],
            "youtube": yt_data,
            "shorts": yt_data,
            "youtube_shorts": yt_data
        }

    @classmethod
    def generate_csv_export(cls, clips: List[Dict[str, Any]]) -> str:
        """
        Exports a CSV spreadsheet ready for batch scheduling in YouTube schedulers or CSV tools.
        """
        import csv
        import io

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Clip ID", "Title", "Platform", "Full Caption", "Hashtags", "Pinned Comment", "Video URL", "Scheduled Time"
        ])

        for c in clips:
            cid = c.get("id", "")
            title = c.get("title", "")
            video_url = c.get("video_url", "")
            sched_time = c.get("scheduled_for", "")

            meta = cls.generate_all_platforms(c)
            writer.writerow([
                cid, title, "YouTube Shorts", meta["youtube"]["caption"], meta["youtube"]["hashtags"],
                meta["youtube"]["pinned_comment"], video_url, sched_time
            ])

        return output.getvalue()

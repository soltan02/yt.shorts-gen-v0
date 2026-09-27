import os
import sys
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

class AnalyticsTracker:
    """
    High-performance SQLite-backed Analytics & Clip Tracking engine.
    - Uses WAL (Write-Ahead Logging) mode and busy timeouts for thread-safe concurrency.
    - Automatically migrates existing records from database.json on initial launch with zero data loss.
    - Maintains a mirrored database.json snapshot for backward compatibility with external scripts.
    """
    def __init__(self, db_path: str):
        self.db_path = db_path
        dir_name = os.path.dirname(self.db_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        self.sqlite_path = os.path.join(dir_name or ".", "viral_clipper.db")
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS clips (
                id TEXT PRIMARY KEY,
                channel_id TEXT,
                title TEXT,
                status TEXT,
                views INTEGER DEFAULT 0,
                likes INTEGER DEFAULT 0,
                comments INTEGER DEFAULT 0,
                subs_gained INTEGER DEFAULT 0,
                scheduled_for TEXT,
                published_at TEXT,
                created_at TEXT,
                file_path TEXT,
                video_url TEXT,
                youtube_video_id TEXT,
                youtube_url TEXT,
                caption_style TEXT,
                data_json TEXT
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_clips_status ON clips(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_clips_channel ON clips(channel_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_clips_created ON clips(created_at DESC);")

            cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS channel_stats (
                channel_id TEXT PRIMARY KEY,
                stats_json TEXT,
                last_updated TEXT
            );
            """)
            # Seed essential defaults if not present
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_purge_on_publish', 'true');")
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('caption_art_direction', '\"dynamic_smart\"');")
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('audio_normalization', 'true');")
            conn.commit()

        # Migrate from JSON if SQLite table is empty
        self._migrate_from_json_if_needed()

    def _migrate_from_json_if_needed(self):
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT count(*) FROM clips;")
            count = cur.fetchone()[0]
            if count > 0:
                return

        if not os.path.exists(self.db_path):
            return

        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[Tracker] Error reading {self.db_path} for migration: {e}")
            return

        clips = data.get("clips", {})
        settings = data.get("settings", {})
        channel_stats = data.get("channel_stats", {})

        with self._get_conn() as conn:
            cur = conn.cursor()
            for cid, c in clips.items():
                cur.execute("""
                INSERT OR REPLACE INTO clips (
                    id, channel_id, title, status, views, likes, comments, subs_gained,
                    scheduled_for, published_at, created_at, file_path, video_url,
                    youtube_video_id, youtube_url, caption_style, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c.get('id', cid),
                    c.get('channel_id'),
                    c.get('title'),
                    c.get('status', 'rendered'),
                    c.get('views', 0),
                    c.get('likes', 0),
                    c.get('comments', 0),
                    c.get('subs_gained', 0),
                    c.get('scheduled_for'),
                    c.get('published_at'),
                    c.get('created_at'),
                    c.get('file_path'),
                    c.get('video_url'),
                    c.get('youtube_video_id'),
                    c.get('youtube_url'),
                    c.get('caption_style'),
                    json.dumps(c, ensure_ascii=False)
                ))

            for k, v in settings.items():
                val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, val_str))

            if channel_stats:
                cur.execute("INSERT OR REPLACE INTO channel_stats (channel_id, stats_json, last_updated) VALUES (?, ?, ?)",
                    ("default", json.dumps(channel_stats, ensure_ascii=False), channel_stats.get('last_updated'))
                )
            conn.commit()
            print(f"[Tracker] Migrated {len(clips)} clips into SQLite ({self.sqlite_path}).")

    def _sync_to_json_snapshot(self):
        """Export snapshot to database.json for compatibility."""
        try:
            full_db = self._read_db()
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(full_db, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Tracker] Error syncing JSON snapshot: {e}")

    def _read_db(self) -> Dict:
        """Reads all clips, settings, and channel stats from SQLite."""
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM clips;")
            rows = cur.fetchall()
            clips = {}
            for r in rows:
                c_data = {}
                if r["data_json"]:
                    try:
                        c_data = json.loads(r["data_json"])
                    except Exception:
                        pass
                c_data["id"] = r["id"]
                c_data["title"] = r["title"]
                c_data["channel_id"] = r["channel_id"]
                c_data["status"] = r["status"]
                c_data["views"] = r["views"]
                c_data["likes"] = r["likes"]
                c_data["comments"] = r["comments"]
                c_data["subs_gained"] = r["subs_gained"]
                c_data["scheduled_for"] = r["scheduled_for"]
                c_data["published_at"] = r["published_at"]
                c_data["created_at"] = r["created_at"]
                c_data["file_path"] = r["file_path"]
                c_data["video_url"] = r["video_url"]
                c_data["youtube_video_id"] = r["youtube_video_id"]
                c_data["youtube_url"] = r["youtube_url"]
                c_data["caption_style"] = r["caption_style"]
                clips[r["id"]] = c_data

            cur.execute("SELECT key, value FROM settings;")
            settings = {}
            for r in cur.fetchall():
                val = r["value"]
                try:
                    settings[r["key"]] = json.loads(val)
                except Exception:
                    settings[r["key"]] = val

            cur.execute("SELECT stats_json FROM channel_stats WHERE channel_id = 'default';")
            row = cur.fetchone()
            channel_stats = {
                "subscribers": 0,
                "total_views": 0,
                "shorts_views_90d": 0,
                "total_shorts_subs_gained": 0,
                "monetization_views_target": 10000000,
                "monetization_subs_target": 1000,
                "last_updated": None
            }
            if row and row["stats_json"]:
                try:
                    channel_stats.update(json.loads(row["stats_json"]))
                except Exception:
                    pass

            return {
                "clips": clips,
                "settings": settings,
                "channel_stats": channel_stats
            }

    def get_channel_stats(self, channel_id: str = "default") -> Dict:
        """
        Fast in-memory/SQLite retrieval of channel monetization & aggregate metrics.
        Calculates views, likes, and attributed subs STRICTLY from POSTED clips.
        Never blocks on external APIs, returning in < 1ms.
        """
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT stats_json FROM channel_stats WHERE channel_id = ?;", (channel_id,))
            row = cur.fetchone()
            if not row and channel_id != "default":
                cur.execute("SELECT stats_json FROM channel_stats WHERE channel_id = 'default';")
                row = cur.fetchone()
            
            stats = {
                "subscribers": 0,
                "total_views": 0,
                "shorts_views_90d": 0,
                "total_shorts_subs_gained": 0,
                "monetization_views_target": 10000000,
                "monetization_subs_target": 1000,
                "last_updated": None
            }
            if row and row["stats_json"]:
                try:
                    stats.update(json.loads(row["stats_json"]))
                except Exception:
                    pass

            # Always ensure subscribers & views are populated from connected channels if currently 0
            if stats.get("subscribers", 0) == 0:
                channels_file = os.path.join(os.path.dirname(self.db_path), "channels.json")
                if os.path.exists(channels_file):
                    try:
                        with open(channels_file, "r", encoding="utf-8") as f:
                            ch_dict = json.load(f)
                            ch_info = ch_dict.get(channel_id) or (list(ch_dict.values())[0] if ch_dict else None)
                            if ch_info and ch_info.get("subscribers"):
                                stats["subscribers"] = int(ch_info["subscribers"])
                                if not stats.get("total_views") and ch_info.get("views"):
                                    stats["total_views"] = int(ch_info["views"])
                    except Exception as e:
                        print(f"[Tracker] Error loading channels.json: {e}")

            # Recalculate shorts_views_90d and total_shorts_subs_gained
            # STRICTLY from posted/published clips (never scheduled!)
            cur.execute("""
                SELECT views, subs_gained FROM clips 
                WHERE status = 'published' AND (views > 0 OR likes > 0 OR youtube_video_id IS NOT NULL);
            """)
            published_rows = cur.fetchall()
            real_posted_views = sum(r["views"] or 0 for r in published_rows)
            real_posted_subs = sum(r["subs_gained"] or 0 for r in published_rows)
            
            stats["shorts_views_90d"] = real_posted_views
            stats["total_shorts_subs_gained"] = real_posted_subs
            return stats

    def _write_db(self, data: Dict):
        """Writes dictionary to SQLite and syncs JSON snapshot."""
        clips = data.get("clips", {})
        settings = data.get("settings", {})
        channel_stats = data.get("channel_stats", {})

        with self._get_conn() as conn:
            cur = conn.cursor()
            for cid, c in clips.items():
                cur.execute("""
                INSERT OR REPLACE INTO clips (
                    id, channel_id, title, status, views, likes, comments, subs_gained,
                    scheduled_for, published_at, created_at, file_path, video_url,
                    youtube_video_id, youtube_url, caption_style, data_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    c.get('id', cid),
                    c.get('channel_id'),
                    c.get('title'),
                    c.get('status', 'rendered'),
                    c.get('views', 0),
                    c.get('likes', 0),
                    c.get('comments', 0),
                    c.get('subs_gained', 0),
                    c.get('scheduled_for'),
                    c.get('published_at'),
                    c.get('created_at'),
                    c.get('file_path'),
                    c.get('video_url'),
                    c.get('youtube_video_id'),
                    c.get('youtube_url'),
                    c.get('caption_style'),
                    json.dumps(c, ensure_ascii=False)
                ))

            for k, v in settings.items():
                val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, val_str))

            if channel_stats:
                cur.execute("INSERT OR REPLACE INTO channel_stats (channel_id, stats_json, last_updated) VALUES (?, ?, ?)",
                    ("default", json.dumps(channel_stats, ensure_ascii=False), channel_stats.get('last_updated'))
                )
            conn.commit()

        self._sync_to_json_snapshot()

    def get_settings(self) -> Dict:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT key, value FROM settings;")
            settings = {}
            for r in cur.fetchall():
                val = r["value"]
                try: settings[r["key"]] = json.loads(val)
                except Exception: settings[r["key"]] = val
            return settings

    def update_settings(self, new_settings: Dict):
        with self._get_conn() as conn:
            cur = conn.cursor()
            for k, v in new_settings.items():
                val_str = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?);", (k, val_str))
            conn.commit()
        self._sync_to_json_snapshot()

    def get_active_channel_id(self) -> Optional[str]:
        return self.get_settings().get("active_channel_id")

    def set_active_channel_id(self, channel_id: str):
        self.update_settings({"active_channel_id": channel_id})

    def save_clip(self, clip: Dict) -> str:
        clip_id = clip.get("id") or str(uuid.uuid4())[:8]
        clip["id"] = clip_id
        clip.setdefault("created_at", datetime.now().isoformat())
        clip.setdefault("status", "rendered")
        clip.setdefault("views", 0)
        clip.setdefault("likes", 0)
        clip.setdefault("comments", 0)

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT OR REPLACE INTO clips (
                id, channel_id, title, status, views, likes, comments, subs_gained,
                scheduled_for, published_at, created_at, file_path, video_url,
                youtube_video_id, youtube_url, caption_style, data_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                clip_id,
                clip.get("channel_id"),
                clip.get("title"),
                clip.get("status"),
                clip.get("views", 0),
                clip.get("likes", 0),
                clip.get("comments", 0),
                clip.get("subs_gained", 0),
                clip.get("scheduled_for"),
                clip.get("published_at"),
                clip.get("created_at"),
                clip.get("file_path"),
                clip.get("video_url"),
                clip.get("youtube_video_id"),
                clip.get("youtube_url"),
                clip.get("caption_style"),
                json.dumps(clip, ensure_ascii=False)
            ))
            conn.commit()

        self._sync_to_json_snapshot()
        return clip_id

    def update_clip(self, clip_id: str, updates: Dict):
        clip = self.get_clip(clip_id)
        if not clip:
            return
        clip.update(updates)
        self.save_clip(clip)

    def get_clip(self, clip_id: str) -> Optional[Dict]:
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM clips WHERE id = ?;", (clip_id,))
            r = cur.fetchone()
            if not r:
                return None
            c = {}
            if r["data_json"]:
                try: c = json.loads(r["data_json"])
                except Exception: pass
            c.update({k: r[k] for k in r.keys() if k != "data_json"})
            return c

    def delete_clip(self, clip_id: str):
        self.delete_clips([clip_id])

    def delete_clips(self, clip_ids: List[str]):
        if not clip_ids:
            return
        placeholders = ",".join(["?"] * len(clip_ids))
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(f"DELETE FROM clips WHERE id IN ({placeholders});", clip_ids)
            conn.commit()
        self._sync_to_json_snapshot()

    def auto_reconcile_scheduled_clips(self) -> int:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        scheduled_clips = []
        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM clips WHERE status = 'scheduled';")
            for r in cur.fetchall():
                c = {}
                if r["data_json"]:
                    try: c = json.loads(r["data_json"])
                    except Exception: pass
                c.update({k: r[k] for k in r.keys() if k != "data_json"})
                scheduled_clips.append(c)

        reconciled_count = 0
        for clip in scheduled_clips:
            should_promote = False
            sched_for = clip.get("scheduled_for")
            if sched_for:
                try:
                    clean_iso = sched_for.replace("Z", "+00:00")
                    sched_dt = datetime.fromisoformat(clean_iso)
                    if sched_dt.tzinfo is not None:
                        sched_dt_utc = sched_dt.astimezone(timezone.utc).replace(tzinfo=None)
                    else:
                        sched_dt_utc = sched_dt
                    # Strictly promote only when the scheduled publish time has arrived
                    if sched_dt_utc <= now_utc:
                        should_promote = True
                except Exception as err:
                    print(f"[Tracker] Error parsing scheduled_for timestamp '{sched_for}' for {clip.get('id')}: {err}")

            if should_promote:
                cid = clip["id"]
                published_at = sched_for or now_utc.isoformat()
                self.update_clip(cid, {
                    "status": "published",
                    "published_at": published_at,
                    "auto_reconciled": True
                })
                reconciled_count += 1
                safe_title = (clip.get('title') or '').encode('ascii', 'replace').decode('ascii')
                print(f"[Tracker] Auto-reconciled scheduled clip '{safe_title}' ({cid}) -> status: published")

        return reconciled_count

    def get_all_clips(self, channel_id: Optional[str] = None) -> List[Dict]:
        self.auto_reconcile_scheduled_clips()
        with self._get_conn() as conn:
            cur = conn.cursor()
            if channel_id:
                cur.execute("SELECT * FROM clips WHERE channel_id = ? OR channel_id IS NULL ORDER BY created_at DESC;", (channel_id,))
            else:
                cur.execute("SELECT * FROM clips ORDER BY created_at DESC;")
            rows = cur.fetchall()

        clips = []
        for r in rows:
            c = {}
            if r["data_json"]:
                try: c = json.loads(r["data_json"])
                except Exception: pass
            c.update({k: r[k] for k in r.keys() if k != "data_json"})
            clips.append(c)
        return clips

    def get_clips_by_status(self, *statuses, channel_id: Optional[str] = None) -> List[Dict]:
        self.auto_reconcile_scheduled_clips()
        status_list = list(statuses)
        if "rendered" in status_list and "ready" not in status_list:
            status_list.append("ready")
        placeholders = ",".join(["?"] * len(status_list))
        query = f"SELECT * FROM clips WHERE status IN ({placeholders})"
        params = list(status_list)
        if channel_id:
            query += " AND (channel_id = ? OR channel_id IS NULL)"
            params.append(channel_id)
        query += " ORDER BY created_at DESC;"

        with self._get_conn() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()

        clips = []
        for r in rows:
            c = {}
            if r["data_json"]:
                try: c = json.loads(r["data_json"])
                except Exception: pass
            c.update({k: r[k] for k in r.keys() if k != "data_json"})
            if c.get("status") == "ready":
                c["status"] = "rendered"
            clips.append(c)
        return clips

    def fetch_public_video_stats(self, video_id: str) -> Optional[Dict]:
        """Fetch views and engagement for a public video via yt-dlp without requiring OAuth."""
        import subprocess
        try:
            cmd = ['yt-dlp', '--dump-single-json', '--no-warnings', f'https://www.youtube.com/watch?v={video_id}']
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
            if proc.returncode == 0 and proc.stdout:
                data = json.loads(proc.stdout)
                return {
                    "views": int(data.get("view_count") or 0),
                    "likes": int(data.get("like_count") or 0),
                    "comments": int(data.get("comment_count") or 0)
                }
        except Exception as e:
            print(f"[Tracker] yt-dlp public stats query error for {video_id}: {e}")
        return None

    def refresh_youtube_stats(self, uploader) -> Dict:
        """
        Query YouTube Data API (or yt-dlp fallback) to update views, likes, comments,
        and calculate subscriber conversion performance for all published clips.
        Automatically reconciles any scheduled clips whose publish time has arrived.
        """
        self.auto_reconcile_scheduled_clips()
        # Query ONLY genuinely published clips with valid YouTube IDs (never pending scheduled clips!)
        published_clips = [
            c for c in self.get_all_clips()
            if c.get("status") == "published" and c.get("youtube_video_id")
        ]

        # 1. Update Channel Stats via OAuth if authenticated
        channel_subscribers = 0
        channel_total_views = 0
        if uploader and uploader.is_authenticated():
            try:
                youtube = uploader.get_youtube_service()
                channel_res = youtube.channels().list(part="statistics", mine=True).execute()
                if channel_res.get("items"):
                    stats = channel_res["items"][0]["statistics"]
                    channel_subscribers = int(stats.get("subscriberCount", 0))
                    channel_total_views = int(stats.get("viewCount", 0))
            except Exception as e:
                print(f"[Tracker] Error updating channel stats: {e}")

        # If subscriberCount is 0 or failed, fallback to connected channels list
        if channel_subscribers == 0 and uploader:
            for ch in uploader.get_connected_channels():
                if ch.get("subscribers"):
                    channel_subscribers = int(ch["subscribers"])
                    if not channel_total_views and ch.get("views"):
                        channel_total_views = int(ch["views"])
                    break

        # 2. Update Published Clips Stats
        video_ids_map = {c.get("youtube_video_id"): c for c in published_clips if c.get("youtube_video_id")}
        updated_vids = set()

        if uploader and uploader.is_authenticated() and video_ids_map:
            try:
                youtube = uploader.get_youtube_service()
                all_ids = list(video_ids_map.keys())
                for i in range(0, len(all_ids), 50):
                    chunk = all_ids[i:i+50]
                    v_res = youtube.videos().list(part="statistics", id=",".join(chunk)).execute()
                    for item in v_res.get("items", []):
                        vid = item["id"]
                        v_stats = item["statistics"]
                        c = video_ids_map.get(vid)
                        if c:
                            views = int(v_stats.get("viewCount", 0))
                            likes = int(v_stats.get("likeCount", 0))
                            comments = int(v_stats.get("commentCount", 0))
                            subs_gained = max(0, round(views * 0.007 + likes * 0.035 + comments * 0.12))
                            eng_rate = round(((likes + comments * 2) / max(1, views)) * 100, 2)
                            tier = (
                                "🔥 VIRAL BREAKOUT" if views >= 10000 else
                                "⚡ STRONG RETENTION" if views >= 2000 else
                                "📈 STEADY GROWTH" if views >= 500 else
                                "🧪 TESTING"
                            )
                            c["views"] = views
                            c["likes"] = likes
                            c["comments"] = comments
                            c["subs_gained"] = subs_gained
                            c["engagement_rate"] = eng_rate
                            c["viral_tier"] = tier
                            self.save_clip(c)
                            updated_vids.add(vid)
            except Exception as e:
                print(f"[Tracker] Error updating clips via YouTube API: {e}")

        # Method B: Fallback for any videos not updated via API
        for vid, c in video_ids_map.items():
            if vid not in updated_vids:
                pub_stats = self.fetch_public_video_stats(vid)
                if pub_stats:
                    views = pub_stats["views"]
                    likes = pub_stats["likes"]
                    comments = pub_stats["comments"]
                    subs_gained = max(0, round(views * 0.007 + likes * 0.035 + comments * 0.12))
                    eng_rate = round(((likes + comments * 2) / max(1, views)) * 100, 2)
                    tier = (
                                "🔥 VIRAL BREAKOUT" if views >= 10000 else
                                "⚡ STRONG RETENTION" if views >= 2000 else
                                "📈 STEADY GROWTH" if views >= 500 else
                                "🧪 TESTING"
                    )
                    c["views"] = views
                    c["likes"] = likes
                    c["comments"] = comments
                    c["subs_gained"] = subs_gained
                    c["engagement_rate"] = eng_rate
                    c["viral_tier"] = tier
                    self.save_clip(c)

        # 3. Aggregate totals and save channel stats (STRICTLY from posted/published clips!)
        all_posted = [c for c in self.get_all_clips() if c.get("status") == "published"]
        total_short_views = sum(c.get("views", 0) for c in all_posted)
        total_subs_gained = sum(c.get("subs_gained", 0) for c in all_posted)

        channel_stats = {
            "subscribers": channel_subscribers,
            "total_views": channel_total_views,
            "shorts_views_90d": total_short_views,
            "total_shorts_subs_gained": total_subs_gained,
            "monetization_views_target": 10000000,
            "monetization_subs_target": 1000,
            "last_updated": datetime.now().isoformat()
        }

        active_id = self.get_active_channel_id() or "default"
        with self._get_conn() as conn:
            cur = conn.cursor()
            for cid in set([active_id, "default"]):
                cur.execute("""
                INSERT OR REPLACE INTO channel_stats (channel_id, stats_json, last_updated)
                VALUES (?, ?, ?);
                """, (cid, json.dumps(channel_stats, ensure_ascii=False), channel_stats["last_updated"]))
            conn.commit()

        self._sync_to_json_snapshot()
        return channel_stats


if getattr(sys, 'frozen', False):
    _DEFAULT_APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    _DEFAULT_APP_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_APP_DIR, "storage", "database.json")
tracker = AnalyticsTracker(_DEFAULT_DB_PATH)

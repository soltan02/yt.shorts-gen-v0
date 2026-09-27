import os
import json
from typing import Dict, List, Optional
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.readonly'
]

class YouTubeUploader:
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self.tokens_dir = os.path.join(storage_dir, "tokens")
        self.channels_path = os.path.join(storage_dir, "channels.json")
        self.legacy_token_path = os.path.join(storage_dir, "token.json")
        os.makedirs(self.tokens_dir, exist_ok=True)
        self._init_channels()

    def _init_channels(self):
        if not os.path.exists(self.channels_path):
            with open(self.channels_path, "w", encoding="utf-8") as f:
                json.dump({}, f)

    def get_client_secret_path(self) -> Optional[str]:
        standard = os.path.join(self.storage_dir, "client_secret.json")
        if os.path.exists(standard) and os.path.getsize(standard) > 10:
            return standard
        double_ext = os.path.join(self.storage_dir, "client_secret.json.json")
        if os.path.exists(double_ext) and os.path.getsize(double_ext) > 10:
            return double_ext
        for f in os.listdir(self.storage_dir):
            if f.startswith("client_secret") and f.endswith(".json"):
                full = os.path.join(self.storage_dir, f)
                if os.path.getsize(full) > 10:
                    return full
        return None

    def has_client_secrets(self) -> bool:
        return self.get_client_secret_path() is not None

    def _read_channels(self) -> Dict[str, Dict]:
        try:
            with open(self.channels_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _write_channels(self, data: Dict[str, Dict]):
        with open(self.channels_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def get_connected_channels(self) -> List[Dict]:
        """Return list of all connected YouTube channels."""
        channels = list(self._read_channels().values())
        # Check if legacy token exists and not in channels
        if not channels and os.path.exists(self.legacy_token_path):
            try:
                creds = Credentials.from_authorized_user_file(self.legacy_token_path, SCOPES)
                if creds and creds.valid:
                    return [{
                        "channel_id": "primary",
                        "title": "Connected YouTube Channel",
                        "subscribers": 0,
                        "views": 0,
                        "thumbnail": "",
                        "token_file": self.legacy_token_path
                    }]
            except Exception:
                pass
        return channels

    def is_authenticated(self) -> bool:
        channels = self.get_connected_channels()
        if channels:
            return True
        return os.path.exists(self.legacy_token_path)

    def get_auth_flow(self, redirect_uri: str = "http://localhost:5001/oauth2callback") -> InstalledAppFlow:
        path = self.get_client_secret_path()
        if not path:
            raise FileNotFoundError("Missing client_secret.json in storage folder.")
        flow = InstalledAppFlow.from_client_secrets_file(
            path, 
            SCOPES,
            redirect_uri=redirect_uri
        )
        return flow

    def register_channel_from_credentials(self, creds: Credentials) -> Dict:
        """Fetch channel metadata from credentials and register it."""
        service = build('youtube', 'v3', credentials=creds)
        res = service.channels().list(part="snippet,statistics", mine=True).execute()

        if not res.get("items"):
            raise ValueError("No YouTube channel found for this Google account.")

        item = res["items"][0]
        channel_id = item["id"]
        snippet = item.get("snippet", {})
        stats = item.get("statistics", {})

        token_file = os.path.join(self.tokens_dir, f"{channel_id}.json")
        with open(token_file, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        # Also write legacy token for backwards compatibility
        with open(self.legacy_token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        channel_info = {
            "channel_id": channel_id,
            "title": snippet.get("title", "Untitled Channel"),
            "description": snippet.get("description", "")[:200],
            "custom_url": snippet.get("customUrl", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("default", {}).get("url", ""),
            "subscribers": int(stats.get("subscriberCount", 0)),
            "views": int(stats.get("viewCount", 0)),
            "video_count": int(stats.get("videoCount", 0)),
            "token_file": token_file
        }

        channels = self._read_channels()
        channels[channel_id] = channel_info
        self._write_channels(channels)

        return channel_info

    def remove_channel(self, channel_id: str):
        channels = self._read_channels()
        if channel_id in channels:
            token_file = channels[channel_id].get("token_file")
            if token_file and os.path.exists(token_file):
                try:
                    os.remove(token_file)
                except Exception:
                    pass
            del channels[channel_id]
            self._write_channels(channels)

    def get_youtube_service(self, channel_id: Optional[str] = None):
        """Build service for specific channel, or default to first connected channel."""
        channels = self._read_channels()
        token_path = None

        if channel_id and channel_id in channels:
            token_path = channels[channel_id].get("token_file")
        elif channels:
            # First channel
            first_key = list(channels.keys())[0]
            token_path = channels[first_key].get("token_file")
        elif os.path.exists(self.legacy_token_path):
            token_path = self.legacy_token_path

        if not token_path or not os.path.exists(token_path):
            raise RuntimeError("YouTube account is not authenticated. Please connect your channel first.")

        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, 'w', encoding='utf-8') as token:
                token.write(creds.to_json())

        return build('youtube', 'v3', credentials=creds)

    def upload_short(
        self,
        video_file_path: str,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        privacy_status: str = "private",
        publish_at: Optional[str] = None,
        channel_id: Optional[str] = None,
        thumbnail_path: Optional[str] = None
    ) -> Dict:
        """
        Upload video directly to YouTube as a Short to the specified channel,
        with optional custom thumbnail.
        """
        if not os.path.exists(video_file_path):
            raise FileNotFoundError(f"Video file not found: {video_file_path}")

        youtube = self.get_youtube_service(channel_id=channel_id)

        # Ensure #shorts is in title or description for Shorts feed recognition
        if "#shorts" not in title.lower() and "#shorts" not in description.lower():
            title = f"{title} #shorts"

        body = {
            'snippet': {
                'title': title[:100],
                'description': description,
                'tags': tags or ['shorts', 'viral', 'podcast'],
                'categoryId': '24'  # Entertainment
            },
            'status': {
                'privacyStatus': 'private' if publish_at else privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }

        if publish_at:
            body['status']['publishAt'] = publish_at

        media = MediaFileUpload(
            video_file_path, 
            mimetype='video/mp4', 
            resumable=True, 
            chunksize=1024*1024*2
        )

        request = youtube.videos().insert(
            part=','.join(body.keys()),
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print(f"[YouTube Upload] Uploaded {int(status.progress() * 100)}%")

        video_id = response.get('id')

        # Upload custom thumbnail if available
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                print(f"[YouTube Upload] Setting custom thumbnail for {video_id}...")
                thumb_media = MediaFileUpload(thumbnail_path, mimetype='image/jpeg')
                youtube.thumbnails().set(
                    videoId=video_id,
                    media_body=thumb_media
                ).execute()
                print(f"[YouTube Upload] Thumbnail set successfully!")
            except Exception as e:
                print(f"[YouTube Upload] Note: Custom thumbnail could not be set automatically ({e}). Channel may need phone verification for custom thumbnails.")

        return {
            "video_id": video_id,
            "url": f"https://www.youtube.com/shorts/{video_id}",
            "title": title,
            "channel_id": channel_id,
            "publish_at": publish_at,
            "privacy_status": privacy_status
        }

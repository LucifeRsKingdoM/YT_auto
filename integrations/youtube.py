"""YouTube integration: OAuth 2.0, resumable video upload, and analytics.

Token handling:
  - The OAuth refresh token (as JSON) is stored Fernet-encrypted in the
    integrations table under the key "yt_token".
  - get_credentials() loads it and auto-refreshes when expired.
"""
import json

import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

from config import config
from integrations.store import (
    get_value, set_value, yt_client_id, yt_client_secret, yt_default_privacy,
)

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def _client_config():
    return {
        "web": {
            "client_id": yt_client_id(),
            "client_secret": yt_client_secret(),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [config.YT_REDIRECT_URI],
        }
    }


# ---- OAuth flow ---------------------------------------------------------
def build_auth_url():
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        _client_config(), scopes=SCOPES
    )
    flow.redirect_uri = config.YT_REDIRECT_URI
    auth_url, _state = flow.authorization_url(
        access_type="offline", include_granted_scopes="true", prompt="consent"
    )
    return auth_url


def handle_callback(full_redirect_url):
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        _client_config(), scopes=SCOPES
    )
    flow.redirect_uri = config.YT_REDIRECT_URI
    flow.fetch_token(authorization_response=full_redirect_url)
    creds = flow.credentials
    set_value("yt_token", _creds_to_json(creds))
    return True


def _creds_to_json(creds):
    return json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    })


def get_credentials():
    raw = get_value("yt_token", "")
    if not raw:
        return None
    data = json.loads(raw)
    creds = google.oauth2.credentials.Credentials(**data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        set_value("yt_token", _creds_to_json(creds))
    return creds


def is_connected():
    return bool(get_value("yt_token", ""))


# ---- Upload -------------------------------------------------------------
def upload_video(video, file_path):
    """Upload a local file to YouTube. Returns the new video id.

    Raises on failure so the caller can log it.
    """
    creds = get_credentials()
    if creds is None:
        raise RuntimeError("YouTube is not connected. Authorize it first on the Integrations page.")

    youtube = build("youtube", "v3", credentials=creds)

    privacy = (video.privacy or yt_default_privacy() or "private").lower()
    tags = [t.strip() for t in (video.tags or "").split(",") if t.strip()]

    body = {
        "snippet": {
            "title": video.title,
            "description": video.description or "",
            "tags": tags,
            "categoryId": video.category_id or "22",
        },
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }

    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    response = None
    while response is None:
        _status, response = request.next_chunk()
    return response["id"]


# ---- Analytics ----------------------------------------------------------
def fetch_video_statistics(video_ids):
    """Basic counts (views/likes/comments) via the Data API. 1 unit total."""
    creds = get_credentials()
    if creds is None or not video_ids:
        return {}
    youtube = build("youtube", "v3", credentials=creds)
    out = {}
    # Data API accepts up to 50 ids per call
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i + 50]
        resp = youtube.videos().list(
            part="statistics", id=",".join(chunk)
        ).execute()
        for item in resp.get("items", []):
            st = item.get("statistics", {})
            out[item["id"]] = {
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            }
    return out


def fetch_analytics(start_date, end_date):
    """Channel time-series from the YouTube Analytics API.

    start_date / end_date are 'YYYY-MM-DD' strings. Returns rows of
    [day, views, estimatedMinutesWatched, likes, comments].
    Note: YouTube analytics data lags several hours to ~a day; this is
    near-real-time, not instantaneous.
    """
    creds = get_credentials()
    if creds is None:
        return {"columnHeaders": [], "rows": []}
    yta = build("youtubeAnalytics", "v2", credentials=creds)
    resp = yta.reports().query(
        ids="channel==MINE",
        startDate=start_date,
        endDate=end_date,
        metrics="views,estimatedMinutesWatched,likes,comments",
        dimensions="day",
        sort="day",
    ).execute()
    return resp

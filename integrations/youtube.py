"""YouTube integration: OAuth 2.0, resumable video upload, and analytics.

Multi-slot token handling:
  - Supports 5 independent YouTube channel slots per admin user.
  - Credentials are stored securely in the youtube_accounts table.
"""
import json
import google.oauth2.credentials
import google_auth_oauthlib.flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request

from config import config
from database import get_session
from models import YouTubeAccount
from integrations.store import (
    yt_client_id, yt_client_secret, yt_default_privacy,
)

import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Allows local http:// development

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


def handle_callback(full_redirect_url, username, slot_number):
    flow = google_auth_oauthlib.flow.Flow.from_client_config(
        _client_config(), scopes=SCOPES
    )
    flow.redirect_uri = config.YT_REDIRECT_URI
    flow.fetch_token(authorization_response=full_redirect_url)
    creds = flow.credentials

    # Build a temporary client to fetch the real channel name
    youtube_client = build('youtube', 'v3', credentials=creds)
    channel_response = youtube_client.channels().list(mine=True, part='snippet').execute()
    
    channel_title = "Connected Channel"
    if channel_response.get('items'):
        channel_title = channel_response['items'][0]['snippet']['title']

    cred_json = json.dumps({
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": creds.scopes,
    })

    # Save or update the slot in the database securely
    session = get_session()
    try:
        account = session.query(YouTubeAccount).filter_by(
            owner_username=username, slot_number=slot_number
        ).first()

        if account:
            account.channel_name = channel_title
            account.credentials = cred_json
        else:
            account = YouTubeAccount(
                owner_username=username,
                slot_number=slot_number,
                channel_name=channel_title,
                credentials=cred_json
            )
            session.add(account)
        session.commit()
    finally:
        session.close()
    return True


def get_credentials_from_text(raw_creds_text):
    if not raw_creds_text:
        return None
    data = json.loads(raw_creds_text)
    creds = google.oauth2.credentials.Credentials(**data)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


# ---- Upload -------------------------------------------------------------
def upload_video(video, file_path, raw_creds_text):
    """Upload a local file to a specific channel using its credential string."""
    creds = get_credentials_from_text(raw_creds_text)
    if creds is None:
        raise RuntimeError("YouTube account credentials for this slot are invalid or missing.")

    youtube = build("youtube", "v3", credentials=creds)

    privacy = (video.privacy or yt_default_privacy() or "private").lower()
    tags = [t.strip() for t in (video.tags or "").split(",") if t.strip()]

    body = {
        "snippet": {
            "title": video.title,
            "description": video.description or "",
            "tags": tags,
            "category_id": video.category_id or "22",
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
def fetch_video_statistics(video_ids, raw_creds_text):
    creds = get_credentials_from_text(raw_creds_text)
    if creds is None or not video_ids:
        return {}
    youtube = build("youtube", "v3", credentials=creds)
    out = {}
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


def is_connected():
    # Returns true if at least one slot has credentials
    session = get_session()
    try:
        count = session.query(YouTubeAccount).count()
        return count > 0
    finally:
        session.close()
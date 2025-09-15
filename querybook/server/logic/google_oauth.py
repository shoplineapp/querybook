from datetime import datetime, timedelta
from typing import Optional, Dict

from app.db import with_session
from models.google_oauth import GoogleOAuthToken
from env import QuerybookSettings


@with_session
def get_google_oauth_token(uid: int, session=None) -> Optional[GoogleOAuthToken]:
    """Get Google OAuth token for a user"""
    return session.query(GoogleOAuthToken).filter(GoogleOAuthToken.uid == uid).first()


@with_session
def create_or_update_google_oauth_token(
    uid: int,
    access_token: str,
    refresh_token: str = None,
    expires_in: int = 3600,
    scope: str = None,
    session=None
) -> GoogleOAuthToken:
    """Create or update Google OAuth token for a user"""

    # Calculate expiration time
    expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

    # Check if token already exists
    oauth_token = session.query(GoogleOAuthToken).filter(GoogleOAuthToken.uid == uid).first()

    if oauth_token:
        # Update existing token
        oauth_token.access_token = access_token
        if refresh_token:
            oauth_token.refresh_token = refresh_token
        oauth_token.expires_at = expires_at
        if scope:
            oauth_token.scope = scope
        oauth_token.updated_at = datetime.utcnow()
    else:
        # Create new token
        oauth_token = GoogleOAuthToken(
            uid=uid,
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
            scope=scope
        )
        session.add(oauth_token)

    session.commit()
    return oauth_token


@with_session
def delete_google_oauth_token(uid: int, session=None) -> bool:
    """Delete Google OAuth token for a user"""
    oauth_token = session.query(GoogleOAuthToken).filter(GoogleOAuthToken.uid == uid).first()
    if oauth_token:
        session.delete(oauth_token)
        session.commit()
        return True
    return False


def get_google_credentials_for_user(uid: int) -> Optional[Dict]:
    """Get Google credentials dict for BigQuery client"""
    print(f"DEBUG: Looking for OAuth token for user {uid}")
    oauth_token = get_google_oauth_token(uid)

    if not oauth_token:
        print(f"DEBUG: No OAuth token found for user {uid}")
        return None

    print(f"DEBUG: Found OAuth token for user {uid}, token exists: {bool(oauth_token.access_token)}")
    credentials_dict = oauth_token.get_credentials_dict()
    credentials_dict.update({
        "client_id": QuerybookSettings.OAUTH_CLIENT_ID,
        "client_secret": QuerybookSettings.OAUTH_CLIENT_SECRET,
    })

    return credentials_dict


def refresh_google_token_if_needed(uid: int) -> Optional[GoogleOAuthToken]:
    """Refresh Google token if it's expired or about to expire"""
    oauth_token = get_google_oauth_token(uid)

    if not oauth_token or not oauth_token.refresh_token:
        return oauth_token

    # Check if token expires within 5 minutes
    if oauth_token.expires_at and (oauth_token.expires_at - datetime.utcnow()).total_seconds() < 300:
        try:
            import requests
            from env import QuerybookSettings

            # Refresh the token
            response = requests.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "client_id": QuerybookSettings.OAUTH_CLIENT_ID,
                    "client_secret": QuerybookSettings.OAUTH_CLIENT_SECRET,
                    "refresh_token": oauth_token.refresh_token,
                    "grant_type": "refresh_token",
                }
            )

            if response.status_code == 200:
                token_data = response.json()
                return create_or_update_google_oauth_token(
                    uid=uid,
                    access_token=token_data["access_token"],
                    refresh_token=oauth_token.refresh_token,  # Keep existing refresh token
                    expires_in=token_data.get("expires_in", 3600),
                    scope=oauth_token.scope
                )
        except Exception:
            # If refresh fails, return the existing token and let the BigQuery client handle it
            pass

    return oauth_token
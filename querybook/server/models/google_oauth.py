import sqlalchemy as sql
from sqlalchemy.orm import relationship

from app import db
from const.db import now
from lib.sqlalchemy import CRUDMixin


Base = db.Base


class GoogleOAuthToken(CRUDMixin, Base):
    __tablename__ = "google_oauth_token"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id = sql.Column(sql.Integer, primary_key=True)
    uid = sql.Column(sql.Integer, sql.ForeignKey("user.id", ondelete="CASCADE"), unique=True)

    access_token = sql.Column(sql.Text, nullable=False)
    refresh_token = sql.Column(sql.Text)
    token_type = sql.Column(sql.String(50), default="Bearer")
    expires_at = sql.Column(sql.DateTime)
    scope = sql.Column(sql.Text)

    created_at = sql.Column(sql.DateTime, default=now)
    updated_at = sql.Column(sql.DateTime, default=now, onupdate=now)

    # Relationship to User
    user = relationship("User", backref="google_oauth_token")

    def to_dict(self):
        return {
            "id": self.id,
            "uid": self.uid,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "scope": self.scope,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def is_token_expired(self):
        """Check if the access token is expired"""
        if not self.expires_at:
            return False
        from datetime import datetime
        return datetime.utcnow() > self.expires_at

    def get_credentials_dict(self):
        """Get credentials in format suitable for Google OAuth2 library"""
        return {
            "token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": None,  # Will be filled from settings
            "client_secret": None,  # Will be filled from settings
            "scopes": self.scope.split(",") if self.scope else [],
        }
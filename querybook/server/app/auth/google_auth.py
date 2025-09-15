from flask import Markup, request, session as flask_session, redirect
import flask_login
from app.db import DBSession
from app.auth.oauth_auth import OAuthLoginManager, OAUTH_CALLBACK_PATH
from app.auth.utils import AuthenticationError, AuthUser, abort_unauthorized
from env import QuerybookSettings
from clients.google_client import get_google_oauth_config
from logic.google_oauth import create_or_update_google_oauth_token
from lib.logger import get_logger

LOG = get_logger(__file__)

class GoogleLoginManager(OAuthLoginManager):
    @property
    def oauth_config(self):
        google_config = get_google_oauth_config()

        return {
            "callback_url": "{}{}".format(
                QuerybookSettings.PUBLIC_URL, OAUTH_CALLBACK_PATH
            ),
            "client_id": QuerybookSettings.OAUTH_CLIENT_ID,
            "client_secret": QuerybookSettings.OAUTH_CLIENT_SECRET,
            "authorization_url": google_config["authorization_endpoint"],
            "token_url": google_config["token_endpoint"],
            "profile_url": google_config["userinfo_endpoint"],
            "scope": [
                "https://www.googleapis.com/auth/userinfo.email",
                "openid",
                "https://www.googleapis.com/auth/userinfo.profile",
                "https://www.googleapis.com/auth/bigquery",
            ],
        }
    
    def _parse_user_profile(self, resp):
        user = resp.json()
        username = user["email"].split("@")[0]
        return username, user["email"]
    
    def _get_authn_url(self):
        return self.oauth_session.authorization_url(
            self.oauth_config["authorization_url"],
            access_type="offline",
            prompt="consent"
        )

    def _fetch_access_token(self, code):
        resp = self.oauth_session.fetch_token(
            token_url=self.oauth_config["token_url"],
            client_id=self.oauth_config["client_id"],
            code=code,
            client_secret=self.oauth_config["client_secret"],
        )
        if resp is None:
            raise AuthenticationError("Null response, denying access.")
        # Return the full response instead of just access_token
        return resp

    def oauth_callback(self):
        LOG.debug("Handling Google OAuth callback...")

        if request.args.get("error"):
            return f"<h1>Error: {Markup.escape(request.args.get('error'))}</h1>"

        code = request.args.get("code")
        try:
            # Fetch the full token response
            token_resp = self._fetch_access_token(code)
            access_token = token_resp["access_token"]

            # Get user profile
            username, email = self._get_user_profile(access_token)

            with DBSession() as session:
                # Create or login user
                user = self.login_user(username, email, session=session)

                # Store Google OAuth tokens
                create_or_update_google_oauth_token(
                    uid=user.id,
                    access_token=access_token,
                    refresh_token=token_resp.get("refresh_token"),
                    expires_in=token_resp.get("expires_in", 3600),
                    scope=",".join(self.oauth_config["scope"]),
                    session=session
                )

                # Login the user
                flask_login.login_user(AuthUser(user))

        except AuthenticationError as e:
            LOG.error("Failed authenticate oauth user", e)
            abort_unauthorized()

        next_url = QuerybookSettings.PUBLIC_URL
        if "next" in flask_session:
            next_url = flask_session["next"]
            del flask_session["next"]

        return redirect(next_url)


login_manager = GoogleLoginManager()

ignore_paths = [OAUTH_CALLBACK_PATH]


def init_app(app):
    login_manager.init_app(app)


def login(request):
    return login_manager.login(request)


def oauth_authorization_url():
    return login_manager._get_authn_url()

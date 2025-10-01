from clients.google_client import get_google_credentials
from lib.query_executor.base_client import ClientBaseClass, CursorBaseClass
from lib.utils.json import safe_loads
from google.oauth2.credentials import Credentials
from google.cloud.bigquery import Client


class BigQueryClient(ClientBaseClass):
    def __init__(self, auth_method="service_account", project_id=None, google_credentials_json=None, user_oauth_credentials=None, *args, **kwargs):
        from google.cloud.bigquery import dbapi, Client

        if auth_method == "google_sso" and user_oauth_credentials:
            try:
                # Create OAuth2 credentials from user tokens
                cred = Credentials(
                    token=user_oauth_credentials["token"],
                    refresh_token=user_oauth_credentials.get("refresh_token"),
                    token_uri=user_oauth_credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
                    client_id=user_oauth_credentials.get("client_id"),
                    client_secret=user_oauth_credentials.get("client_secret"),
                    scopes=user_oauth_credentials.get("scopes", [])
                )

                # Use project_id from configuration
                if not project_id:
                    raise ValueError("project_id is required when using Google SSO authentication")

                client = Client(credentials=cred, project=project_id)
                
            except Exception as e:
                if auth_method == "google_sso":
                    # Don't fallback to service account if explicitly configured for SSO
                    raise ValueError(f"Google SSO authentication failed: {e}")
                else:
                    # Fallback to service account
                    client = self._create_service_account_client(google_credentials_json, project_id)

        else:
            client = self._create_service_account_client(google_credentials_json, project_id)

        self._conn = dbapi.connect(client=client)
        super(BigQueryClient, self).__init__()

    def _create_service_account_client(self, google_credentials_json, project_id=None):
        parsed_google_json = (
            safe_loads(google_credentials_json)
            if google_credentials_json is not None
            else None
        )
        if parsed_google_json is not None:
            cred = get_google_credentials(parsed_google_json)
            # Use project_id from config if provided, otherwise use the one from credentials
            final_project_id = project_id or cred.project_id
            return Client(project=final_project_id, credentials=cred)
        else:
            raise ValueError(
                "No BigQuery credentials found. Please:\n"
                "1. Set auth_method to 'google_sso' and log in with Google OAuth, or\n"
                "2. Set auth_method to 'service_account' and provide 'google_credentials_json' parameter"
            )

    def cursor(self) -> CursorBaseClass:
        return BigQueryCursor(cursor=self._conn.cursor())


class BigQueryCursor(CursorBaseClass):
    def __init__(self, cursor):
        self._cursor = cursor

    def run(self, query):
        self._cursor.execute(query)

        # Caching the first row to allow column names
        self._first_row = self._cursor.fetchone()
        self._should_send_first_row = True

    def cancel(self):
        # Can't cancel (yet)
        pass

    def poll(self):
        # Query should immediately start to block after
        # run, so when it gets to poll it is already
        # finished
        return True

    def get_one_row(self):
        if self._should_send_first_row:
            self._should_send_first_row = False
            return self._convert_row(self._first_row)

        return self._convert_row(self._cursor.fetchone())

    def get_n_rows(self, n: int):
        def _fetch_k_rows(k: int):
            return [self._convert_row(row) for row in self._cursor.fetchmany(size=k)]

        if self._should_send_first_row:
            self._should_send_first_row = False
            return [self._convert_row(self._first_row)] + _fetch_k_rows(n - 1)
        return _fetch_k_rows(n)

    def get_columns(self):
        if not self._first_row:
            return None
        return list(self._first_row.keys())

    def _convert_row(self, row):
        if row:
            return list(row.values())
        return None

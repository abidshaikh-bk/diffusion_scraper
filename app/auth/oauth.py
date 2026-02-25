from __future__ import annotations

from pathlib import Path
from typing import Sequence

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow


def get_credentials(
    scopes: Sequence[str],
    client_secret_path: str = "secrets/client_secret.json",
    token_path: str = "secrets/token.json",
) -> Credentials:
    """
    OAuth user credentials for installed app.
    - First run opens a browser to authorize.
    - Subsequent runs use refresh token from token.json.
    """
    client_secret = Path(client_secret_path)
    token_file = Path(token_path)

    if not client_secret.exists():
        raise FileNotFoundError(
            f"Missing OAuth client secrets: {client_secret.resolve()}"
        )

    creds: Credentials | None = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), scopes=scopes)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secret), scopes=scopes
            )
            creds = flow.run_local_server(port=0)

        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(creds.to_json())

    return creds
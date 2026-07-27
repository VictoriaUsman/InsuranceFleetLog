import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.environ.get("DATABASE_URL", "")

    argyle_api_token: str = os.environ.get("ARGYLE_API_TOKEN", "")
    argyle_api_secret: str = os.environ.get("ARGYLE_API_SECRET", "")
    argyle_env: str = os.environ.get("ARGYLE_ENV", "sandbox")
    argyle_webhook_secret: str = os.environ.get("ARGYLE_WEBHOOK_SECRET", "")

    ghl_api_key: str = os.environ.get("GHL_API_KEY", "")

    fleet_timezone: str = os.environ.get("FLEET_TIMEZONE", "America/New_York")

    @property
    def argyle_base_url(self) -> str:
        return (
            "https://api.argyle.com"
            if self.argyle_env == "production"
            else "https://api-sandbox.argyle.com"
        )


settings = Settings()

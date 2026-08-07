import certifi
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mongodb_uri: str
    voyage_api_key: str
    postmark_webhook_token: str = ""
    postmark_server_token: str = ""
    digest_email_sender: str = ""
    digest_email_recipients: str = ""
    anthropic_api_key: str
    harmonic_api_key: str = ""
    slack_bot_token: str = ""
    slack_signing_secret: str = ""

    @property
    def mongodb_uri_with_tls(self) -> str:
        if "tlsCAFile" in self.mongodb_uri:
            return self.mongodb_uri
        sep = "&" if "?" in self.mongodb_uri else "?"
        return f"{self.mongodb_uri}{sep}tlsCAFile={certifi.where()}"

    @property
    def digest_email_recipient_list(self) -> list[str]:
        return [addr.strip() for addr in self.digest_email_recipients.split(",") if addr.strip()]


settings = Settings()

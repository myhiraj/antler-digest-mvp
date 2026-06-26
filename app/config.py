import certifi
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mongodb_uri: str
    voyage_api_key: str
    postmark_webhook_token: str = ""
    anthropic_api_key: str

    @property
    def mongodb_uri_with_tls(self) -> str:
        if "tlsCAFile" in self.mongodb_uri:
            return self.mongodb_uri
        sep = "&" if "?" in self.mongodb_uri else "?"
        return f"{self.mongodb_uri}{sep}tlsCAFile={certifi.where()}"


settings = Settings()

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongodb_uri: str
    voyage_api_key: str
    postmark_webhook_token: str

    class Config:
        env_file = ".env"


settings = Settings()

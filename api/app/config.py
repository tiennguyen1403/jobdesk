from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "JobDesk API"
    database_url: str = "postgresql+psycopg://jobdesk:jobdesk@db:5432/jobdesk"
    cors_origins: str = "http://localhost:5173"

    # Phase 2
    anthropic_api_key: str | None = None
    # Phase 3
    upwork_client_id: str | None = None
    upwork_client_secret: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

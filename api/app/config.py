from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "JobDesk API"
    database_url: str = "postgresql+psycopg://jobdesk:jobdesk@db:5432/jobdesk"
    # Comma-separated allowed origins. Includes https://www.upwork.com so the
    # capture bookmarklet (docs/capture-bookmarklet.md) can POST a scraped job
    # from an Upwork page. Override via CORS_ORIGINS in .env.
    cors_origins: str = "http://localhost:5173,https://www.upwork.com"

    # Phase 2 — AI layer (Claude via the Anthropic Messages API)
    anthropic_api_key: str | None = None
    # Default to the most capable model; override with ANTHROPIC_MODEL if needed.
    anthropic_model: str = "claude-opus-5"
    # Ceiling on generated tokens per call (a cap, not a charge). Callers may override.
    anthropic_max_tokens: int = 4096
    # Phase 3 — Upwork OAuth2 connector
    upwork_client_id: str | None = None
    upwork_client_secret: str | None = None
    # OAuth2 redirect (callback) URI. Must match EXACTLY the value registered on
    # your Upwork app and the API's public URL (host + API_PORT). Defaults to the
    # example API_PORT (8000); override to match your port (this machine: 8001).
    upwork_redirect_uri: str = "http://localhost:8000/api/upwork/callback"
    # Optional OAuth2 scopes (space-separated). Upwork grants the permissions set
    # on the app, so this is normally empty; when set, it is added to the authorize
    # URL, otherwise the scope parameter is omitted.
    upwork_scope: str = ""

    # Phase 3 — polling scheduler (in-process APScheduler, app.scheduler).
    # Off by default: without a stored Upwork token the poll is a logged no-op, and
    # POST /api/saved-searches/{id}/run covers testing, so a background loop only
    # runs when explicitly enabled. Flip POLL_ENABLED=true once Upwork is connected.
    poll_enabled: bool = False
    # Minutes between poll cycles (each iterates the enabled saved searches). Kept
    # gentle — Upwork has no webhooks, but polling need not be aggressive.
    poll_interval_minutes: int = 15

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

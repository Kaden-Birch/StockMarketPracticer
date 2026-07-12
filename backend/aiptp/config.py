from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIPTP_")

    data_dir: Path = Path("data")
    db_url: str = ""  # derived from data_dir when empty
    host: str = "127.0.0.1"
    port: int = 8420
    # Ordered failover chain; comma-separated: yahoo | stooq | alphavantage | fake
    market_providers: str = "yahoo,stooq"
    alphavantage_key: str = ""
    watch_interval_seconds: int = 15
    quote_ttl_seconds: int = 15
    history_ttl_seconds: int = 600

    def resolved_db_url(self) -> str:
        if self.db_url:
            return self.db_url
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.data_dir / 'aiptp.db'}"


settings = Settings()

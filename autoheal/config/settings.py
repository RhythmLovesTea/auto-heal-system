from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # --- Polling ---
    poll_interval: int = 30          # seconds between heal scans
    heal_cooldown: int = 60          # seconds before re-healing the same container

    # --- Docker ---
    docker_socket: str = "unix://var/run/docker.sock"
    container_filter: list[str] = [] # empty = watch all; e.g. ["payments-api", "worker"]

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    redis_ttl: int = 86400           # incident log retention in seconds (24 h)

    # --- Logging ---
    log_level: str = "INFO"          # DEBUG | INFO | WARNING | ERROR
    log_json: bool = False           # True = structured JSON logs


# Single import-time instance used everywhere
settings = Settings()

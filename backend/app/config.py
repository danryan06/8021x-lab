from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://dot1x:dot1x_lab_change_me@localhost:5432/dot1x_lab"
    secret_key: str = "change-me-to-a-long-random-string"
    admin_username: str = "admin"
    admin_password: str = "admin"
    access_token_expire_minutes: int = 480
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    freeradius_config_dir: str = "/var/lib/dot1x-lab/freeradius"
    freeradius_reload_command: str = 'echo "reload-requested"'
    freeradius_templates_dir: str = "/app/services/freeradius/templates"
    ca_data_dir: str = "/var/lib/dot1x-lab/ca"
    ca_adapter: str = "openssl"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

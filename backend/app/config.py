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
    freeradius_auth_log_path: str = "/var/lib/dot1x-lab/freeradius/logs/auth.log"
    # Compose service DNS name for in-cluster eapol_test / health probes.
    freeradius_host: str = "freeradius"
    freeradius_auth_port: int = 1812
    # Matches services/freeradius docker-entrypoint lab-docker-host client.
    freeradius_lab_secret: str = "testing123"
    # CoA / Disconnect-Request (RFC 5176) destination port on the NAS.
    coa_port: int = 3799
    # Loopback sink in the backend process so Compose demos get an ACK without
    # a switch listening on 3799. Not published to the host.
    coa_sink_host: str = "127.0.0.1"
    coa_sink_enabled: bool = True
    # FreeRADIUS EAP server CA copied onto the shared runtime volume.
    freeradius_ca_path: str = "/var/lib/dot1x-lab/freeradius/certs/ca.pem"
    freeradius_health_max_age_seconds: int = 45
    # When true, the FreeRADIUS entrypoint enforces the published CRL for
    # EAP-TLS (check_crl). Off by default: enabling CRL checking requires a
    # current CRL for every trusted lab CA or client validation fails.
    freeradius_enforce_crl: bool = False
    # Advertised RADIUS target for real NAS/AP devices (DHCP/auto + manual override).
    radius_advertise_ip: str = ""
    radius_advertise_auth_port: int = 1812
    radius_advertise_acct_port: int = 1813
    # Optional host-written file (bootstrap) with the LAN/DHCP IPv4 to advertise.
    radius_host_ip_file: str = "/var/lib/dot1x-lab/freeradius/host-ip"
    ca_data_dir: str = "/var/lib/dot1x-lab/ca"
    ca_adapter: str = "openssl"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

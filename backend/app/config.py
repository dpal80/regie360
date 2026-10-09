from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurazione letta dalle variabili d'ambiente (file .env in Docker Compose)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://crm:crm@db:5432/crm"

    # Chiave per firmare i token di sessione: obbligatoria e lunga in produzione.
    jwt_secret: str
    jwt_minuti: int = 30
    cookie_secure: bool = True

    # Amministratore locale di emergenza, creato al primo avvio se non esiste.
    admin_username: str = "admin"
    admin_password: str | None = None

    # Active Directory (LDAPS). Se ad_server è vuoto entra solo l'admin locale.
    ad_server: str = ""
    ad_port: int = 636
    ad_use_ssl: bool = True
    ad_domain: str = ""  # es. regieauto.local, usato come utente@dominio
    ad_ca_file: str = ""  # certificato della CA interna, se serve
    ad_timeout: int = 5

    # Blocco dopo troppi tentativi falliti.
    login_max_tentativi: int = 5
    login_blocco_minuti: int = 15

    import_max_mb: int = 20

    # Documentazione interattiva delle API su /api/docs (carica script da CDN: solo in sviluppo).
    api_docs: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()

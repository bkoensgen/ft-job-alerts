import os
from dataclasses import dataclass


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return str(val).strip() not in ("0", "false", "FALSE", "no", "No", "")


def _load_dotenv_if_present() -> None:
    path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except Exception:
        # Silently ignore .env parsing errors; user can export manually
        pass


@dataclass
class Config:
    api_simulate: bool
    client_id: str | None
    client_secret: str | None
    auth_url: str
    oauth_scope: str | None
    oauth_audience: str | None
    oauth_use_basic: bool
    range_header: bool
    accept_language: str | None
    debug: bool
    offres_search_url: str
    offres_detail_url: str
    lbb_api_url: str | None
    rome_api_url: str | None
    email_to: str | None
    smtp_host: str | None
    smtp_port: int
    smtp_user: str | None
    smtp_password: str | None
    smtp_starttls: bool
    default_keywords: list[str]
    default_dept: str | None
    default_radius_km: int


def load_config() -> Config:
    _load_dotenv_if_present()
    return Config(
        api_simulate=_get_bool("FT_API_SIMULATE", True),
        client_id=os.getenv("FT_CLIENT_ID"),
        client_secret=os.getenv("FT_CLIENT_SECRET"),
        auth_url=os.getenv(
            "FT_AUTH_URL",
            "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire",
        ),
        oauth_scope=os.getenv("FT_SCOPE"),
        oauth_audience=os.getenv("FT_AUDIENCE"),
        oauth_use_basic=_get_bool("FT_OAUTH_BASIC", True),
        range_header=_get_bool("FT_RANGE_HEADER", False),
        accept_language=os.getenv("FT_ACCEPT_LANGUAGE", "fr-FR"),
        debug=_get_bool("FT_DEBUG", False),
        offres_search_url=os.getenv(
            "FT_OFFRES_SEARCH_URL",
            "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search",
        ),
        offres_detail_url=os.getenv(
            "FT_OFFRES_DETAIL_URL",
            "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/{id}",
        ),
        lbb_api_url=os.getenv("LBB_API_URL"),
        rome_api_url=os.getenv("ROME_API_URL"),
        email_to=os.getenv("EMAIL_TO"),
        smtp_host=os.getenv("SMTP_HOST"),
        smtp_port=int(os.getenv("SMTP_PORT", "587")),
        smtp_user=os.getenv("SMTP_USER"),
        smtp_password=os.getenv("SMTP_PASSWORD"),
        smtp_starttls=_get_bool("SMTP_STARTTLS", True),
        default_keywords=[k.strip() for k in os.getenv("DEFAULT_KEYWORDS", "ros2,c++,vision").split(",") if k.strip()],
        default_dept=os.getenv("DEFAULT_DEPT", "68"),
        default_radius_km=int(os.getenv("DEFAULT_RADIUS_KM", "50")),
    )

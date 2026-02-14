import os
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

load_dotenv()


def to_asyncpg_dsn(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme
    if scheme == "postgres":
        scheme = "postgresql+asyncpg"
    elif scheme == "postgresql":
        scheme = "postgresql+asyncpg"
    elif scheme in {"postgresql+psycopg2", "postgresql+psycopg"}:
        scheme = "postgresql+asyncpg"

    query_items = dict(parse_qsl(parsed.query, keep_blank_values=True))
    sslmode = query_items.pop("sslmode", None)
    if sslmode and "ssl" not in query_items:
        query_items["ssl"] = (
            "require" if sslmode in {"require", "verify-ca", "verify-full"} else sslmode
        )

    return urlunparse(
        (
            scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query_items),
            parsed.fragment,
        )
    )


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class ServiceSettings:
    database_url: str


settings = ServiceSettings(database_url=_require_env("DATABASE_URL"))

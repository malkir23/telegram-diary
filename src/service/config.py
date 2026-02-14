from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def to_asyncpg_dsn(url: str) -> str:
    parsed = urlparse(url)
    scheme = parsed.scheme
    # if scheme == "postgres":
    #     scheme = "postgresql+asyncpg"
    # elif scheme == "postgresql":
    #     scheme = "postgresql+asyncpg"
    # elif scheme in {"postgresql+psycopg2", "postgresql+psycopg"}:
    #     scheme = "postgresql+asyncpg"

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


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(alias="DATABASE_URL")


settings = ServiceSettings()

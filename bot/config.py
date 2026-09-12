from dataclasses import dataclass
from os import environ


@dataclass(frozen=True, slots=True)
class Config:
    bot_token: str

    @classmethod
    def from_env(cls) -> "Config":
        token = environ.get("BOT_TOKEN", "").strip()
        if not token:
            raise RuntimeError("BOT_TOKEN environment variable is required")
        return cls(bot_token=token)

from dataclasses import dataclass


@dataclass
class PostgresConfig:
    host: str
    port: int
    user: str
    password: str
    name: str

    @property
    def dsn(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"


@dataclass
class RedisConfig:
    fsm_dsn: str
    cache_dsn: str


@dataclass
class BotConfig:
    token: str
    creator_id: int
    timezone: str = "Europe/Minsk"


@dataclass
class Config:
    postgres: PostgresConfig
    redis: RedisConfig
    bot: BotConfig

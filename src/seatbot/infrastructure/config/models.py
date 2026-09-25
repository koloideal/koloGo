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
class CryptoBotConfig:
    api_token: str
    api_url: str = "https://pay.crypt.bot/api/"


@dataclass
class GeoConfig:
    yandex_max_route_points: int = 20


@dataclass
class TrackingConfig:
    min_point_gap_m: float = 2.0
    max_speed_mps: float = 60.0
    max_accuracy_m: float = 100.0
    arrival_radius_m: float = 150.0
    arrival_debounce: int = 2
    arrival_dwell_s: int = 60
    auto_complete_after_h: int = 12


@dataclass
class HealthConfig:
    host: str = "0.0.0.0"
    port: int = 8080
    path: str = "/health"


@dataclass
class Config:
    postgres: PostgresConfig
    redis: RedisConfig
    bot: BotConfig
    cryptobot: CryptoBotConfig
    geo: GeoConfig
    tracking: TrackingConfig
    health: HealthConfig

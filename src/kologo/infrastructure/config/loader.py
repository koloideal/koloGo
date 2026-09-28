import toml

from .models import (BotConfig, Config, CryptoBotConfig, GeoConfig, HealthConfig,
                     PostgresConfig, RedisConfig, TrackingConfig)


def load_config(config_path: str) -> Config:
    raw = toml.load(config_path)
    bot_raw = raw["bot"]
    cb = raw["cryptobot"]
    geo_raw = raw.get("geo", {})
    tracking_raw = raw.get("tracking", {})
    health_raw = raw.get("health", {})
    cryptobot = CryptoBotConfig(
        api_token=cb["api_token"],
        api_url=cb.get("api_url", "https://pay.crypt.bot/api/"),
    )
    return Config(
        postgres=PostgresConfig(
            host=raw["postgres"]["host"],
            port=raw["postgres"]["port"],
            user=raw["postgres"]["user"],
            password=raw["postgres"]["password"],
            name=raw["postgres"]["name"],
        ),
        redis=RedisConfig(
            fsm_dsn=raw["redis"]["fsm_dsn"],
            cache_dsn=raw["redis"]["cache_dsn"],
        ),
        bot=BotConfig(
            token=bot_raw["token"],
            creator_id=bot_raw["creator_id"],
            timezone=bot_raw.get("timezone", "Europe/Minsk"),
        ),
        cryptobot=cryptobot,
        geo=GeoConfig(
            yandex_max_route_points=int(geo_raw.get("yandex_max_route_points", 20)),
        ),
        tracking=TrackingConfig(
            min_point_gap_m=float(tracking_raw.get("min_point_gap_m", 2.0)),
            max_speed_mps=float(tracking_raw.get("max_speed_mps", 60.0)),
            max_accuracy_m=float(tracking_raw.get("max_accuracy_m", 100.0)),
            arrival_radius_m=float(
                tracking_raw.get("arrival_radius_m", bot_raw.get("arrival_radius_m", 150.0))
            ),
            arrival_debounce=int(tracking_raw.get("arrival_debounce", bot_raw.get("arrival_debounce", 2))),
            arrival_dwell_s=int(tracking_raw.get("arrival_dwell_s", 60)),
            auto_complete_after_h=int(tracking_raw.get("auto_complete_after_h", 12)),
        ),
        health=HealthConfig(
            host=str(health_raw.get("host", "0.0.0.0")),
            port=int(health_raw.get("port", 8080)),
            path=str(health_raw.get("path", "/health")),
        ),
    )

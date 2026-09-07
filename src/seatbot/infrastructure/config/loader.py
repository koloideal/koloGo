import toml

from .models import BotConfig, Config, PostgresConfig, RedisConfig


def load_config(config_path: str) -> Config:
    raw = toml.load(config_path)
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
            token=raw["bot"]["token"],
            creator_id=raw["bot"]["creator_id"],
            timezone=raw["bot"].get("timezone", "Europe/Minsk"),
        ),
    )

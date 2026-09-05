import json
import logging.config
import os
from pathlib import Path


def setup_logging(config_path: str) -> None:
    path = Path(config_path)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
        logging.config.dictConfig(config)
    else:
        logging.basicConfig(level=logging.INFO)

    os.makedirs("logs", exist_ok=True)

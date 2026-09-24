import json
import logging.config
from pathlib import Path


def setup_logging(config_path: str) -> None:
    path = Path(config_path)
    if not path.exists():
        logging.basicConfig(level=logging.INFO)
        return
    config = json.loads(path.read_text(encoding="utf-8"))
    for handler in config.get("handlers", {}).values():
        if filename := handler.get("filename"):
            Path(filename).parent.mkdir(parents=True, exist_ok=True)
    logging.config.dictConfig(config)

from __future__ import annotations

import logging
from pathlib import Path


def setup_logger(run_id: str | None = None, log_root: Path | None = None) -> logging.Logger:
    base_dir = log_root or Path(__file__).resolve().parent / "logs"
    base_dir.mkdir(parents=True, exist_ok=True)

    logger_name = "assistance_helper_ai"
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_name = f"agent_{run_id}.log" if run_id else "agent.log"
    file_handler = logging.FileHandler(base_dir / file_name, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    logger.propagate = False
    return logger

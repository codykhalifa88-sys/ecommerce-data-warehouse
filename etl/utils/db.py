"""Database connection and shared logging helpers for the ETL pipeline."""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

load_dotenv()


def get_engine() -> Engine:
    """Build a SQLAlchemy engine from POSTGRES_* environment variables."""
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "ecommerce_dw")
    user = os.getenv("POSTGRES_USER", "dw_user")
    password = os.getenv("POSTGRES_PASSWORD", "change_me")
    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db}"
    return create_engine(url, future=True)


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes to console and to logs/etl_run_{date}.log."""
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger  # already configured (e.g. re-imported in the same process)

    logger.setLevel(logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)

    from datetime import date

    file_handler = logging.FileHandler(log_dir / f"etl_run_{date.today().isoformat()}.log")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


def raw_data_dir() -> Path:
    return Path(os.getenv("RAW_DATA_DIR", "data/raw"))

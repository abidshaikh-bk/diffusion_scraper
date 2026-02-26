import logging
from pathlib import Path


def setup_logger(log_file: str = "data/logs/worker.log") -> logging.Logger:
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("video_platform_scraper")
    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)

    sh = logging.StreamHandler()
    sh.setFormatter(fmt)

    # avoid duplicate handlers if re-imported
    if not logger.handlers:
        logger.addHandler(fh)
        logger.addHandler(sh)

    return logger
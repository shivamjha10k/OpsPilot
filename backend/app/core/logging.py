import logging
import sys

from .config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure one consistent application logger for the foundation."""

    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stdout,
        force=True,
    )

# helpers/logger.py
import logging
import sys
import contextvars

STEP = contextvars.ContextVar("step", default="-")

class ContextFilter(logging.Filter):
    def filter(self, record):
        record.step = STEP.get()
        return True

def set_log_context(step=None):
    if step is not None:
        STEP.set(step)

def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        logger.addHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s - %(name)s - step=%(step)s - %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )

    for h in logger.handlers:
        h.setFormatter(formatter)
        if not any(isinstance(f, ContextFilter) for f in getattr(h, "filters", [])):
            h.addFilter(ContextFilter())

    logger.propagate = False
    return logger


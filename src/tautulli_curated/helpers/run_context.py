# helpers/run_context.py
import time
from contextlib import contextmanager
from tautulli_curated.helpers.logger import set_log_context

class RunContext:
    @contextmanager
    def step(self, logger, step_name: str, **meta):
        set_log_context(step=step_name)
        t0 = time.time()

        meta_str = f" {meta}" if meta else ""
        logger.info(f"▶ START{meta_str}")

        try:
            yield
        except Exception:
            logger.exception("✖ ERROR")
            raise
        finally:
            took = time.time() - t0
            logger.info(f"■ END took={took:.2f}s")
            set_log_context(step="-")


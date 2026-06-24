import asyncio
import random
import functools
import logging

logger = logging.getLogger("Retry-Decorator")

def with_retry(max_attempts=5, base_delay=1.0):
    def decorator(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return await fn(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(f"Function {fn.__name__} failed after {max_attempts} attempts. Error: {str(e)}")
                        raise
                    delay = base_delay * (2 ** attempt) + random.random()
                    logger.warning(f"Function {fn.__name__} failed (attempt {attempt + 1}/{max_attempts}). Retrying in {delay:.2f}s... Error: {str(e)}")
                    await asyncio.sleep(delay)
        return wrapper
    return decorator

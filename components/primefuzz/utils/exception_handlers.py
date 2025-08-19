import asyncio
import functools
import logging
import traceback
from typing import Callable, Any

logger = logging.getLogger(__name__)

def handle_missing_event_loop(func: Callable) -> Callable:
    """
    Decorator to handle exceptions related to missing asyncio event loops.
    
    This decorator is particularly useful for functions that may be called from
    both synchronous contexts (like background threads) and asynchronous contexts.
    If a function attempts to access asyncio features without a running event loop,
    this decorator will catch the error and provide a fallback mechanism.
    
    Args:
        func (Callable): The function to decorate
        
    Returns:
        Callable: The wrapped function with exception handling
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RuntimeError as e:
            if "no running event loop" in str(e):
                logger.debug(f"No running event loop available for {func.__name__}. Creating new loop.")
                try:
                    # Create a new event loop for this thread
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    # Try again with new loop
                    return func(*args, **kwargs)
                except Exception as inner_e:
                    logger.debug(f"Failed to execute {func.__name__} with new event loop: {inner_e}")
                    # Just log and continue without raising
                    return None
            else:
                # For other RuntimeErrors, re-raise
                raise
        except Exception as e:
            logger.debug(f"Exception in {func.__name__}: {e}")
            # For telemetry operations, we typically want to continue even if they fail
            return None
            
    return wrapper

"""Resilience utilities - retries, rate limiting, circuit breaker."""

import time
import functools
from collections import deque
from datetime import datetime
from typing import Callable, TypeVar, ParamSpec
from threading import Lock

from src.utils.logging import get_logger


P = ParamSpec("P")
T = TypeVar("T")

logger = get_logger("resilience")


class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    pass


class CircuitBreakerOpen(Exception):
    """Raised when circuit breaker is open."""
    pass


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    pass


def with_retry(
    max_attempts: int = 3,
    backoff_base: float = 2.0,
    exceptions: tuple = (Exception,),
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Decorator for retry with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        backoff_base: Base for exponential backoff (seconds)
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        sleep_time = backoff_base ** attempt
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {func.__name__}: {e}. "
                            f"Retrying in {sleep_time:.1f}s"
                        )
                        time.sleep(sleep_time)
                    else:
                        logger.error(
                            f"All {max_attempts} attempts failed for {func.__name__}"
                        )

            raise RetryError(
                f"All {max_attempts} attempts failed"
            ) from last_exception

        return wrapper
    return decorator


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.window_size = 60.0  # seconds
        self._requests: deque = deque()
        self._lock = Lock()

    def _cleanup_old_requests(self):
        """Remove requests outside the time window."""
        cutoff = time.time() - self.window_size
        while self._requests and self._requests[0] < cutoff:
            self._requests.popleft()

    def acquire(self, block: bool = True, timeout: float | None = None) -> bool:
        """Try to acquire a rate limit token.

        Args:
            block: If True, block until a token is available
            timeout: Maximum time to wait (only if block=True)

        Returns:
            True if token acquired, False otherwise

        Raises:
            RateLimitExceeded: If block=False and limit is exceeded
        """
        start_time = time.time()

        while True:
            with self._lock:
                self._cleanup_old_requests()

                if len(self._requests) < self.requests_per_minute:
                    self._requests.append(time.time())
                    return True

                if not block:
                    raise RateLimitExceeded(
                        f"Rate limit of {self.requests_per_minute}/min exceeded"
                    )

                # Calculate wait time
                oldest = self._requests[0]
                wait_time = oldest + self.window_size - time.time()

            if timeout is not None:
                elapsed = time.time() - start_time
                if elapsed >= timeout:
                    raise RateLimitExceeded(
                        f"Rate limit timeout after {timeout}s"
                    )
                wait_time = min(wait_time, timeout - elapsed)

            if wait_time > 0:
                time.sleep(min(wait_time, 0.1))  # Check frequently

    def __call__(self, func: Callable[P, T]) -> Callable[P, T]:
        """Use as a decorator."""
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            self.acquire()
            return func(*args, **kwargs)
        return wrapper


class CircuitBreaker:
    """Circuit breaker pattern for fault tolerance."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_requests: int = 1,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self._failures = 0
        self._last_failure_time: float | None = None
        self._state = "closed"  # closed, open, half-open
        self._half_open_successes = 0
        self._lock = Lock()

    @property
    def state(self) -> str:
        """Get current circuit breaker state."""
        with self._lock:
            self._check_state_transition()
            return self._state

    def _check_state_transition(self):
        """Check if state should transition."""
        if self._state == "open" and self._last_failure_time:
            if time.time() - self._last_failure_time >= self.recovery_timeout:
                self._state = "half-open"
                self._half_open_successes = 0
                logger.info("Circuit breaker transitioning to half-open")

    def _record_success(self):
        """Record a successful call."""
        with self._lock:
            if self._state == "half-open":
                self._half_open_successes += 1
                if self._half_open_successes >= self.half_open_requests:
                    self._state = "closed"
                    self._failures = 0
                    logger.info("Circuit breaker closed")
            elif self._state == "closed":
                self._failures = 0

    def _record_failure(self):
        """Record a failed call."""
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()

            if self._state == "half-open":
                self._state = "open"
                logger.warning("Circuit breaker re-opened from half-open")
            elif self._failures >= self.failure_threshold:
                self._state = "open"
                logger.warning(
                    f"Circuit breaker opened after {self._failures} failures"
                )

    def call(self, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
        """Execute a function through the circuit breaker."""
        with self._lock:
            self._check_state_transition()
            current_state = self._state

        if current_state == "open":
            raise CircuitBreakerOpen("Circuit breaker is open")

        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise

    def __call__(self, func: Callable[P, T]) -> Callable[P, T]:
        """Use as a decorator."""
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return self.call(func, *args, **kwargs)
        return wrapper

    def reset(self):
        """Manually reset the circuit breaker."""
        with self._lock:
            self._state = "closed"
            self._failures = 0
            self._last_failure_time = None
            self._half_open_successes = 0
        logger.info("Circuit breaker manually reset")

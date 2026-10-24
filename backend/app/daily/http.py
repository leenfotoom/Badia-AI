"""HTTP client: host allowlist, retries with backoff, disk cache, injectable transport."""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .config import ALLOWED_HOSTS
from .store import write_text_atomic

log = logging.getLogger("badia.daily.http")


class ProviderError(RuntimeError):
    """Provider unreachable / invalid after all retries."""


class HostNotAllowed(ProviderError):
    pass


_MISSING = object()


def _default_transport(url: str, timeout: float) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "BADIA-AI/daily-engine"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


class Client:
    def __init__(self, cache_dir: Path | None = None, transport: Callable[[str, float], tuple[int, str]] | None = None,
                 retries: int = 4, backoff: float = 1.5, timeout: float = 90.0,
                 sleep: Callable[[float], None] = time.sleep, cache_ttl_s: float = 3 * 3600,
                 rate_limit_backoff: float = 60.0) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.transport = transport or _default_transport
        self.retries, self.backoff, self.timeout = retries, backoff, timeout
        self.sleep, self.cache_ttl_s = sleep, cache_ttl_s
        self.rate_limit_backoff = rate_limit_backoff
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_json(self, base: str, params: dict[str, Any], *, use_cache: bool = True,
                 immutable: bool = False) -> tuple[Any, dict]:
        """Return (payload, meta). `immutable` = historical data, cache never expires."""
        host = urllib.parse.urlparse(base).hostname or ""
        if host not in ALLOWED_HOSTS:
            raise HostNotAllowed(f"host '{host}' is not in the provider allowlist")
        url = base + "?" + urllib.parse.urlencode(sorted(params.items()), safe=",")
        key = hashlib.sha256(url.encode()).hexdigest()[:32]
        path = self.cache_dir / f"{key}.json" if self.cache_dir else None
        cached, cache_mtime = _MISSING, None
        if use_cache and path and path.exists():
            cached, cache_mtime = self._read_cache(path)
            if cached is not _MISSING and cache_mtime is not None:
                age = max(0.0, time.time() - cache_mtime)
                if immutable or age <= self.cache_ttl_s:
                    return cached, {"from_cache": True, "stale": False, "host": host,
                                    "fetched_at": _iso(cache_mtime), "cache_key": key}
        last: str = ""
        for attempt in range(self.retries + 1):
            rate_limited = False
            try:
                status, body = self.transport(url, self.timeout)
                if status == 200:
                    payload = json.loads(body)
                    if isinstance(payload, dict) and payload.get("error"):
                        raise ProviderError(str(payload.get("reason", "provider error")))
                    if path:
                        write_text_atomic(path, body)
                    fetched_at = path.stat().st_mtime if path and path.exists() else time.time()
                    return payload, {"from_cache": False, "stale": False, "host": host,
                                     "fetched_at": _iso(fetched_at), "cache_key": key}
                reason = ""
                try:
                    error_payload = json.loads(body)
                    if isinstance(error_payload, dict):
                        reason = str(error_payload.get("reason") or "").strip()
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
                last = f"HTTP {status}" + (f": {reason}" if reason else "")
                rate_limited = status == 429
                if status not in (408, 425, 429, 500, 502, 503, 504):
                    break  # non-retryable (e.g. 400/403)
            except (OSError, ValueError, ProviderError) as exc:
                last = f"{type(exc).__name__}: {exc}"
            if attempt < self.retries:
                # Open-Meteo's free API applies a rolling minutely weighted-call
                # limit.  A one-second exponential retry simply burns every retry
                # inside the same window.  Respect that window for HTTP 429 while
                # retaining the shorter transient-error backoff for 5xx/timeouts.
                delay = self.backoff ** attempt + random.uniform(0, 0.25)
                if rate_limited:
                    delay = max(delay, self.rate_limit_backoff)
                log.warning("retry %d for %s after %s (%.1fs)", attempt + 1, host, last, delay)
                self.sleep(delay)
        # Stale cache beats nothing, but is flagged so freshness logic can degrade confidence.
        if use_cache and cached is not _MISSING and cache_mtime is not None:
            log.error("serving STALE cache for %s (%s)", host, last)
            return cached, {"from_cache": True, "stale": True, "host": host,
                            "fetched_at": _iso(cache_mtime), "cache_key": key}
        raise ProviderError(f"{host} unavailable: {last}")

    @staticmethod
    def _read_cache(path: Path) -> tuple[Any, float | None]:
        """Read a cache entry defensively; corrupt entries are reproducible and discarded."""
        try:
            modified = path.stat().st_mtime
            return json.loads(path.read_text("utf-8")), modified
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
            log.warning("discarding unreadable HTTP cache entry %s: %s", path.name, exc)
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning("could not remove corrupt cache entry %s", path.name)
            return _MISSING, None


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")

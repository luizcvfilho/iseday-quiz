"""Opaque credentials and bounded, per-process throttling for the public API."""

import hashlib
import math
import re
from collections import OrderedDict
from threading import Lock
from time import monotonic

from fastapi import HTTPException, Request


def cookie_name(production: bool) -> str:
    return "__Host-iseday_participant" if production else "iseday_participant"


def token_hash(token: str | None) -> str | None:
    if token is None or re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
        return None
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def require_write_request(request: Request) -> None:
    # No CORS is enabled. This custom header requires browser preflight from any
    # foreign origin, including sibling subdomains. Keep this policy when adding CORS.
    if (
        request.headers.get("X-Quiz-Request") != "1"
        or request.headers.get("Sec-Fetch-Site") == "cross-site"
    ):
        raise HTTPException(403, "Requisição não autorizada.")


class PublicRateLimiter:
    """Fixed 60s windows, bounded memory; deployments with workers need upstream limits."""

    def __init__(self, *, capacity: int = 4096, clock=monotonic):
        self._capacity = capacity
        self._clock = clock
        self._windows: OrderedDict[tuple[str, str], tuple[float, int]] = OrderedDict()
        self._lock = Lock()

    def check(self, action: str, key: str, limit: int) -> None:
        with self._lock:
            now = self._clock()
            window_start, count = self._windows.pop((action, key), (now, 0))
            if now - window_start >= 60:
                window_start, count = now, 0
            self._windows[action, key] = (window_start, count + 1)
            if len(self._windows) > self._capacity:
                self._windows.popitem(last=False)
            if count >= limit:
                raise HTTPException(
                    429,
                    "Muitas tentativas. Aguarde antes de tentar novamente.",
                    headers={"Retry-After": str(max(1, math.ceil(60 - (now - window_start))))},
                )

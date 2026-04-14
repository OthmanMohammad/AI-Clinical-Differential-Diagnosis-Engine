"""Shared rate limiter instance.

Lives in its own module so routers can import it without creating a
circular dependency with `app.main`.
"""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter


def get_real_ip(request: Request) -> str:
    """Extract the real client IP behind a reverse proxy (Fly.io / Vercel /
    typical X-Forwarded-For chain)."""
    return (
        request.headers.get("fly-client-ip")
        or request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )


# Single, shared limiter. Routers attach @limiter.limit(...) decorators to
# their endpoints. The limiter is registered with the FastAPI app inside
# main.py via `app.state.limiter = limiter`.
limiter = Limiter(key_func=get_real_ip, default_limits=[])

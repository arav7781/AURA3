"""CSRF protection for cookie-authenticated writes.

The session cookie is SameSite=Lax. On top of that, every unsafe ``/api`` request must carry
``X-Aura-CSRF: 1`` (a custom header a cross-site form cannot send) and, when the browser sends an
``Origin``, it must be one of the allowed origins.
"""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from aura.core.config import get_settings
from aura.core.security import CSRF_HEADER

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def _forbidden(message: str) -> JSONResponse:
    return JSONResponse(status_code=403, content={"error": {"code": "CSRF_FAILED", "message": message, "details": {}}})


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method in UNSAFE and request.url.path.startswith("/api/"):
            if request.headers.get(CSRF_HEADER) != "1":
                return _forbidden(f"Missing {CSRF_HEADER} header")
            origin = request.headers.get("origin")
            if origin and origin not in get_settings().allowed_origins and origin != f"{request.url.scheme}://{request.url.netloc}":
                return _forbidden("Origin not allowed")
        return await call_next(request)

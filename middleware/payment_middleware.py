from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class PaymentMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not request.url.path.startswith("/v2") or "/v2/order" in request.url.path or "/v2/auth" in request.url.path:
            print("skipping middleware")
            return await call_next(request)
        
        print("payment middleware")
        
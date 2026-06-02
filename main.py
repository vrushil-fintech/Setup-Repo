from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import github_routes
from .routes import (
    analysis_routes,
    webhook_routes,
    proxy_route,
    gemini,
    feedback_routes,
    websocket_routes,
    auth_routes, github_auth_routes,
    payment_routes,
    usage_routes,
    contactUs_routes,
    loading_tips_routes,
    mcp_api_key_routes,
)
from .routes.v2 import (
    auth_routes_v2,
    analysis_routes_v2,
    commit_review_route_v2,
    feedback_routes_v2,
    proxy_route_v2,
    websocket_routes_v2,
    payment_routes_v2,
    loading_tips_routes_v2,
    missing_dependencies_routes_v2,
)
from .middleware.auth_middleware import AuthenticationMiddleware
from .config import ALLOWED_ORIGINS, APP_ENV
from .database import async_engine

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await async_engine.dispose()

# Conditionally configure docs based on environment
if APP_ENV == "prod":
    app = FastAPI(
        lifespan=lifespan,
        docs_url=None,       # disable Swagger UI
        redoc_url=None,      # disable ReDoc
    )
else:
    app = FastAPI(lifespan=lifespan)

FastAPIInstrumentor.instrument_app(app)

app.include_router(proxy_route.router)
app.include_router(gemini.router)
app.include_router(websocket_routes.router)
app.include_router(feedback_routes.router)
app.include_router(auth_routes.router)
app.include_router(github_auth_routes.router)
app.include_router(github_routes.router)
app.include_router(payment_routes.router)
app.include_router(usage_routes.router)
app.include_router(analysis_routes.router)
app.include_router(contactUs_routes.router)
app.include_router(loading_tips_routes.router)
app.include_router(webhook_routes.router)
app.include_router(mcp_api_key_routes.router)
app.include_router(auth_routes_v2.router, prefix="/v2")
app.include_router(analysis_routes_v2.router, prefix="/v2")
app.include_router(feedback_routes_v2.router, prefix="/v2")
app.include_router(proxy_route_v2.router, prefix="/v2")
app.include_router(websocket_routes_v2.router, prefix="/v2")
app.include_router(payment_routes_v2.router, prefix="/v2")
app.include_router(loading_tips_routes_v2.router, prefix="/v2")
app.include_router(commit_review_route_v2.router, prefix="/v2")
app.include_router(missing_dependencies_routes_v2.router, prefix="/v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"^vscode-webview://.*$",  # Regex for VS Code webviews
    allow_credentials=True,  # Allow cookies and headers like Authorization
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "OPTIONS",
    ],  # Restrict to specific methods
    allow_headers=["*"]  # Restrict to specific headers
)

app.add_middleware(AuthenticationMiddleware)



@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health/db-pool")
async def check_pool_status():
    main_pool = async_engine.pool
    
    return {
        "main_pool": {
            "size": main_pool.size(),
            "checked_in": main_pool.checkedin(),
            "checked_out": main_pool.checkedout(),
            "overflow": main_pool.overflow(),
        }
    }

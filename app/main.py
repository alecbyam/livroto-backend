from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.products.router import router as products_router
from app.modules.orders.router import router as orders_router
from app.modules.payments.router import router as payments_router
from app.modules.notifications.router import router as notifications_router
from app.modules.ai.router import router as ai_router
from app.modules.location.router import router as location_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 {settings.APP_NAME} v{settings.APP_VERSION} démarré")
    logger.info(f"   Base URL : {settings.BASE_URL}")
    logger.info(f"   Debug    : {settings.DEBUG}")
    yield
    logger.info("Arrêt du serveur")


limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.RATE_LIMIT_PER_MINUTE}/minute"],
)

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Plateforme SaaS e-commerce & livraison — contexte africain (RDC)",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# ── Rate limiting ──────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ── Middleware : résolution du tenant depuis header ou JWT ─────────────────────
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    request.state.tenant_id = request.headers.get("X-Tenant-ID")
    return await call_next(request)


# ── Middleware : audit log des mutations ───────────────────────────────────────
@app.middleware("http")
async def audit_log(request: Request, call_next):
    response = await call_next(request)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        logger.info(
            f"{request.method} {request.url.path} "
            f"→ {response.status_code} "
            f"[{request.client.host if request.client else '?'}]"
        )
    return response


# ── Gestion globale des erreurs non capturées ──────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erreur non gérée : {exc} | {request.method} {request.url.path}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne. Réessayez ou contactez le support."},
    )


# ── Routes système ────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
async def health():
    return {
        "status": "ok",
        "version": settings.APP_VERSION,
        "app": settings.APP_NAME,
    }


@app.get("/", tags=["System"])
async def root():
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs" if settings.DEBUG else "désactivé en production",
        "health": "/health",
    }


# ── Montage des modules ────────────────────────────────────────────────────────
app.include_router(auth_router,          prefix="/api/v1/auth",          tags=["Auth"])
app.include_router(users_router,         prefix="/api/v1/users",         tags=["Users"])
app.include_router(products_router,      prefix="/api/v1/products",      tags=["Products"])
app.include_router(orders_router,        prefix="/api/v1/orders",        tags=["Orders"])
app.include_router(payments_router,      prefix="/api/v1/payments",      tags=["Payments"])
app.include_router(notifications_router, prefix="/api/v1/notifications", tags=["Notifications"])
app.include_router(ai_router,            prefix="/api/v1/ai",            tags=["AI"])
app.include_router(location_router,      prefix="/api/v1/location",      tags=["Location"])

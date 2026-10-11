"""Application factory (owner: D1, spec §5 foundation).

The API is a **modular monolith**: one FastAPI application, one database
connection, one canonical envelope — with modules separated by ownership rather
than by process (spec §3: microservices are out of scope).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from bloodlink_config.logging import configure_logging, get_logger
from bloodlink_contracts import API_PREFIX
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bloodlink_api import __version__
from bloodlink_api.core.envelope import RequestContextMiddleware, success
from bloodlink_api.core.errors import register_exception_handlers
from bloodlink_api.core.registry import all_modules, module_summary, routers
from bloodlink_api.core.routing import api_router
from bloodlink_api.core.settings import get_settings

logger = get_logger("bloodlink.api")

DESCRIPTION = """
**BloodLink** — hospital-centred blood coordination.

BloodLink connects hospitals with authorised blood centres and voluntary donors
through hospital-verified blood requests, location-aware matching, tiered
notifications, donor networks and structured coordination.

BloodLink does **not** perform or replace donor medical screening, blood testing,
crossmatching, collection, processing, storage, issue, transfusion or medical
eligibility determination. Those remain with authorised hospitals and blood
centres.

**Conventions**
* All responses use one envelope: `{"data": ..., "meta": {...}, "error": null}`.
* Errors: `{"data": null, "meta": {...}, "error": {"code", "message", "details"}}`.
* Auth: `Authorization: Bearer <JWT>`; roles are enforced server-side.
* JSON is camelCase; Python is snake_case.

**Ownership** — `D1` platform foundation, `D2` individual/PatientNeed,
`D3` hospital/BloodRequest, `D4` donor/coordination. Each module and endpoint
declares its owner in the OpenAPI tags and in `docs/ownership.md`.
"""

TAGS_METADATA = [
    {"name": "auth", "description": "OWNER: D1 — registration, sign-in, tokens, account context."},
    {"name": "users", "description": "OWNER: D1 — self-service profile and personal history."},
    {"name": "organizations", "description": "OWNER: D1 — organization directory and context."},
    {"name": "admin", "description": "OWNER: D1 — verification, administration, audit, platform."},
    {"name": "patient-needs", "description": "OWNER: D2 — PatientNeed submission and history."},
    {"name": "hospital-needs", "description": "OWNER: D3 — hospital review queue for PatientNeeds."},
    {"name": "blood-requests", "description": "OWNER: D3 — request lifecycle and fulfilment."},
    {"name": "donor-profile", "description": "OWNER: D4 — donor profile, availability, subscriptions."},
    {"name": "donor-responses", "description": "OWNER: D4 — donor acceptance, standby, withdrawal."},
    {"name": "blood-centre-responses", "description": "OWNER: D4 — organization availability responses."},
    {"name": "matching", "description": "OWNER: D4 — deterministic distance-first matching."},
    {"name": "notifications", "description": "OWNER: D4 — notification feed and push subscriptions."},
    {"name": "communication", "description": "OWNER: D4 — request-scoped coordination threads."},
    {"name": "donations", "description": "OWNER: D4 — donation confirmation and history."},
    {"name": "platform", "description": "OWNER: D1 — health, version and module registry."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    # The resolved database is logged in full: running two applications built from
    # the same specification on one machine is normal, and this line is how you
    # tell instantly which database (and which instance) you are looking at.
    logger.info(
        "api.starting env=%s database=%s geo=%s pushTransport=%s",
        settings.env,
        "sqlite" if settings.is_sqlite else "postgresql",
        settings.geo_backend,
        settings.push_transport,
    )
    if settings.geo_backend != "haversine":
        # Honest rather than silent: the setting is accepted and validated, but
        # distance math still runs through the haversine adapter (core/geo.py).
        logger.warning(
            "geo.backend_reserved requested=%s in_use=haversine — coordinates are stored as "
            "plain Float columns and need no PostGIS extension; see docs/database.md",
            settings.geo_backend,
        )

    # Dev/test convenience: create tables and seed demo data. Production uses
    # Alembic (`make migrate`) and never seeds.
    if not settings.is_production:
        from bloodlink_api.db.session import create_all

        create_all()
        if settings.seed_on_startup:
            from bloodlink_api.seed import seed_demo_data

            seed_demo_data()

    yield
    logger.info("api.stopping")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=DESCRIPTION,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        contact={"name": "BloodLink platform team (D1)"},
        license_info={"name": "Proprietary"},
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id", "X-Response-Time-ms"],
    )
    register_exception_handlers(app)

    # ---- domain modules (registered by each module on import) ---------------
    module_routers = routers()
    for module_router in module_routers:
        app.include_router(module_router, prefix=settings.api_prefix)

    # ---- platform endpoints (D1) -------------------------------------------
    platform = api_router(owner="D1", domain="platform", prefix="/platform", foundation_status="COMPLETE")

    @platform.get("/health", summary="Liveness and dependency check")
    def health(request: Request) -> dict:
        """Report API and database health.

        OWNER: D1
        PURPOSE: Liveness probe for the web app and deployments.
        INPUT: none
        OUTPUT: { status, version, env, database, modules }
        AUTHORIZATION: Public.
        STATE CHANGES: none
        ERRORS: 200 with status=DEGRADED when the database is unreachable
        PRIVACY: no configuration secrets are returned
        """
        from sqlalchemy import text

        from bloodlink_api.db.session import get_engine

        database = "ok"
        try:
            with get_engine().connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            database = f"error: {type(exc).__name__}"

        return success(
            request,
            {
                "status": "ok" if database == "ok" else "degraded",
                "version": __version__,
                "env": settings.env,
                "database": database,
                "moduleCount": len(all_modules()),
            },
        )

    @platform.get("/version", summary="Build information")
    def version(request: Request) -> dict:
        """Return build/version metadata for the running API.

        OWNER: D1
        PURPOSE: Client build diagnostics.
        INPUT: none
        OUTPUT: { version, apiPrefix, foundation }
        AUTHORIZATION: Public.
        """
        return success(
            request,
            {
                "name": "BloodLink API",
                "version": __version__,
                "apiPrefix": API_PREFIX,
                "foundation": "spec-1.0-web-only-python",
            },
        )

    @platform.get("/modules", summary="Module ownership and status map")
    def modules(request: Request) -> dict:
        """List every domain module with its owner and foundation status.

        OWNER: D1
        PURPOSE: Machine-readable version of docs/ownership.md for dashboards.
        INPUT: none
        OUTPUT: { modules: [{ key, owner, domain, prefix, status }] }
        AUTHORIZATION: Public (metadata only, no secrets).
        STATE CHANGES: none
        """

        return success(request, {"modules": module_summary()})

    app.include_router(platform, prefix=settings.api_prefix)

    @app.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        """Service root.

        OWNER: D1
        PURPOSE: Point humans and probes at the docs, health check and prefix.
        INPUT: none
        OUTPUT: { service, version, docs, health }
        AUTHORIZATION: Public.
        STATE CHANGES: none
        PRIVACY: no configuration or secrets are returned
        """
        return JSONResponse(
            {
                "service": "BloodLink API",
                "version": __version__,
                "docs": "/docs",
                "health": f"{settings.api_prefix}/platform/health",
            }
        )

    logger.info(
        "api.ready modules=%d routers=%d prefix=%s",
        len(module_summary()),
        len(module_routers),
        settings.api_prefix,
    )
    return app


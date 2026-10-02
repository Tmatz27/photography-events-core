"""Small v1 API: bounded failures, explicit DTOs, no browser-to-Core path."""
import hmac
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException

from .config import Settings
from .database import VERSION, Database, DatabaseUnavailable
from .logging import event
from .schemas import Error, Health, Opportunity, OpportunityList, Presentation, SourceHealthList


def error(status, code, message):
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings=None, database=None, clock=None):
    settings = settings or Settings.from_env()
    db = database or Database(settings)
    clock = clock or (lambda: datetime.now(UTC))

    @asynccontextmanager
    async def lifespan(app):
        event("startup", code="core_0_1_dev")
        yield
        await db.close()

    app = FastAPI(title="Photography Events Core", version=VERSION["core_version"], lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.database = db
    bearer = HTTPBearer(auto_error=False)

    async def auth(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        value = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
        if not hmac.compare_digest(value.encode(), settings.api_token.encode()):
            event("authentication_failure", code="invalid_bearer")
            raise HTTPException(401, "Authentication required")

    @app.exception_handler(DatabaseUnavailable)
    async def db_unavailable(request, exc):
        return error(503, exc.code, "Core cannot serve a trustworthy current assessment")

    @app.exception_handler(RequestValidationError)
    async def invalid(request, exc):
        return error(422, "invalid_request", "Invalid request parameters")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        codes = {401: ("unauthorized", "Authentication required"), 404: ("not_found", "Resource not found")}
        code, message = codes.get(exc.status_code, ("request_failed", "Request failed"))
        response = error(exc.status_code, code, message)
        if exc.status_code == 401:
            response.headers["WWW-Authenticate"] = "Bearer"
        return response

    @app.exception_handler(Exception)
    async def failed(request: Request, exc):
        event("api_request_failure", code="internal_error")
        return error(500, "internal_error", "Request failed")

    @app.get("/health/live", response_model=Health)
    async def live():
        return Health(**VERSION, status="alive")

    @app.get("/health/ready", response_model=Health, responses={503: {"model": Error}})
    async def ready():
        await db.ready()
        return Health(**VERSION, status="ready")

    secured = [Depends(auth)]

    @app.get("/api/v1/opportunities", response_model=OpportunityList, dependencies=secured,
             responses={401: {"model": Error}, 503: {"model": Error}, 422: {"model": Error}})
    async def opportunities(presentation: Presentation | None = None, category: Literal["mammals", "birds"] | None = None):
        return await db.opportunities(clock(), presentation, category)

    @app.get("/api/v1/opportunities/{occurrence_key}", response_model=Opportunity, dependencies=secured,
             responses={401: {"model": Error}, 404: {"model": Error}, 503: {"model": Error}})
    async def opportunity(occurrence_key: str):
        result = await db.opportunities(clock(), occurrence_key=occurrence_key)
        if not result.items:
            raise HTTPException(404)
        return result.items[0]

    @app.get("/api/v1/sources/health", response_model=SourceHealthList, dependencies=secured)
    async def sources():
        now = clock()
        return SourceHealthList(**VERSION, generated_at=now, items=await db.health(now))

    return app

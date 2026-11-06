"""FastAPI application factory."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from relayer.application.exceptions import PaymentNotFoundError
from relayer.domain.exceptions import DomainError
from relayer.entrypoints.api.routes import router
from relayer.entrypoints.api.schemas import ErrorResponse


def create_app() -> FastAPI:
    app = FastAPI(
        title="Gasless Relayer",
        version="0.1.0",
        description=(
            "Sponsors gas for EIP-3009 USDC transfers. "
            "Users sign off-chain; this service pays the gas."
        ),
    )

    app.include_router(router)

    @app.exception_handler(DomainError)
    async def domain_error_handler(
        request: Request, exc: DomainError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(
                error=type(exc).__name__,
                message=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(PaymentNotFoundError)
    async def not_found_handler(
        request: Request, exc: PaymentNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content=ErrorResponse(
                error="PaymentNotFound",
                message=str(exc),
            ).model_dump(),
        )

    return app


app = create_app()

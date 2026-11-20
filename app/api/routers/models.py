from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.api.auth_deps import require
from app.api.errors import ApiError
from app.ml.registry import ModelUnavailable

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/status", dependencies=[Depends(require("models:read"))])
def status(request: Request):
    """Which models are trained, on what data, and with which features."""
    try:
        return request.app.state.model_registry.metadata()
    except ModelUnavailable as exc:
        raise ApiError(404, "not_trained", str(exc))


@router.get("/comparison", dependencies=[Depends(require("models:read"))])
def comparison(request: Request):
    """The saved test-period comparison of the baseline and both models."""
    try:
        return request.app.state.model_registry.report()
    except ModelUnavailable as exc:
        raise ApiError(404, "not_trained", str(exc))

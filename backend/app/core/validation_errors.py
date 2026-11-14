"""The 422 response for a request that fails validation (AGT-F6). FastAPI's default handler
echoes each error's rejected ``input`` (and its ``ctx``), and Python's JSON parser accepts the
non-standard ``NaN``, ``Infinity`` and ``-Infinity`` literals, which strict JSON can't encode:
the response would fail to render and the request would end in a 500. This handler returns the
same ``{"detail": [...]}`` body with each non-finite number spelled as the literal sent."""

import math
from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_LITERALS = {math.inf: "Infinity", -math.inf: "-Infinity"}


def _finite(value: Any) -> Any:
    """``value`` with every non-finite float, however deeply nested, replaced by its literal."""
    if isinstance(value, float) and not math.isfinite(value):
        return _LITERALS.get(value, "NaN")
    if isinstance(value, dict):
        return {key: _finite(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_finite(item) for item in value]
    return value


async def request_validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422, content={"detail": _finite(jsonable_encoder(error.errors()))}
    )

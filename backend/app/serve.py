"""API server entrypoint: `python -m app.serve [port]`.

Logging is configured before uvicorn starts, so even its startup lines are JSON. The whole
module is the entrypoint block; tests run it as a process (`tests/integration/test_logging.py`).
"""

if __name__ == "__main__":
    import sys

    import uvicorn

    from app.core.logs import configure_logging

    configure_logging("api")
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_config=None)  # noqa: S104

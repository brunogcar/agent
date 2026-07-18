"""Test that core.gateway:create_app is importable (uvicorn string reference).

server.py starts the gateway via:
    uvicorn.run("core.gateway:create_app", factory=True, ...)

If this string reference breaks (e.g., import error, renamed function),
the gateway won't start. This test catches that early.
"""
from __future__ import annotations


def test_create_app_importable():
    """Assert that core.gateway.create_app can be imported (the uvicorn string reference)."""
    from core.gateway import create_app
    assert callable(create_app)


def test_create_app_returns_fastapi_app():
    """Assert that create_app() returns a FastAPI app instance."""
    from core.gateway import create_app
    app = create_app()
    # FastAPI apps have these attributes
    assert hasattr(app, "routes")
    assert hasattr(app, "middleware_stack")


def test_websocket_route_registered():
    """v1.1: Assert that the /ws WebSocket route is registered."""
    from core.gateway import create_app
    app = create_app()
    ws_routes = [r for r in app.routes if hasattr(r, "path") and r.path == "/ws"]
    assert len(ws_routes) == 1, f"Expected 1 /ws route, got {len(ws_routes)}"

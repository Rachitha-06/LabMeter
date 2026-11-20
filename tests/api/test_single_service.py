from fastapi.testclient import TestClient

from app.main import create_app


def build_dist(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>LabMeter</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    return dist


def test_interface_is_served_and_deep_links_fall_back_to_index(tmp_path):
    client = TestClient(create_app(frontend_dist=build_dist(tmp_path)))
    assert "LabMeter" in client.get("/").text
    assert "LabMeter" in client.get("/labs/12").text          # deep link inside the single-page app
    assert client.get("/assets/app.js").text == "console.log('ok')"


def test_api_routes_are_not_swallowed_by_the_interface(tmp_path):
    client = TestClient(create_app(frontend_dist=build_dist(tmp_path)))
    assert client.get("/api/health").json() == {"status": "ok"}
    missing = client.get("/api/does-not-exist")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_path_resolver_never_returns_a_file_outside_the_build_folder(tmp_path):
    """Tested directly, because an HTTP client normalises '..' before the server ever sees it."""
    from app.main import resolve_interface_file
    dist = build_dist(tmp_path).resolve()
    (tmp_path / "secret.txt").write_text("do not serve", encoding="utf-8")
    assert resolve_interface_file(dist, "../secret.txt") is None
    assert resolve_interface_file(dist, "assets/../../secret.txt") is None
    assert resolve_interface_file(dist, "/etc/passwd") is None
    assert resolve_interface_file(dist, "") is None
    assert resolve_interface_file(dist, "assets/app.js") == dist / "assets" / "app.js"


def test_without_a_build_the_api_still_works(tmp_path):
    client = TestClient(create_app(frontend_dist=tmp_path / "missing"))
    assert client.get("/api/health").json() == {"status": "ok"}


def test_cors_allows_the_methods_the_interface_uses(tmp_path, monkeypatch):
    """The interface on another origin (for example Vercel) must be allowed to send PUT and PATCH."""
    client = TestClient(create_app(frontend_dist=tmp_path / "missing"))
    response = client.options("/api/calendar", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "PUT" in response.headers["access-control-allow-methods"]

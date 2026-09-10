from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_backend_release_contains_the_pinned_ua_viewer() -> None:
    dockerfile = (ROOT / "deploy/backend.Dockerfile").read_text(encoding="utf-8")
    assert "COPY web/ua-viewer-dist ./web/ua-viewer-dist" in dockerfile
    assert "COINTENT_UA_VIEWER_ROOT=/app/web/ua-viewer-dist" in dockerfile


def test_nginx_routes_viewer_and_scoped_artifact_data_plane() -> None:
    for name in ("cointent.conf", "cointent.bootstrap.conf"):
        config = (ROOT / "deploy/nginx" / name).read_text(encoding="utf-8")
        assert "location ^~ /ua-viewer" in config
        assert "location ^~ /internal/" in config
        assert "client_max_body_size 1024m" in config
        assert "proxy_request_buffering off" in config


def test_release_validates_dashboard_commit_and_bridge_patch() -> None:
    release = (ROOT / "deploy/release-beijing.sh").read_text(encoding="utf-8")
    builder = (ROOT / "scripts/build-ua-viewer.sh").read_text(encoding="utf-8")
    assert "bridge_patch_sha256" in release
    assert "scripts/build-ua-viewer.sh" in release
    assert "bridge_patch_sha256" in builder

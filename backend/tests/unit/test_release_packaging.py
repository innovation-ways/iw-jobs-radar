"""Install-from-images packaging: frontend image, secrets entrypoint, release and demo compose (ADR-079)."""

import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from jobs_radar.core.settings import Settings

ROOT = Path(__file__).resolve().parents[3]
RELEASE = ROOT / "docker-compose.release.yml"
DEMO = ROOT / "docker-compose.demo.yml"
ENTRYPOINT = ROOT / "backend" / "docker-entrypoint.sh"


def _compose(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict)
    return data


def _services(path: Path) -> dict[str, dict[str, Any]]:
    services = _compose(path)["services"]
    assert isinstance(services, dict)
    return services


# --- frontend image -------------------------------------------------------------------------------


def test_the_frontend_image_serves_a_static_build_with_nginx() -> None:
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()
    assert "pnpm" in dockerfile and "--frozen-lockfile" in dockerfile
    assert re.search(r"^FROM .*nginx", dockerfile, re.M)
    assert (ROOT / "frontend" / ".dockerignore").read_text().count("node_modules")


def test_nginx_proxies_the_api_on_the_same_origin_and_falls_back_to_the_app() -> None:
    conf = (ROOT / "frontend" / "nginx.conf").read_text()
    for prefix in ("/api/", "/healthz", "/readyz"):
        assert re.search(rf"location\s+(\^~\s+|=\s+)?{re.escape(prefix)}", conf), prefix
    assert "proxy_pass http://api:8000" in conf
    assert "try_files $uri /index.html" in conf


# --- secrets entrypoint ---------------------------------------------------------------------------


def _run_entrypoint(secrets: Path, *args: str, extra: dict[str, str] | None = None) -> str:
    # The script calls plain `python`; use the interpreter running the tests.
    env = {
        "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        "JOBS_RADAR_SECRETS_DIR": str(secrets),
        **(extra or {}),
    }
    result = subprocess.run(  # noqa: S603
        ["sh", str(ENTRYPOINT), *args],  # noqa: S607
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def test_init_creates_the_secrets_once_and_keeps_them(tmp_path: Path) -> None:
    _run_entrypoint(tmp_path, "init")
    key = (tmp_path / "credential_key").read_text()
    password = (tmp_path / "db_password").read_text()
    assert len(key) == 44 and key.endswith("=")  # Fernet: 32 bytes, url-safe base64
    assert re.fullmatch(r"[A-Za-z0-9]{32}", password)
    assert stat.S_IMODE((tmp_path / "credential_key").stat().st_mode) == 0o400
    _run_entrypoint(tmp_path, "init")
    assert (tmp_path / "credential_key").read_text() == key
    assert (tmp_path / "db_password").read_text() == password


def test_a_command_gets_the_secrets_in_its_environment(tmp_path: Path) -> None:
    _run_entrypoint(tmp_path, "init")
    out = _run_entrypoint(
        tmp_path,
        "sh",
        "-c",
        'printf "%s|%s" "$JOBS_RADAR_CREDENTIAL_KEY" "$JOBS_RADAR_DB_PASSWORD"',
    )
    key, password = out.split("|")
    assert key == (tmp_path / "credential_key").read_text()
    assert password == (tmp_path / "db_password").read_text()


def test_values_already_in_the_environment_win_and_nothing_is_printed(tmp_path: Path) -> None:
    _run_entrypoint(tmp_path, "init")
    out = _run_entrypoint(
        tmp_path,
        "sh",
        "-c",
        'printf "%s" "$JOBS_RADAR_DB_PASSWORD"',
        extra={"JOBS_RADAR_DB_PASSWORD": "from-env"},
    )
    assert out == "from-env"


def test_without_a_secrets_directory_the_command_just_runs() -> None:
    env = {"PATH": os.environ["PATH"]}
    result = subprocess.run(  # noqa: S603
        ["sh", str(ENTRYPOINT), "echo", "ok"],  # noqa: S607
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "ok"


def test_the_backend_image_uses_the_entrypoint() -> None:
    dockerfile = (ROOT / "backend" / "Dockerfile").read_text()
    assert "docker-entrypoint.sh" in dockerfile and "ENTRYPOINT" in dockerfile


# --- release compose ------------------------------------------------------------------------------


def test_the_release_compose_uses_published_images_only() -> None:
    for name, service in _services(RELEASE).items():
        assert "build" not in service, name
        assert "network_mode" not in service, name
        image = service["image"]
        if "jobs-radar" in image:
            assert "ghcr.io/innovation-ways/iw-jobs-radar-" in image
            assert "${JOBS_RADAR_VERSION:?" in image or "${JOBS_RADAR_VERSION:-" in image


def test_only_the_frontend_is_published_and_on_loopback_by_default() -> None:
    services = _services(RELEASE)
    published = {name: s["ports"] for name, s in services.items() if "ports" in s}
    assert list(published) == ["frontend"]
    (port,) = published["frontend"]
    assert str(port).startswith("${JOBS_RADAR_FRONTEND_BIND:-127.0.0.1}:")


def test_the_release_compose_wires_the_services_over_the_bridge_network() -> None:
    services = _services(RELEASE)
    env = services["api"]["environment"]
    assert env["JOBS_RADAR_DB_HOST"] == "db" and str(env["JOBS_RADAR_DB_PORT"]) == "5432"
    assert env["JOBS_RADAR_ENV"] == "prod"
    assert services["worker"]["environment"]["JOBS_RADAR_DB_HOST"] == "db"
    # Secrets come from the volume written by the init service, never from the compose file.
    assert "JOBS_RADAR_CREDENTIAL_KEY" not in env and "JOBS_RADAR_DB_PASSWORD" not in env
    for name in ("db", "api", "worker"):
        assert services[name]["depends_on"].get("init", {}).get("condition") or name == "db"
    assert "host.docker.internal:host-gateway" in services["api"]["extra_hosts"]
    assert services["db"]["environment"]["POSTGRES_PASSWORD_FILE"] == "/secrets/db_password"


def test_the_release_secrets_live_in_a_named_volume() -> None:
    compose = _compose(RELEASE)
    assert "secrets" in compose["volumes"] and "pgdata" in compose["volumes"]


# --- demo compose ---------------------------------------------------------------------------------


def test_the_demo_is_self_contained_and_shares_no_volume_with_the_release() -> None:
    services = _services(DEMO)
    assert {"db", "seed", "worker", "api", "frontend"} <= set(services)
    assert "demo_seed" in " ".join(services["seed"]["command"])
    assert "idle_worker" in " ".join(services["worker"]["command"])
    assert set(_compose(DEMO)["volumes"]).isdisjoint(_compose(RELEASE)["volumes"])
    assert [name for name, s in services.items() if "ports" in s] == ["frontend"]
    assert _compose(DEMO)["name"] != _compose(RELEASE)["name"]


@pytest.mark.parametrize("path", [RELEASE, DEMO])
def test_every_setting_a_compose_file_passes_exists(path: Path) -> None:
    # SECRETS_DIR is read by the image's entrypoint, not by the application settings.
    known = {f"JOBS_RADAR_{name.upper()}" for name in Settings.model_fields} | {
        "JOBS_RADAR_SECRETS_DIR"
    }
    for name, service in _services(path).items():
        env = service.get("environment") or {}
        for key in env:
            if key.startswith("JOBS_RADAR_"):
                assert key in known, f"{path.name}: {name} sets unknown {key}"

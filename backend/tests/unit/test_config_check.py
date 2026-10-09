"""The configuration check: exposure, secrets and permissions (T8.2, document 08)."""

from cryptography.fernet import Fernet

from jobs_radar.tools.config_check import Finding, check

GOOD = {
    "JOBS_RADAR_DB_PASSWORD": "a-long-random-password-1234",
    "JOBS_RADAR_CREDENTIAL_KEY": Fernet.generate_key().decode(),
    "JOBS_RADAR_API_BIND": "127.0.0.1",
    "JOBS_RADAR_DB_BIND": "127.0.0.1",
    "JOBS_RADAR_CORS_ORIGINS": '["http://127.0.0.1:5180"]',
    "JOBS_RADAR_FRONTEND_ALLOWED_HOSTS": "localhost,127.0.0.1",
}


def levels(findings: list[Finding]) -> dict[str, str]:
    return {f.code: f.level for f in findings}


def test_a_loopback_configuration_has_no_warning_or_failure() -> None:
    found = check(GOOD, env_file_mode=0o600)
    assert {f.level for f in found} <= {"ok", "info"}


def test_exposing_the_api_or_the_database_is_a_warning_with_the_reason() -> None:
    found = check(
        {**GOOD, "JOBS_RADAR_API_BIND": "0.0.0.0", "JOBS_RADAR_DB_BIND": "192.168.0.5"},
        env_file_mode=0o600,
    )
    assert levels(found)["api_bind"] == "warn" and levels(found)["db_bind"] == "warn"
    api = next(f for f in found if f.code == "api_bind")
    assert "authentication" in api.message


def test_a_missing_key_is_a_warning_and_a_malformed_key_a_failure() -> None:
    missing = {k: v for k, v in GOOD.items() if k != "JOBS_RADAR_CREDENTIAL_KEY"}
    assert levels(check(missing, env_file_mode=0o600))["credential_key"] == "warn"
    assert (
        levels(check({**GOOD, "JOBS_RADAR_CREDENTIAL_KEY": "not-a-key"}, env_file_mode=0o600))[
            "credential_key"
        ]
        == "fail"
    )


def test_the_env_file_must_be_private() -> None:
    assert levels(check(GOOD, env_file_mode=0o644))["env_file"] == "fail"
    assert levels(check(GOOD, env_file_mode=0o600))["env_file"] == "ok"
    assert "env_file" not in levels(check(GOOD, env_file_mode=None))


def test_wildcards_in_origins_or_hosts_fail() -> None:
    assert (
        levels(check({**GOOD, "JOBS_RADAR_CORS_ORIGINS": '["*"]'}, env_file_mode=0o600))["cors"]
        == "fail"
    )
    assert (
        levels(check({**GOOD, "JOBS_RADAR_FRONTEND_ALLOWED_HOSTS": "all"}, env_file_mode=0o600))[
            "allowed_hosts"
        ]
        == "fail"
    )


def test_a_short_database_password_fails_outside_development() -> None:
    weak = {**GOOD, "JOBS_RADAR_DB_PASSWORD": "short", "JOBS_RADAR_ENV": "prod"}
    assert levels(check(weak, env_file_mode=0o600))["db_password"] == "fail"
    assert "db_password" not in {
        f.code
        for f in check({**GOOD, "JOBS_RADAR_DB_PASSWORD": "short"}, env_file_mode=0o600)
        if f.level == "fail"
    }


def test_local_providers_are_reported() -> None:
    found = check({**GOOD, "JOBS_RADAR_ALLOW_LOCAL_PROVIDERS": "true"}, env_file_mode=0o600)
    assert levels(found)["local_providers"] == "info"

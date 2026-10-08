"""The development watchlist (research R-00169) is plain data: check it stays valid."""

import re

import pytest
from pydantic import SecretStr

from jobs_radar.core.settings import Settings
from jobs_radar.tools.seed_dev_sources import DEV_BOARDS, check_environment

TOKEN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def test_the_watchlist_has_the_14_verified_boards() -> None:
    assert len(DEV_BOARDS) == 14
    assert {token for token, _ in DEV_BOARDS} >= {"anthropic", "databricks", "stripe", "gitlab"}


def test_tokens_are_unique_and_valid_for_the_adapter() -> None:
    tokens = [token for token, _ in DEV_BOARDS]
    assert len(set(tokens)) == len(tokens)
    assert all(TOKEN.match(token) for token in tokens)


def test_every_board_has_a_display_name() -> None:
    assert all(name.strip() for _, name in DEV_BOARDS)


def test_seeding_is_refused_outside_development() -> None:
    check_environment(Settings(_env_file=None, db_password=SecretStr("x"), env="dev"))  # type: ignore[call-arg]
    for env in ("test", "prod"):
        settings = Settings(
            _env_file=None,
            db_password=SecretStr("x"),
            db_name="seed_test",
            env=env,  # type: ignore[call-arg, arg-type]
        )
        with pytest.raises(SystemExit, match="Refusing"):
            check_environment(settings)

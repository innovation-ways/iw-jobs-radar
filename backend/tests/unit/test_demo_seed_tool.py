"""The demo seed command only ever touches a database that is clearly the demo one."""

import pytest
from pydantic import SecretStr

from jobs_radar.core.settings import Settings
from jobs_radar.tools.demo_seed import check_environment


def _settings(**values: object) -> Settings:
    return Settings(_env_file=None, db_password=SecretStr("x"), **values)  # type: ignore[call-arg, arg-type]


def test_the_demo_database_in_development_is_accepted() -> None:
    check_environment(_settings(env="dev", db_name="jobs_radar_demo"))


@pytest.mark.parametrize("name", ["jobs_radar", "postgres", "demo", "jobs_radar_demo_old"])
def test_any_other_database_name_is_refused(name: str) -> None:
    with pytest.raises(SystemExit, match="Refusing"):
        check_environment(_settings(env="dev", db_name=name))


def test_other_environments_are_refused() -> None:
    with pytest.raises(SystemExit, match="Refusing"):
        check_environment(_settings(env="prod", db_name="jobs_radar_demo"))

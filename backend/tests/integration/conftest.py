import pytest

from tests.conftest import TEST_DATABASE_URL
from tests.worker_resources import ensure_database


@pytest.fixture(scope="session", autouse=True)
def worker_database() -> None:
    """Every integration test can reach this worker's database, whichever test runs first.

    A serial run's database already exists; under pytest-xdist each worker's
    ``studio_test_<worker id>`` is created here on first use.
    """
    ensure_database(TEST_DATABASE_URL)

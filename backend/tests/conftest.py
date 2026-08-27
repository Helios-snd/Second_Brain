import pytest
from pydantic_ai import models


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _model_requests_guard(request: pytest.FixtureRequest) -> object:
    """Block real LLM calls in the fast suite; allow them only for tests marked
    `integration`. Set per-test (not module-level) so the flag can't leak from a
    unit test into an integration test sharing the session."""
    allowed = request.node.get_closest_marker("integration") is not None
    saved = models.ALLOW_MODEL_REQUESTS
    models.ALLOW_MODEL_REQUESTS = allowed
    yield
    models.ALLOW_MODEL_REQUESTS = saved

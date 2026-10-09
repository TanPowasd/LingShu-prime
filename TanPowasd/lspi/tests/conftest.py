import warnings
import pytest

warnings.filterwarnings("ignore", message=r"\[issue156\]")


@pytest.fixture
def engine():
    from lingshu.core.core import SpacetimeMemoryEngine
    e = SpacetimeMemoryEngine(":memory:")
    yield e
    try:
        e.close()
    except Exception:
        pass

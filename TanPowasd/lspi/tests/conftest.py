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


# ---------- 大脑宿主（dsh-memory md_cg）：LSPI_BRAIN_SRC 指向 dsh-memory 仓根 ----------
import os
import sys
import tempfile


def _brain_available():
    src = os.environ.get("LSPI_BRAIN_SRC")
    if src and src not in sys.path:
        sys.path.insert(0, src)
    try:
        import md_cg.mcp_server  # noqa: F401
        return True
    except Exception:
        return False


def make_brain(ops_allow=("read", "write"), can_write=True):
    from md_cg.mdcos import MdCGSecure
    from md_cg.security import Principal
    p = Principal(actor="lspi-test", can_write=can_write, role="recorder",
                  ops_allow=tuple(ops_allow), session="lspi")
    return MdCGSecure(tempfile.mkdtemp(prefix="lspi_brain_"), principal=p)


@pytest.fixture
def brain():
    if not _brain_available():
        pytest.skip("未提供 dsh-memory（设 LSPI_BRAIN_SRC=<dsh-memory 仓根>）")
    return make_brain()

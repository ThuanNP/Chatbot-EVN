"""Cấu hình dùng chung cho pytest trong thư mục tests/."""

import warnings
import pytest
from pydantic.warnings import PydanticDeprecatedSince20
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base, dat_engine


def pytest_configure(config: pytest.Config) -> None:
    """Cấu hình bộ lọc cảnh báo và tham số cho pytest."""
    # Bỏ qua cảnh báo deprecation từ Pydantic V2 do thư viện phụ thuộc LiteLLM gây ra
    config.addinivalue_line(
        "filterwarnings",
        "ignore::pydantic.warnings.PydanticDeprecatedSince20",
    )
    # Bỏ qua cảnh báo PytestDeprecationWarning về asyncio_default_fixture_loop_scope nếu chưa set qua file ini
    config.addinivalue_line(
        "filterwarnings",
        "ignore::pytest.PytestDeprecationWarning:pytest_asyncio.*",
    )


@pytest.fixture(autouse=True)
def thiet_lap_co_so_du_lieu_in_memory():
    """Thiết lập SQLite in-memory tự động cho toàn bộ các ca kiểm thử."""
    test_engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    dat_engine(test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)

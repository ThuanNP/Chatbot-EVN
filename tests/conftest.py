"""Cấu hình dùng chung cho pytest trong thư mục tests/."""

import warnings
import pytest
from pydantic.warnings import PydanticDeprecatedSince20


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

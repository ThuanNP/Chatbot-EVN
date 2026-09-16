"""Quản lý kết nối cơ sở dữ liệu và các mô hình dữ liệu cho Chatbot EVN.

Sử dụng SQLAlchemy 2.0 để quản lý kết nối PostgreSQL (sản xuất)
và hỗ trợ SQLite (môi trường kiểm thử hoặc fallback cục bộ).
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import logging
from typing import Generator, Optional

import uuid
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.config import lay_cau_hinh

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Lớp cơ sở cho toàn bộ các model SQLAlchemy."""
    pass


class HoiThoai(Base):
    """Mô hình bảng phiên hội thoại của người dùng."""

    __tablename__ = "hoi_thoai"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    nguoi_dung_id: Mapped[str] = mapped_column(
        String(100),
        default="khach",
        nullable=False,
    )
    tieu_de: Mapped[str] = mapped_column(
        String(255),
        default="Cuộc trò chuyện mới",
        nullable=False,
    )
    tao_luc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    cap_nhat_luc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Quan hệ một-nhiều với TinNhan, tự động xoá cascade khi phiên hội thoại bị xoá
    tin_nhan: Mapped[list["TinNhan"]] = relationship(
        "TinNhan",
        back_populates="hoi_thoai",
        cascade="all, delete-orphan",
        order_by="TinNhan.tao_luc",
    )

    __table_args__ = (
        # Chỉ mục phục vụ tra cứu danh sách hội thoại của người dùng theo thời gian cập nhật
        Index("ix_hoi_thoai_nguoi_dung_cap_nhat", "nguoi_dung_id", "cap_nhat_luc"),
    )


class TinNhan(Base):
    """Mô hình bảng tin nhắn trong từng phiên hội thoại."""

    __tablename__ = "tin_nhan"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    hoi_thoai_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("hoi_thoai.id", ondelete="CASCADE"),
        nullable=False,
    )
    vai_tro: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    noi_dung: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    token_uoc_tinh: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    tang_phuc_vu: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    tao_luc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Quan hệ ngược lại với phiên hội thoại
    hoi_thoai: Mapped["HoiThoai"] = relationship(
        "HoiThoai",
        back_populates="tin_nhan",
    )

    __table_args__ = (
        # Chỉ mục phục vụ lấy danh sách tin nhắn theo thứ tự thời gian trong cuộc hội thoại
        Index("ix_tin_nhan_hoi_thoai_tao_luc", "hoi_thoai_id", "tao_luc"),
        # Ràng buộc vai trò chỉ được phép là 'user' hoặc 'assistant'
        CheckConstraint(
            "vai_tro IN ('user', 'assistant')",
            name="ck_tin_nhan_vai_tro",
        ),
    )


class LuotGoi(Base):
    """Mô hình bảng ghi nhận lịch sử và chi phí của từng lượt gọi mô hình."""

    __tablename__ = "luot_goi"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thoi_diem: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    nguoi_dung_id: Mapped[str] = mapped_column(
        String(100),
        default="khach",
        nullable=False,
    )
    tang: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    model: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    token_vao: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    token_ra: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    chi_phi_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    do_tre_ms: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    thanh_cong: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )
    ghi_chu: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    __table_args__ = (
        # Chỉ mục phục vụ truy vấn theo mốc thời gian (ví dụ: thống kê hôm nay, 1 giờ gần nhất)
        Index("ix_luot_goi_thoi_diem", "thoi_diem"),
        # Chỉ mục phức hợp phục vụ tra cứu lịch sử theo người dùng và thời điểm
        Index("ix_luot_goi_nguoi_dung_thoi_diem", "nguoi_dung_id", "thoi_diem"),
    )


# Quản lý Engine và SessionFactory dưới dạng singleton
_engine = None
_session_factory = None


def tao_engine(database_url: Optional[str] = None):
    """Khởi tạo engine SQLAlchemy từ chuỗi kết nối cấu hình."""
    if not database_url:
        try:
            database_url = lay_cau_hinh().env.DATABASE_URL
        except Exception:
            database_url = "sqlite:///chatbot_evn.db"

    # Kết nối SQLite cần cấu hình check_same_thread=False
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            echo=False,
        )

    # Kết nối PostgreSQL với hồ chứa kết nối (connection pool)
    try:
        return create_engine(
            database_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            echo=False,
        )
    except Exception as e:
        logger.warning(
            f"Không thể khởi tạo engine với DATABASE_URL={database_url}: {e}. Chuyển sang SQLite cục bộ."
        )
        return create_engine(
            "sqlite:///chatbot_evn.db",
            connect_args={"check_same_thread": False},
            echo=False,
        )


def lay_engine():
    """Lấy hoặc tạo mới engine kết nối cơ sở dữ liệu (singleton)."""
    global _engine, _session_factory
    if _engine is None:
        _engine = tao_engine()
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        try:
            Base.metadata.create_all(bind=_engine)
        except Exception as e:
            logger.warning(f"Lỗi tự động tạo bảng: {e}")
    return _engine


def dat_engine(engine_moi) -> None:
    """Thiết lập engine mới (hữu ích cho môi trường kiểm thử SQLite in-memory)."""
    global _engine, _session_factory
    _engine = engine_moi
    _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    try:
        Base.metadata.create_all(bind=_engine)
    except Exception as e:
        logger.warning(f"Lỗi tự động tạo bảng khi dat_engine: {e}")


def lay_session_factory() -> sessionmaker[Session]:
    """Lấy Session factory đã khởi tạo."""
    global _session_factory
    if _session_factory is None:
        lay_engine()
    return _session_factory  # type: ignore


@contextmanager
def lay_phien_db() -> Generator[Session, None, None]:
    """Context manager cung cấp phiên làm việc cơ sở dữ liệu với tự động commit/rollback."""
    factory = lay_session_factory()
    phien: Session = factory()
    try:
        yield phien
        phien.commit()
    except Exception:
        phien.rollback()
        raise
    finally:
        phien.close()


def khoi_tao_db() -> None:
    """Tạo tất cả các bảng trong cơ sở dữ liệu nếu chưa tồn tại."""
    try:
        engine = lay_engine()
        Base.metadata.create_all(bind=engine)
        logger.info("Đã khởi tạo/kiểm tra lược đồ cơ sở dữ liệu thành công.")
    except Exception as e:
        logger.error(f"Lỗi khi khởi tạo cơ sở dữ liệu: {e}")
        # Nếu postgres lỗi kết nối, chuyển sang SQLite cục bộ
        global _engine, _session_factory
        logger.warning("Chuyển fallback sang SQLite chatbot_evn.db...")
        _engine = create_engine("sqlite:///chatbot_evn.db", connect_args={"check_same_thread": False})
        _session_factory = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
        Base.metadata.create_all(bind=_engine)
        logger.info("Đã tạo bảng trên SQLite cục bộ thành công.")

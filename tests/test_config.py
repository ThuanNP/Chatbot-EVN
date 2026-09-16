"""Bộ kiểm thử đơn vị cho cấu hình hệ thống (app/config.py và config/models.yaml).

Kiểm tra:
- Nạp đúng 4 tầng trong chuỗi dự phòng
- Kiểm tra các tham số cài đặt chung
- Đảm bảo không có giá trị mặc định cho bất kỳ khoá API nào
- Kiểm tra các phương thức truy vấn tầng và khoá API
"""

import pytest
from pydantic import ValidationError
from pydantic_core import PydanticUndefined

from app.config import (
    CaiDatMoiTruong,
    CauHinhModels,
    doc_cau_hinh_models,
    lay_cau_hinh,
)


def test_khong_co_gia_tri_mac_dinh_cho_khoa_api():
    """Đảm bảo quy tắc bất biến: Không đặt giá trị mặc định cho bất kỳ khoá API nào."""
    cac_khoa_api = [
        "GOOGLE_API_KEY",
        "OPENROUTER_API_KEY",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
    ]
    for ten_khoa in cac_khoa_api:
        field_info = CaiDatMoiTruong.model_fields[ten_khoa]
        assert field_info.is_required(), f"Khoá API {ten_khoa} phải là bắt buộc (is_required=True)"
        assert field_info.default is None or field_info.default == PydanticUndefined, (
            f"Khoá API {ten_khoa} không được có giá trị mặc định!"
        )


def test_cai_dat_moi_truong_thieu_khoa_that_bai():
    """Khi khởi tạo mà thiếu khoá API, Pydantic phải báo lỗi ValidationError."""
    with pytest.raises(ValidationError):
        # Truyền rỗng để kiểm tra tính bắt buộc
        CaiDatMoiTruong(
            _env_file=None,
            GOOGLE_API_KEY=None,  # type: ignore
        )


def test_doc_cau_hinh_models_yaml():
    """Kiểm tra nạp tệp config/models.yaml và các tầng trong chuỗi dự phòng."""
    cau_hinh_models = doc_cau_hinh_models()
    assert isinstance(cau_hinh_models, CauHinhModels)

    # Phải có đủ 4 tầng
    assert len(cau_hinh_models.chuoi_du_phong) == 4

    # Kiểm tra thứ tự và tên của từng tầng
    cac_tang = cau_hinh_models.chuoi_du_phong
    assert cac_tang[0].tang == 1
    assert cac_tang[0].ten == "gemini"
    assert cac_tang[0].api_key_env == "GOOGLE_API_KEY"
    assert cac_tang[0].gia_vao_usd_moi_trieu >= 0
    assert cac_tang[0].gia_ra_usd_moi_trieu >= 0
    assert cac_tang[0].timeout_giay > 0

    assert cac_tang[1].tang == 2
    assert cac_tang[1].ten == "openrouter_auto"
    assert cac_tang[1].api_key_env == "OPENROUTER_API_KEY"
    assert cac_tang[1].tham_so_them.get("cost_tier") == "low"

    assert cac_tang[2].tang == 3
    assert cac_tang[2].ten == "claude"
    assert cac_tang[2].api_key_env == "ANTHROPIC_API_KEY"

    assert cac_tang[3].tang == 4
    assert cac_tang[3].ten == "openai"
    assert cac_tang[3].api_key_env == "OPENAI_API_KEY"

    # Kiểm tra cài đặt chung
    chung = cau_hinh_models.cai_dat_chung
    assert chung.so_lan_thu_lai_moi_tang >= 1
    assert chung.giay_gian_cach_dau > 0
    assert chung.timeout_mac_dinh_giay > 0
    assert chung.gioi_han_token_ra > 0


def test_lay_cau_hinh_he_thong():
    """Kiểm tra đối tượng CauHinhHeThong và các phương thức tiện ích."""
    he_thong = lay_cau_hinh(nap_lai=True)
    assert he_thong is not None
    assert he_thong.models is not None
    assert he_thong.env is not None

    # Kiểm tra lấy tầng theo số
    tang_1 = he_thong.lay_tang_theo_so(1)
    assert tang_1 is not None
    assert tang_1.ten == "gemini"

    tang_khong_ton_tai = he_thong.lay_tang_theo_so(99)
    assert tang_khong_ton_tai is None

    # Kiểm tra lấy tầng theo tên
    tang_openrouter = he_thong.lay_tang_theo_ten("openrouter_auto")
    assert tang_openrouter is not None
    assert tang_openrouter.tang == 2

    # Kiểm tra lấy khoá API
    khoa_gemini = he_thong.lay_khoa_api("GOOGLE_API_KEY")
    assert bool(khoa_gemini)

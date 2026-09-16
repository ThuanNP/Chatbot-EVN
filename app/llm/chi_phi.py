"""Tính toán và theo dõi chi phí sử dụng token của các mô hình."""


def tinh_chi_phi_usd(
    token_vao: int,
    token_ra: int,
    gia_vao_moi_trieu: float,
    gia_ra_moi_trieu: float,
) -> float:
    """Tính toán chi phí ước tính (USD) dựa trên số lượng token và đơn giá mỗi triệu token.

    Args:
        token_vao: Số lượng token đầu vào (prompt tokens).
        token_ra: Số lượng token đầu ra (completion tokens).
        gia_vao_moi_trieu: Giá mỗi triệu token đầu vào (USD).
        gia_ra_moi_trieu: Giá mỗi triệu token đầu ra (USD).

    Returns:
        float: Chi phí ước tính bằng USD, làm tròn đến 8 chữ số thập phân.
    """
    chi_phi_vao = (token_vao / 1_000_000.0) * gia_vao_moi_trieu
    chi_phi_ra = (token_ra / 1_000_000.0) * gia_ra_moi_trieu
    tong_chi_phi = chi_phi_vao + chi_phi_ra
    return round(tong_chi_phi, 8)

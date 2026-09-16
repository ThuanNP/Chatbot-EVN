"""Bộ định tuyến duy nhất xử lý các cuộc gọi mô hình qua chuỗi dự phòng.

Tuân thủ nghiêm ngặt các quy tắc bất biến trong AGENTS.md:
- Phơi ra ĐÚNG MỘT hàm công khai: goi_mo_hinh
- Cấm ghi cứng tên model trong mã Python (toàn bộ nạp từ config/models.yaml)
- Mọi lượt gọi mô hình phải ghi lại: tầng phục vụ, model, token vào, token ra, chi phí, độ trễ
- Phân loại lỗi chính xác: Lỗi tạm thời (thử lại + rơi tầng), Lỗi vĩnh viễn (rơi tầng ngay), Lỗi đầu vào (ném lỗi)
"""

import asyncio
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
    overload,
)

import litellm
from litellm.exceptions import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    ContentPolicyViolationError,
    ContextWindowExceededError,
    InternalServerError,
    InvalidRequestError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)

from app.config import CauHinhTang, doc_cau_hinh_models
from app.llm.chi_phi import tinh_chi_phi_usd

# Tắt bớt thông tin gỡ lỗi thừa từ litellm
litellm.suppress_debug_info = True

logger = logging.getLogger(__name__)

# Cờ ghi nhận việc kiểm tra khoá một lần duy nhất lúc khởi động
_da_kiem_tra_khoi_dong = False

TNoiDung = TypeVar("TNoiDung", bound=Union[str, AsyncIterator[str]])


@dataclass
class KetQuaGoi(Generic[TNoiDung]):
    """Kết quả trả về sau khi gọi mô hình qua bộ định tuyến."""

    noi_dung: TNoiDung
    tang_phuc_vu: int
    ten_model: str
    token_vao: int
    token_ra: int
    do_tre_ms: float
    so_lan_thu: int
    danh_sach_tang_da_hong: List[Dict[str, Any]] = field(default_factory=list)
    chi_phi_usd: float = 0.0


@dataclass
class ManhPhatRa:
    """Đại diện cho một mảnh được phát ra từ luồng mô hình theo dòng.

    Có ba dạng chính:
    - Mảnh nội dung (loai='manh'): Chứa đoạn văn bản mới (doan_van_ban).
    - Mảnh kết thúc (loai='xong'): Chứa toàn bộ siêu dữ liệu cuộc gọi (KetQuaGoi).
    - Mảnh lỗi (loai='loi'): Chứa thông báo lỗi khi bị đứt gãy giữa chừng kèm văn bản đã nhận.
    """

    loai: Literal["manh", "xong", "loi"]
    doan_van_ban: str = ""
    ket_qua: Optional[KetQuaGoi[str]] = None
    thong_diep_loi: Optional[str] = None
    van_ban_da_nhan: str = ""

    # Các trường siêu dữ liệu trực tiếp tương thích hoàn toàn với KetQuaGoi:
    tang_phuc_vu: Optional[int] = None
    ten_model: Optional[str] = None
    token_vao: int = 0
    token_ra: int = 0
    do_tre_ms: float = 0.0
    so_lan_thu: int = 1
    danh_sach_tang_da_hong: List[Dict[str, Any]] = field(default_factory=list)
    chi_phi_usd: float = 0.0

    @property
    def noi_dung(self) -> str:
        """Thuộc tính nội dung tương thích linh hoạt với cả 3 dạng mảnh."""
        if self.loai == "manh":
            return self.doan_van_ban
        if self.loai == "xong":
            return self.ket_qua.noi_dung if self.ket_qua else self.van_ban_da_nhan
        return self.van_ban_da_nhan

    @classmethod
    def tao_manh_noi_dung(cls, doan_van_ban: str) -> "ManhPhatRa":
        """Tạo mảnh nội dung mới."""
        return cls(loai="manh", doan_van_ban=doan_van_ban)

    @classmethod
    def tao_manh_ket_thuc(cls, ket_qua: KetQuaGoi[str]) -> "ManhPhatRa":
        """Tạo mảnh kết thúc mang đầy đủ siêu dữ liệu cuộc gọi."""
        return cls(
            loai="xong",
            ket_qua=ket_qua,
            tang_phuc_vu=ket_qua.tang_phuc_vu,
            ten_model=ket_qua.ten_model,
            token_vao=ket_qua.token_vao,
            token_ra=ket_qua.token_ra,
            do_tre_ms=ket_qua.do_tre_ms,
            so_lan_thu=ket_qua.so_lan_thu,
            danh_sach_tang_da_hong=list(ket_qua.danh_sach_tang_da_hong),
            chi_phi_usd=ket_qua.chi_phi_usd,
            van_ban_da_nhan=ket_qua.noi_dung,
        )

    @classmethod
    def tao_manh_loi(cls, thong_diep_loi: str, van_ban_da_nhan: str = "") -> "ManhPhatRa":
        """Tạo mảnh lỗi khi bị đứt gãy giữa chừng kèm phần văn bản đã nhận được."""
        return cls(
            loai="loi",
            thong_diep_loi=thong_diep_loi,
            van_ban_da_nhan=van_ban_da_nhan,
        )


class TatCaTangDeuHongError(Exception):
    """Ngoại lệ khi toàn bộ các tầng trong chuỗi dự phòng đều thất bại."""

    def __init__(
        self,
        thong_tin_that_bai: List[Dict[str, Any]],
        thong_diep: str = "Tất cả các tầng mô hình đều thất bại",
    ):
        self.thong_tin_that_bai = thong_tin_that_bai
        chi_tiet = "; ".join(
            f"Tầng {t.get('tang')} ({t.get('ten')} - {t.get('model')}): {t.get('ly_do')}"
            for t in thong_tin_that_bai
        )
        super().__init__(f"{thong_diep}: [{chi_tiet}]")


class LoiDauVaoError(Exception):
    """Ngoại lệ khi dữ liệu đầu vào không hợp lệ (400, prompt quá dài, nội dung bị chặn) - KHÔNG rơi tầng."""

    pass


def _phan_loai_loi(e: Exception) -> str:
    """Phân loại ngoại lệ thành một trong 3 nhóm: 'dau_vao', 'vinh_vien', 'tam_thoi'.

    - dau_vao: 400, context window, content filter (không thử lại, không rơi tầng, ném lỗi ngay).
    - vinh_vien: 401, 403, 404 (không thử lại, rơi xuống tầng sau ngay).
    - tam_thoi: 429, 500, 502, 503, 504, timeout, mạng (thử lại với backoff, hết lượt rơi tầng).
    """
    ma_trang_thai = getattr(e, "status_code", None)

    # 1. Nhóm lỗi do dữ liệu đầu vào (400, 422, độ dài ngữ cảnh, chính sách nội dung)
    if isinstance(
        e,
        (
            BadRequestError,
            ContextWindowExceededError,
            ContentPolicyViolationError,
            InvalidRequestError,
        ),
    ) or ma_trang_thai in (400, 422):
        return "dau_vao"

    # 2. Nhóm lỗi vĩnh viễn (401 sai khoá, 403 không có quyền, 404 sai model)
    if isinstance(
        e,
        (
            AuthenticationError,
            PermissionDeniedError,
            NotFoundError,
        ),
    ) or ma_trang_thai in (401, 403, 404):
        return "vinh_vien"

    # 3. Nhóm lỗi tạm thời (429 rate limit, 5xx server lỗi, timeout, đứt kết nối mạng)
    if isinstance(
        e,
        (
            RateLimitError,
            InternalServerError,
            ServiceUnavailableError,
            Timeout,
            APIConnectionError,
            asyncio.TimeoutError,
            ConnectionError,
        ),
    ) or ma_trang_thai in (429, 500, 502, 503, 504, 529):
        return "tam_thoi"

    # Các mã HTTP 4xx khác (nếu có) thường là lỗi yêu cầu người dùng
    if isinstance(ma_trang_thai, int) and 400 <= ma_trang_thai < 500:
        return "dau_vao"

    # Mặc định coi là lỗi tạm thời để có cơ hội thử lại và rơi tầng dự phòng
    return "tam_thoi"


def _kiem_tra_khoa_khoi_dong(chuoi_du_phong: List[CauHinhTang]) -> None:
    """Ghi nhật ký thông tin một lần duy nhất lúc khởi động cho các tầng thiếu khoá API."""
    global _da_kiem_tra_khoi_dong
    if _da_kiem_tra_khoi_dong:
        return
    for tang in chuoi_du_phong:
        khoa = os.getenv(tang.api_key_env)
        if not khoa:
            logger.info(
                f"[Khởi động] Tầng {tang.tang} ({tang.ten} - {tang.model}) thiếu khoá API "
                f"trong môi trường ({tang.api_key_env}), sẽ bỏ qua khi định tuyến."
            )
    _da_kiem_tra_khoi_dong = True


async def _tao_luong_phat(
    phan_hoi_stream: Any,
    chunk_dau: Any,
    tang: CauHinhTang,
    so_lan_thu: int,
    thoi_gian_bat_dau: float,
) -> AsyncIterator[str]:
    """Tạo generator bất đồng bộ phát từng đoạn text và ghi nhận log khi hoàn tất luồng stream."""
    tong_token_vao = 0
    tong_token_ra = 0

    # Phát đoạn văn bản từ chunk đầu tiên (đã fetch trước để xác thực kết nối)
    if chunk_dau is not None:
        if hasattr(chunk_dau, "choices") and chunk_dau.choices:
            delta = getattr(chunk_dau.choices[0], "delta", None)
            noi_dung_dau = getattr(delta, "content", None) if delta else None
            if noi_dung_dau:
                cac_manh_dau = re.findall(r"\S+\s*|\s+", noi_dung_dau) or [noi_dung_dau]
                for manh in cac_manh_dau:
                    yield manh
                    await asyncio.sleep(0.02)
        usage_dau = getattr(chunk_dau, "usage", None)
        if usage_dau:
            tong_token_vao = getattr(usage_dau, "prompt_tokens", 0) or 0
            tong_token_ra = getattr(usage_dau, "completion_tokens", 0) or 0

    # Phát các chunk tiếp theo
    async for chunk in phan_hoi_stream:
        if hasattr(chunk, "choices") and chunk.choices:
            delta = getattr(chunk.choices[0], "delta", None)
            doan_text = getattr(delta, "content", None) if delta else None
            if doan_text:
                cac_manh = re.findall(r"\S+\s*|\s+", doan_text) or [doan_text]
                for manh in cac_manh:
                    yield manh
                    await asyncio.sleep(0.02)
        usage = getattr(chunk, "usage", None)
        if usage:
            tong_token_vao = getattr(usage, "prompt_tokens", 0) or tong_token_vao
            tong_token_ra = getattr(usage, "completion_tokens", 0) or tong_token_ra

    # Tính độ trễ và chi phí khi luồng phát kết thúc
    do_tre_ms = (time.perf_counter() - thoi_gian_bat_dau) * 1000.0
    chi_phi_usd = tinh_chi_phi_usd(
        tong_token_vao,
        tong_token_ra,
        tang.gia_vao_usd_moi_trieu,
        tang.gia_ra_usd_moi_trieu,
    )
    logger.info(
        f"[Streaming] Hoàn tất luồng phát từ tầng {tang.tang} ({tang.model}): "
        f"{tong_token_vao} token vào, {tong_token_ra} token ra, "
        f"chi phí ước tính: ${chi_phi_usd:.8f}, độ trễ: {do_tre_ms:.2f}ms"
    )


@overload
async def goi_mo_hinh(
    tin_nhan: list[dict], phat_theo_dong: Literal[True], **tuy_chon
) -> KetQuaGoi[AsyncIterator[str]]: ...


@overload
async def goi_mo_hinh(
    tin_nhan: list[dict], phat_theo_dong: Literal[False] = False, **tuy_chon
) -> KetQuaGoi[str]: ...


@overload
async def goi_mo_hinh(
    tin_nhan: list[dict], phat_theo_dong: bool = False, **tuy_chon
) -> KetQuaGoi[Any]: ...


async def goi_mo_hinh(
    tin_nhan: list[dict], phat_theo_dong: bool = False, **tuy_chon
) -> KetQuaGoi[Any]:
    """Hàm duy nhất gọi mô hình qua chuỗi dự phòng định nghĩa trong config/models.yaml.

    Args:
        tin_nhan: Danh sách tin nhắn theo chuẩn OpenAI [{'role': 'user', 'content': '...'}]
        phat_theo_dong: Nếu True, phản hồi được phát theo dòng (AsyncIterator[str])
        **tuy_chon: Các tham số tuỳ chọn bổ sung (temperature, max_tokens, etc.)

    Returns:
        KetQuaGoi: Đối tượng dataclass chứa nội dung phản hồi, tầng phục vụ, token, chi phí, độ trễ.

    Raises:
        LoiDauVaoError: Khi gặp lỗi do dữ liệu đầu vào không hợp lệ (400, prompt quá dài).
        TatCaTangDeuHongError: Khi toàn bộ các tầng trong chuỗi dự phòng đều thất bại.
    """
    cau_hinh = doc_cau_hinh_models()
    chuoi_du_phong = cau_hinh.chuoi_du_phong
    cai_dat_chung = cau_hinh.cai_dat_chung

    # Kiểm tra và ghi log tầng thiếu khoá một lần duy nhất lúc khởi động
    _kiem_tra_khoa_khoi_dong(chuoi_du_phong)

    danh_sach_tang_da_hong: List[Dict[str, Any]] = []
    so_lan_thu_lai = cai_dat_chung.so_lan_thu_lai_moi_tang
    giay_gian_cach = cai_dat_chung.giay_gian_cach_dau

    # Duyệt lần lượt từng tầng từ 1 đến 4 theo chuỗi dự phòng
    for tang in chuoi_du_phong:
        khoa_api = os.getenv(tang.api_key_env)
        if not khoa_api:
            # Thiếu khoá API trong môi trường -> bỏ qua lặng lẽ
            danh_sach_tang_da_hong.append({
                "tang": tang.tang,
                "ten": tang.ten,
                "model": tang.model,
                "ly_do": f"Thiếu biến môi trường chứa khoá API ({tang.api_key_env})",
            })
            continue

        # Chuẩn bị tham số cho lượt gọi tầng này
        tham_so_goi = dict(tang.tham_so_them or {})
        tham_so_goi.update(tuy_chon)
        if "max_tokens" not in tham_so_goi:
            tham_so_goi["max_tokens"] = cai_dat_chung.gioi_han_token_ra

        timeout_giay = tham_so_goi.pop("timeout", None) or tang.timeout_giay or cai_dat_chung.timeout_mac_dinh_giay

        # Vòng lặp thử lại trong cùng một tầng: lần 1 là lần chính, tiếp theo là số lần thử lại tối đa
        tong_so_lan_thu_tang_nay = so_lan_thu_lai + 1
        tang_thanh_cong = False

        for lan_thu in range(1, tong_so_lan_thu_tang_nay + 1):
            thoi_gian_bat_dau = time.perf_counter()
            try:
                if phat_theo_dong:
                    # Gọi ở chế độ phát theo dòng
                    stream_raw = await litellm.acompletion(
                        model=tang.model,
                        messages=tin_nhan,
                        api_key=khoa_api,
                        timeout=timeout_giay,
                        stream=True,
                        stream_options={"include_usage": True},
                        **tham_so_goi,
                    )
                    stream_resp = cast(AsyncIterator[Any], stream_raw)
                    # Đọc trước chunk đầu tiên để xác nhận kết nối và quyền truy cập tầng này thành công
                    chunk_dau = await anext(stream_resp, None)

                    do_tre_khoi_tao_ms = (time.perf_counter() - thoi_gian_bat_dau) * 1000.0
                    luong_phat = _tao_luong_phat(
                        phan_hoi_stream=stream_resp,
                        chunk_dau=chunk_dau,
                        tang=tang,
                        so_lan_thu=lan_thu,
                        thoi_gian_bat_dau=thoi_gian_bat_dau,
                    )

                    # Trả về kết quả ngay khi luồng phát bắt đầu thành công
                    return KetQuaGoi(
                        noi_dung=luong_phat,
                        tang_phuc_vu=tang.tang,
                        ten_model=tang.model,
                        token_vao=0,
                        token_ra=0,
                        do_tre_ms=round(do_tre_khoi_tao_ms, 2),
                        so_lan_thu=lan_thu,
                        danh_sach_tang_da_hong=list(danh_sach_tang_da_hong),
                        chi_phi_usd=0.0,
                    )
                else:
                    # Gọi ở chế độ nhận toàn bộ phản hồi
                    phan_hoi_raw = await litellm.acompletion(
                        model=tang.model,
                        messages=tin_nhan,
                        api_key=khoa_api,
                        timeout=timeout_giay,
                        stream=False,
                        **tham_so_goi,
                    )
                    phan_hoi = cast(litellm.ModelResponse, phan_hoi_raw)
                    do_tre_ms = (time.perf_counter() - thoi_gian_bat_dau) * 1000.0

                    noi_dung = ""
                    if hasattr(phan_hoi, "choices") and phan_hoi.choices:
                        lua_chon_dau = phan_hoi.choices[0]
                        thong_diep = getattr(lua_chon_dau, "message", None)
                        if thong_diep:
                            noi_dung = getattr(thong_diep, "content", "") or ""

                    usage = getattr(phan_hoi, "usage", None)
                    token_vao = getattr(usage, "prompt_tokens", 0) if usage else 0
                    token_ra = getattr(usage, "completion_tokens", 0) if usage else 0

                    chi_phi_usd = tinh_chi_phi_usd(
                        token_vao=token_vao,
                        token_ra=token_ra,
                        gia_vao_moi_trieu=tang.gia_vao_usd_moi_trieu,
                        gia_ra_moi_trieu=tang.gia_ra_usd_moi_trieu,
                    )

                    # Ghi log bắt buộc theo Quy tắc 4 AGENTS.md
                    logger.info(
                        f"Phục vụ thành công từ tầng {tang.tang} ({tang.model}): "
                        f"{token_vao} token vào, {token_ra} token ra, "
                        f"chi phí ước tính: ${chi_phi_usd:.8f}, độ trễ: {do_tre_ms:.2f}ms"
                    )

                    return KetQuaGoi(
                        noi_dung=noi_dung,
                        tang_phuc_vu=tang.tang,
                        ten_model=tang.model,
                        token_vao=token_vao,
                        token_ra=token_ra,
                        do_tre_ms=round(do_tre_ms, 2),
                        so_lan_thu=lan_thu,
                        danh_sach_tang_da_hong=list(danh_sach_tang_da_hong),
                        chi_phi_usd=chi_phi_usd,
                    )

            except Exception as e:
                loai_loi = _phan_loai_loi(e)

                if loai_loi == "dau_vao":
                    # Lỗi do đầu vào: KHÔNG rơi tầng, ném lỗi lên trên ngay lập tức
                    logger.error(
                        f"Tầng {tang.tang} ({tang.ten}): Lỗi do đầu vào ({getattr(e, 'status_code', 'N/A')}): {e}"
                    )
                    raise LoiDauVaoError(f"Lỗi đầu vào từ mô hình ({tang.ten}): {e}") from e

                elif loai_loi == "vinh_vien":
                    # Lỗi vĩnh viễn: KHÔNG thử lại, ghi log cảnh báo, rơi xuống tầng sau ngay
                    logger.warning(
                        f"Tầng {tang.tang} ({tang.ten}): Gặp lỗi vĩnh viễn "
                        f"({getattr(e, 'status_code', 'N/A')}): {e}. Chuyển sang tầng tiếp theo."
                    )
                    danh_sach_tang_da_hong.append({
                        "tang": tang.tang,
                        "ten": tang.ten,
                        "model": tang.model,
                        "ly_do": f"Lỗi vĩnh viễn ({getattr(e, 'status_code', 'N/A')}): {e}",
                    })
                    break  # Ngắt vòng lặp thử lại, rơi tầng ngay

                else:
                    # Lỗi tạm thời: thử lại nếu còn lượt, hết lượt thì rơi tầng
                    if lan_thu < tong_so_lan_thu_tang_nay:
                        # Giãn cách tăng dần có nhiễu ngẫu nhiên (exponential backoff with jitter)
                        khoang_cho = (giay_gian_cach * (2 ** (lan_thu - 1))) + random.uniform(
                            0.0, 0.5 * giay_gian_cach
                        )
                        logger.warning(
                            f"Tầng {tang.tang} ({tang.ten}): Lỗi tạm thời lần {lan_thu}/{tong_so_lan_thu_tang_nay} "
                            f"({e}). Thử lại sau {khoang_cho:.2f}s..."
                        )
                        await asyncio.sleep(khoang_cho)
                        continue
                    else:
                        # Hết lượt thử lại cho tầng này
                        logger.warning(
                            f"Tầng {tang.tang} ({tang.ten}): Đã thử tối đa {lan_thu} lần nhưng vẫn gặp lỗi tạm thời: {e}. "
                            f"Rơi xuống tầng sau."
                        )
                        danh_sach_tang_da_hong.append({
                            "tang": tang.tang,
                            "ten": tang.ten,
                            "model": tang.model,
                            "ly_do": f"Lỗi tạm thời (hết {lan_thu} lần thử): {e}",
                        })
                        break

    # Nếu duyệt qua cả 4 tầng mà không tầng nào phục vụ thành công
    raise TatCaTangDeuHongError(thong_tin_that_bai=danh_sach_tang_da_hong)


async def goi_mo_hinh_theo_dong(
    tin_nhan: list[dict], **tuy_chon
) -> AsyncIterator[ManhPhatRa]:
    """Hàm gọi mô hình theo dòng qua chuỗi dự phòng nạp từ config/models.yaml.

    Phát ra các đối tượng ManhPhatRa:
    - Mảnh nội dung: loai='manh', doan_van_ban='...'
    - Mảnh kết thúc: loai='xong', ket_qua=KetQuaGoi(...), đầy đủ siêu dữ liệu
    - Mảnh lỗi: loai='loi', thong_diep_loi='...', van_ban_da_nhan='...' (khi lỗi giữa chừng)

    Xử lý đúng hai tình huống khó:
    1. Nếu tầng hiện tại lỗi TRƯỚC khi phát ra mảnh đầu tiên: rơi xuống tầng sau bình thường,
       người dùng không thấy gì bất thường.
    2. Nếu tầng hiện tại lỗi GIỮA CHỪNG, sau khi đã phát ra vài mảnh: KHÔNG được rơi tầng rồi
       phát lại từ đầu, vì người dùng sẽ thấy câu trả lời bị viết lại. Thay vào đó kết thúc luồng
       và phát ra một mảnh lỗi kèm phần văn bản đã nhận được. Ghi nhật ký rõ tình huống này.
    """
    cau_hinh = doc_cau_hinh_models()
    chuoi_du_phong = cau_hinh.chuoi_du_phong
    cai_dat_chung = cau_hinh.cai_dat_chung

    # Kiểm tra và ghi log tầng thiếu khoá một lần duy nhất lúc khởi động
    _kiem_tra_khoa_khoi_dong(chuoi_du_phong)

    danh_sach_tang_da_hong: List[Dict[str, Any]] = []
    so_lan_thu_lai = cai_dat_chung.so_lan_thu_lai_moi_tang
    giay_gian_cach = cai_dat_chung.giay_gian_cach_dau

    for tang in chuoi_du_phong:
        khoa_api = os.getenv(tang.api_key_env)
        if not khoa_api:
            # Thiếu khoá API trong môi trường -> bỏ qua lặng lẽ
            danh_sach_tang_da_hong.append({
                "tang": tang.tang,
                "ten": tang.ten,
                "model": tang.model,
                "ly_do": f"Thiếu biến môi trường chứa khoá API ({tang.api_key_env})",
            })
            continue

        # Chuẩn bị tham số cho lượt gọi tầng này
        tham_so_goi = dict(tang.tham_so_them or {})
        tham_so_goi.update(tuy_chon)
        if "max_tokens" not in tham_so_goi:
            tham_so_goi["max_tokens"] = cai_dat_chung.gioi_han_token_ra

        timeout_giay = (
            tham_so_goi.pop("timeout", None)
            or tang.timeout_giay
            or cai_dat_chung.timeout_mac_dinh_giay
        )

        tong_so_lan_thu_tang_nay = so_lan_thu_lai + 1

        for lan_thu in range(1, tong_so_lan_thu_tang_nay + 1):
            thoi_gian_bat_dau = time.perf_counter()
            da_phat_manh_dau = False
            cac_doan_van_ban: List[str] = []
            tong_token_vao = 0
            tong_token_ra = 0

            try:
                stream_raw = await litellm.acompletion(
                    model=tang.model,
                    messages=tin_nhan,
                    api_key=khoa_api,
                    timeout=timeout_giay,
                    stream=True,
                    stream_options={"include_usage": True},
                    **tham_so_goi,
                )
                stream_resp = cast(AsyncIterator[Any], stream_raw)

                async for chunk in stream_resp:
                    # Trích xuất nội dung văn bản mới từ chunk nếu có
                    doan_text = ""
                    if hasattr(chunk, "choices") and chunk.choices:
                        delta = getattr(chunk.choices[0], "delta", None)
                        if delta:
                            doan_text = getattr(delta, "content", "") or ""

                    # Ghi nhận số lượng token nếu có trong chunk
                    usage = getattr(chunk, "usage", None)
                    if usage:
                        tong_token_vao = getattr(usage, "prompt_tokens", 0) or tong_token_vao
                        tong_token_ra = getattr(usage, "completion_tokens", 0) or tong_token_ra

                    if doan_text:
                        # Tách nội dung thành các mảnh nhỏ (từ/cụm từ) và phát với nhịp độ tự nhiên (dần dần)
                        cac_manh_nho = re.findall(r"\S+\s*|\s+", doan_text) or [doan_text]
                        for manh_nho in cac_manh_nho:
                            da_phat_manh_dau = True
                            cac_doan_van_ban.append(manh_nho)
                            yield ManhPhatRa.tao_manh_noi_dung(manh_nho)
                            await asyncio.sleep(0.02)

            except Exception as e:
                if da_phat_manh_dau:
                    # TÌNH HUỐNG 2: Lỗi GIỮA CHỪNG sau khi đã phát ra vài mảnh:
                    # KHÔNG được rơi tầng rồi phát lại từ đầu, vì người dùng sẽ thấy câu trả lời bị viết lại.
                    # Thay vào đó kết thúc luồng và phát ra một mảnh lỗi kèm phần văn bản đã nhận được.
                    # Ghi nhật ký rõ tình huống này.
                    van_ban_da_nhan = "".join(cac_doan_van_ban)
                    logger.error(
                        f"[Streaming] Tầng {tang.tang} ({tang.ten} - {tang.model}) gặp lỗi GIỮA CHỪNG "
                        f"sau khi đã phát ra {len(cac_doan_van_ban)} mảnh dữ liệu: {e}. "
                        f"Dừng luồng ngay lập tức và phát mảnh lỗi, KHÔNG rơi tầng để tránh lặp nội dung. "
                        f"Văn bản đã nhận được ({len(van_ban_da_nhan)} ký tự)."
                    )
                    yield ManhPhatRa.tao_manh_loi(
                        thong_diep_loi=f"Lỗi gián đoạn khi đang truyền dữ liệu từ tầng {tang.tang} ({tang.ten}): {e}",
                        van_ban_da_nhan=van_ban_da_nhan,
                    )
                    return
                else:
                    # TÌNH HUỐNG 1: Lỗi TRƯỚC khi phát ra mảnh đầu tiên:
                    # Rơi xuống tầng sau bình thường, người dùng không thấy gì bất thường.
                    loai_loi = _phan_loai_loi(e)

                    if loai_loi == "dau_vao":
                        logger.error(
                            f"[Streaming] Tầng {tang.tang} ({tang.ten}): Lỗi do đầu vào ({getattr(e, 'status_code', 'N/A')}): {e}"
                        )
                        raise LoiDauVaoError(f"Lỗi đầu vào từ mô hình ({tang.ten}): {e}") from e

                    elif loai_loi == "vinh_vien":
                        logger.warning(
                            f"[Streaming] Tầng {tang.tang} ({tang.ten}): Gặp lỗi vĩnh viễn "
                            f"({getattr(e, 'status_code', 'N/A')}): {e}. Rơi xuống tầng tiếp theo."
                        )
                        danh_sach_tang_da_hong.append({
                            "tang": tang.tang,
                            "ten": tang.ten,
                            "model": tang.model,
                            "ly_do": f"Lỗi vĩnh viễn ({getattr(e, 'status_code', 'N/A')}): {e}",
                        })
                        break  # Rơi tầng ngay

                    else:  # tam_thoi
                        if lan_thu < tong_so_lan_thu_tang_nay:
                            khoang_cho = (giay_gian_cach * (2 ** (lan_thu - 1))) + random.uniform(
                                0.0, 0.5 * giay_gian_cach
                            )
                            logger.warning(
                                f"[Streaming] Tầng {tang.tang} ({tang.ten}): Lỗi tạm thời lần {lan_thu}/{tong_so_lan_thu_tang_nay} "
                                f"trước khi phát mảnh đầu ({e}). Thử lại sau {khoang_cho:.2f}s..."
                            )
                            await asyncio.sleep(khoang_cho)
                            continue
                        else:
                            logger.warning(
                                f"[Streaming] Tầng {tang.tang} ({tang.ten}): Đã thử tối đa {lan_thu} lần "
                                f"nhưng vẫn gặp lỗi tạm thời: {e}. Rơi xuống tầng sau."
                            )
                            danh_sach_tang_da_hong.append({
                                "tang": tang.tang,
                                "ten": tang.ten,
                                "model": tang.model,
                                "ly_do": f"Lỗi tạm thời (hết {lan_thu} lần thử): {e}",
                            })
                            break
            else:
                # Thành công trọn vẹn luồng stream từ tầng này!
                do_tre_ms = (time.perf_counter() - thoi_gian_bat_dau) * 1000.0
                van_ban_hoan_chinh = "".join(cac_doan_van_ban)

                # Ước tính token nếu provider không trả về qua chunk
                if tong_token_vao == 0:
                    tong_token_vao = max(
                        1,
                        sum(
                            len(str(m.get("content", "")).split())
                            for m in tin_nhan
                            if isinstance(m, dict)
                        ),
                    )
                if tong_token_ra == 0 and van_ban_hoan_chinh:
                    tong_token_ra = max(1, len(van_ban_hoan_chinh.split()))

                chi_phi_usd = tinh_chi_phi_usd(
                    token_vao=tong_token_vao,
                    token_ra=tong_token_ra,
                    gia_vao_moi_trieu=tang.gia_vao_usd_moi_trieu,
                    gia_ra_moi_trieu=tang.gia_ra_usd_moi_trieu,
                )

                # Ghi log bắt buộc theo Quy tắc 4 AGENTS.md
                logger.info(
                    f"Phục vụ thành công luồng phát từ tầng {tang.tang} ({tang.model}): "
                    f"{tong_token_vao} token vào, {tong_token_ra} token ra, "
                    f"chi phí ước tính: ${chi_phi_usd:.8f}, độ trễ: {do_tre_ms:.2f}ms"
                )

                ket_qua = KetQuaGoi(
                    noi_dung=van_ban_hoan_chinh,
                    tang_phuc_vu=tang.tang,
                    ten_model=tang.model,
                    token_vao=tong_token_vao,
                    token_ra=tong_token_ra,
                    do_tre_ms=round(do_tre_ms, 2),
                    so_lan_thu=lan_thu,
                    danh_sach_tang_da_hong=list(danh_sach_tang_da_hong),
                    chi_phi_usd=chi_phi_usd,
                )
                yield ManhPhatRa.tao_manh_ket_thuc(ket_qua)
                return

    # Nếu tất cả các tầng đều thất bại trước khi phát mảnh đầu
    raise TatCaTangDeuHongError(thong_tin_that_bai=danh_sach_tang_da_hong)


__all__ = [
    "goi_mo_hinh",
    "goi_mo_hinh_theo_dong",
    "KetQuaGoi",
    "ManhPhatRa",
    "TatCaTangDeuHongError",
    "LoiDauVaoError",
]

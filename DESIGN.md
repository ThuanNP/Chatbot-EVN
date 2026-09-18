# EVNHCMC — Chuẩn thiết kế nhận diện thương hiệu số

Tài liệu chuẩn thiết kế (design system & brand guidelines) cho các sản phẩm số
thuộc **Tổng công ty Điện lực TP.HCM (EVNHCMC)**, áp dụng thống nhất cho toàn bộ hệ thống EVN.

| Mục | Giá trị |
| --- | --- |
| Phiên bản | 2.0 (Official Standard) |
| Ngày ban hành | 2026-09-18 |
| Phạm vi | Giao diện web/app, ứng dụng văn phòng số và trợ lý ảo EVNHCMC |
| Trạng thái | Đã phê duyệt áp dụng |

---

## 1. Nền tảng thương hiệu

### 1.1. Sứ mệnh

> Đáp ứng đầy đủ nhu cầu về điện của khách hàng với chất lượng ngày càng cao và
> dịch vụ ngày càng hoàn hảo.

### 1.2. Tầm nhìn

Trở thành đơn vị cung cấp dịch vụ điện hàng đầu Việt Nam và khu vực, tiên phong
trong chuyển đổi số và phát triển lưới điện thông minh.

### 1.3. Bốn giá trị cốt lõi

| Giá trị | Diễn giải | Nguyên tắc áp dụng giao diện |
| --- | --- | --- |
| **Con người là nền tảng** | Minh bạch, chính trực trong quan hệ với khách hàng | Trực quan, dễ tiếp cận; mọi thông tin chỉ số, hóa đơn rõ ràng |
| **Trách nhiệm** | Ưu tiên quyền lợi hợp pháp của khách hàng | Luôn có lối thoát: quay lại, hủy bỏ, chuyển tiếp nhân viên hỗ trợ |
| **Tuân thủ pháp luật** | Chấp hành đúng quy định nhà nước và ngành điện | Ngôn ngữ chuẩn mực hành chính công; dữ liệu bảo mật tuyệt đối |
| **Phát triển bền vững** | Tiết kiệm năng lượng, thân thiện môi trường | Giao diện tinh gọn, tải nhanh, tối ưu hóa tiêu thụ năng lượng |

### 1.4. Tính cách thương hiệu

Tin cậy · Chuyên nghiệp · Tiên tiến · Minh bạch · Gần gũi.

Là doanh nghiệp dịch vụ công thiết yếu, giao diện EVNHCMC giữ phong cách trang
trọng, hiện đại, chuẩn mực, không dùng từ ngữ suồng sã hoặc biểu tượng cợt nhả.

---

## 2. Logo và nhận diện cốt lõi

### 2.1. Cấu trúc logo

Logo EVNHCMC là thể thống nhất gồm hai phần:

1. **Biểu tượng ba ngôi sao 4 cánh đồng tâm** đặt trong khối tròn xanh:
   - Ngôi sao trung tâm: **Vàng năng lượng** (`#FFC010` / `#FFF200`)
   - Ngôi sao tầng giữa: **Đỏ nhiệt huyết** (`#DB3030` / `#ED1C24`)
   - Ngôi sao tầng ngoài: **Xanh thẫm bền vững** (`#0C2657` / `#164397`)
2. **Khối chữ thương hiệu**:
   - `EVN`: Xanh truyền thống ngành điện
   - `HCMC`: Đỏ năng động của thành phố mang tên Bác

### 2.2. Quy tắc sử dụng logo

| Tiêu chí | Quy định chuẩn |
| --- | --- |
| **Vùng an toàn (Clear space)** | Tối thiểu 1/3 chiều cao logo ở 4 cạnh; cấm đặt text/graphic vào |
| **Kích thước tối thiểu trên web** | Chiều cao ≥ 36px cho thanh điều hướng, ≥ 94px cho khối nhận diện |
| **Nền đặt logo** | Nền trắng `#FFFFFF`, nền trung tính sáng `#F0F4F8`, hoặc xanh thẫm `#0C2657` |
| **Điều cấm kỵ** | Không tự vẽ lại, không bóp méo tỷ lệ, không đổi sắc thái màu biểu tượng |

---

## 3. Hệ thống màu sắc nhận diện (Color System)

### 3.1. Dải màu xanh chủ đạo (Primary Blue Ramp)

Màu xanh biểu trưng cho dòng điện, sự tin cậy công nghệ và dịch vụ công chuyên nghiệp.

| Tên biến | Mã HEX | Vai trò sử dụng |
| --- | --- | --- |
| `blue-dark-3` | `#0C2657` | Nền header thanh điều hướng, bề mặt tương phản cao, dark sidebar |
| `blue-dark-2` | `#083C90` | Trạng thái hover/active trên nền xanh thẫm |
| `blue-dark-1` | `#1254B7` | Gradient thương hiệu, đường kẻ viền nhấn |
| `blue-base` | `#016BF8` | **Màu thương hiệu chính (Primary):** Nút bấm, tab kích hoạt, link |
| `blue-light-1` | `#0498EC` | Màu phụ trợ (Cyan highlight), biểu đồ dữ liệu, tiến độ vòng xoay |
| `blue-light-2` | `#C3E7FE` | Nền badge nhạt, vùng chọn mềm, viền phụ |
| `blue-light-3` | `#E1F7FF` | Nền thông báo tin tức, highlight dòng dữ liệu |

### 3.2. Màu chức năng & trạng thái (Semantic Colors)

| Trạng thái | Tên biến | Mã HEX | Ý nghĩa nghiệp vụ |
| --- | --- | --- | --- |
| **Thành công (Success)** | `green-base` | `#00ED64` | Vận hành bình thường, hoàn thành chỉ số, kết nối tốt |
| **Nhấn thành công** | `green-dark-1` | `#00A35C` | Chữ trạng thái thành công trên nền sáng |
| **Nền thành công** | `green-light-2` | `#C0FAE6` | Nền badge trạng thái thành công |
| **Cảnh báo (Warning)** | `yellow-base` | `#FFC010` | Chờ xử lý, chậm tiến độ, hóa đơn chưa thanh toán |
| **Chữ cảnh báo** | `yellow-dark-2` | `#944F01` | Chữ cảnh báo đạt chuẩn tương phản |
| **Nền cảnh báo** | `yellow-light-3` | `#FEF7D8` | Nền badge công việc chờ duyệt |
| **Nguy hiểm/Lỗi (Danger)** | `red-base` | `#DB3030` | Mất điện, báo sự cố, lỗi kết nối, nút thao tác hủy |
| **Nền cảnh báo lỗi** | `red-light-3` | `#FFEAE5` | Nền thông báo mất điện, lỗi hệ thống |
| **Nhánh nghiệp vụ** | `purple-base` | `#B45AF2` | Quy trình quản trị đặc biệt, nhãn điều hành |

### 3.3. Dải màu trung tính (Neutral Gray Scale)

| Tên biến | Mã HEX | Ứng dụng |
| --- | --- | --- |
| `white` | `#FFFFFF` | Nền thẻ (card), nền sidebar trắng, chữ trên nền đậm |
| `gray-light-3` | `#F9FBFA` | Nền canvas ứng dụng phụ |
| `gray-light-2` | `#E8EDEB` | Đường viền phân cách card (`border`), divider |
| `gray-light-1` | `#C1C7C6` | Đường viền ô nhập liệu khi không focus, icon phụ |
| `gray-base` | `#889397` | Text phụ (metadata, timestamp, placeholder) |
| `gray-dark-1` | `#5C6C75` | Text mô tả ngắn, nhãn thông số thứ cấp |
| `gray-dark-2` | `#3D4F58` | Tiêu đề chính, văn bản đọc chính (`text-main`) |
| `bg-canvas` | `#F0F4F8` | Nền tổng thể của toàn màn hình ứng dụng |

### 3.4. Kiểm tra độ tương phản tiếp cận (WCAG 2.1)

- Chữ trắng (`#FFFFFF`) trên nền `blue-base` (`#016BF8`): **4.68:1** (Đạt chuẩn WCAG AA).
- Chữ trắng (`#FFFFFF`) trên nền `blue-dark-3` (`#0C2657`): **14.85:1** (Đạt chuẩn AAA).
- Chữ `gray-dark-2` (`#3D4F58`) trên nền trắng (`#FFFFFF`): **8.62:1** (Đạt chuẩn AAA).
- Chữ `red-base` (`#DB3030`) trên nền trắng (`#FFFFFF`): **4.55:1** (Đạt chuẩn WCAG AA).
- Nút bấm và nhãn cảnh báo vàng (`#FFC010`) luôn dùng chữ màu đen hoặc nâu đậm
  (`#1C1917` / `#944F01`), không dùng chữ trắng.

---

## 4. Typography chuẩn

Theo thiết kế, bộ chữ chính được chỉ định là **Lexend**, họ font chữ hiện đại được Google thiết kế
nhằm tối ưu hóa độ đọc (reading proficiency) và khả năng quét nhanh thông tin.

### 4.1. Họ font chỉ định

```css
--font-sans: "Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
--font-mono: "Source Code Pro", "SFMono-Regular", Consolas, monospace;
```

### 4.2. Thang phân cấp chữ (Type Scale)

| Phân cấp | Kích thước | Chiều cao dòng | Độ đậm (Weight) | Ứng dụng |
| --- | --- | --- | --- | --- |
| `Heading 1` | 48px (3.0rem) | 56px | 700 (Bold) | Tiêu đề ấn tượng, landing page |
| `Heading 2` | 32px (2.0rem) | 40px | 700 (Bold) | Tiêu đề trang, số liệu KPI nổi bật |
| `Heading 3` | 24px (1.5rem) | 32px | 500 (Medium) | Tiêu đề màn hình, tên cụm dashboard |
| `Subtitle` | 18px (1.125rem) | 26px | 600 (SemiBold) | Tiêu đề khối thẻ, thanh chào hỏi |
| `Body 2` | 16px (1.0rem) | 24px | 400 (Regular) / 600 | Nội dung tin nhắn chat, ô nhập liệu |
| `Body 1` | 13px (0.8125rem) | 18px | 400 (Regular) / 600 | Thông số kỹ thuật, nhãn thẻ phụ, menu |
| `Overline` | 12px (0.75rem) | 16px | 600 (SemiBold) | Tag trạng thái, tiêu đề nhóm menu (UPPERCASE) |
| `Code 2` | 15px (0.9375rem) | 22px | 400 (Regular) | Nội dung mã, log phản hồi mô hình |
| `Code 1` | 13px (0.8125rem) | 18px | 400 (Regular) | Thông tin token, độ trễ, mã tra cứu |

### 4.3. Quy định xử lý tiếng Việt

- Line-height tối thiểu 1.5 đối với văn bản đoạn văn để đảm bảo dấu thanh tiếng Việt
  không bị dính vào dòng trên.
- Không áp dụng `text-transform: uppercase` cho toàn bộ câu dài tiếng Việt. Chỉ dùng
  cho các nhãn viết tắt kỹ thuật hoặc tiêu đề nhóm danh mục ngắn gọn (dưới 4 từ).
- Luôn kiểm tra khả năng hiển thị hoàn chỉnh của các ký tự đặc thù: `ă, â, đ, ê, ô, ơ, ư`.

---

## 5. Thang kích thước, bo góc và hiệu ứng

### 5.1. Thang khoảng cách (Spacing Scale — 4px Base Grid)

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 20px;
--space-6: 24px;
--space-8: 32px;
--space-10: 40px;
--space-12: 48px;
```

### 5.2. Bo góc (Border Radius)

Giao diện chuẩn EVNHCMC thể hiện phong cách hiện đại với bo góc mềm mại
nhưng rõ ràng, phân tầng chức năng:

| Token | Giá trị | Ứng dụng |
| --- | --- | --- |
| `radius-xs` | 4px | Tag nhỏ, nhãn đếm trạng thái, thanh cuộn tùy biến |
| `radius-sm` | 8px | Nút phụ, ô nhập liệu tìm kiếm, ô chat input |
| `radius-md` | 12px | Thẻ KPI nhỏ, bong bóng chat tin nhắn, dropdown |
| `radius-lg` | 16px | Thẻ tiện ích dashboard, modal dialog, cửa sổ chat |
| `radius-xl` | 24px | Khung bao dashboard container chính |
| `radius-full` | 9999px | Avatar người dùng, badge viên thuốc (pill), nút tròn icon |

### 5.3. Bóng đổ (Elevation & Shadows)

```css
--shadow-sm: 0 1px 3px rgba(12, 38, 87, 0.06), 0 1px 2px rgba(12, 38, 87, 0.04);
--shadow-md: 0 4px 12px rgba(12, 38, 87, 0.08), 0 2px 4px rgba(12, 38, 87, 0.04);
--shadow-lg: 0 12px 24px rgba(12, 38, 87, 0.12), 0 4px 8px rgba(12, 38, 87, 0.06);
--shadow-focus: 0 0 0 3px rgba(1, 107, 248, 0.25);
```

---

## 6. Cấu trúc bố cục hệ thống (Dashboard & App Shell)

```text
+-------------------------------------------------------------------------------+
| TOP HEADER: [Logo EVNHCMC | Trợ lý ảo EVNHCMC]  [Tìm kiếm...]  (Bell) (Avatar) |
+-----------------------+-------------------------------------------------------+
| SIDEBAR               | MAIN WORKSPACE / DASHBOARD                            |
|                       |                                                       |
| DANH MỤC              | +-- KPI METRICS ROW --------------------------------+ |
| * Dashboard (Active)  | | [Tổng yêu cầu] [Đang xử lý] [Hoàn tất] [Độ trễ]   | |
| * Dịch vụ khách hàng  | +---------------------------------------------------+ |
| * Kỹ thuật vận hành   |                                                       |
|                       | +-- CHAT & UTILITY INTERFACE -----------------------+ |
| VĂN PHÒNG             | | Lịch sử chat   | Khung trò chuyện trợ lý ảo EVN   | |
| * Báo cáo thống kê    | | gợi ý tra cứu: | - Phản hồi thời gian thực (SSE)  | |
| * Tra cứu hóa đơn     | | - Hóa đơn tiền | - Huy hiệu mô hình & chi phí     | |
| * Lịch ngừng cấp điện | | - Báo mất điện | - Sao chép mã & nội dung         | |
|                       | +----------------+----------------------------------+ |
| CÀI ĐẶT               |                                                       |
| * Cấu hình mô hình    |                                                       |
| (Toggle thu gọn)      |                                                       |
+-----------------------+-------------------------------------------------------+
```

### 6.1. Thanh điều hướng bên (Sidebar)

- Độ rộng tiêu chuẩn: `240px` (desktop), thu gọn `72px` (icon mode) hoặc ẩn drawer (< 768px).
- Nền: Trắng `#FFFFFF` với viền phải `1px solid var(--gray-light-2)`.
- Nhóm danh mục:
  - **DANH MỤC**: Dashboard, Ứng dụng nghiệp vụ.
  - **VĂN PHÒNG**: Công việc, Báo cáo điều hành, Phân tích.
  - **HỖ TRỢ & CÀI ĐẶT**: Cấu hình mô hình AI, Trợ giúp (Hotline 1900 545454).
- Trạng thái mục đang chọn (Active Item): Nền xanh `var(--blue-base)` `#016BF8`, chữ trắng
  nổi bật, bo góc `8px`, kèm icon sắc nét.

### 6.2. Thanh tiêu đề phía trên (Top Header)

- Chiều cao: `64px`.
- Nền: Trắng `#FFFFFF` hoặc xanh sâu `#0C2657` tùy chế độ hiển thị.
- Phần tử:
  - Breadcrumb định vị: `Trang chủ / Trợ lý số EVNHCMC`.
  - Ô tìm kiếm nhanh: Bo tròn `radius-full`, icon kính lúp, nền `var(--gray-light-3)`.
  - Nút thông báo (Bell) có chấm báo động đỏ `red-base`.
  - Khối định danh người dùng: Avatar bo tròn, tên cán bộ nhân viên, chức danh phòng ban.

### 6.3. Khối thẻ chỉ số KPI (Stat Cards Grid)

Bố trí hàng ngang 4 thẻ thông số:

1. **Tổng lượt tương tác / văn bản**: Icon xanh `var(--blue-base)`, số liệu lớn `Heading 2`.
2. **Yêu cầu xử lý thành công**: Tiến độ xoay tròn màu xanh lá `var(--green-base)` `#00ED64`.
3. **Yêu cầu cần xác minh**: Badge màu vàng `var(--yellow-base)` `#FFC010`.
4. **Tầng mô hình đang phục vụ & độ trễ**: Badge xanh cyan `var(--blue-light-1)` `#0498EC`.

---

## 7. Thành phần giao diện trợ lý ảo Chatbot EVN

### 7.1. Bong bóng trò chuyện (Chat Bubbles)

| Vai trò | Nền | Màu chữ | Căn lề | Viền & bo góc |
| --- | --- | --- | --- | --- |
| **Người dùng** | `#016BF8` (`blue-base`) | Trắng `#FFFFFF` | Căn phải | Bo góc `16px 16px 4px 16px` |
| **Trợ lý EVNHCMC** | `#FFFFFF` (trên nền xám) | `#3D4F58` (`gray-dark-2`) | Căn trái | Viền `#E8EDEB`, bo góc `16px 16px 16px 4px` |

### 7.2. Huy hiệu đo lường mô hình (Model Telemetry Badge)

Theo Quy tắc bất biến số 4 của dự án (`AGENTS.md`), mỗi câu trả lời của mô hình bắt buộc
ghi nhận thông tin vận hành:

- Khối hiển thị thu nhỏ đặt ngay dưới câu trả lời của bot.
- Thông tin gồm: Tầng mô hình (Tier), tên Model (`gemini-2.5-flash`, `openrouter/auto`,
  `claude-3-5-sonnet`, `gpt-4o`), Token vào/ra, Chi phí ước tính (USD/VND), Độ trễ (ms).
- Định dạng: Font monospace (`Source Code Pro`), cỡ chữ `12px`, nền `var(--blue-light-3)`,
  chữ `var(--blue-dark-2)`, viền mềm mại.

### 7.3. Gợi ý tác vụ nhanh (Quick Prompt Chips)

Nằm tại màn hình chào mở đầu để hỗ trợ khách hàng và cán bộ thao tác 1 chạm:

- `Tra cứu tiền điện tháng gần nhất` (Kèm icon hóa đơn)
- `Lịch ngừng giảm cung cấp điện tuần này` (Kèm icon tia điện cảnh báo)
- `Quy trình đăng ký gắn mới công tơ điện tử` (Kèm icon hồ sơ)
- `Báo cáo sự cố mất điện đột xuất` (Kèm icon hotline cứu hộ)

---

## 8. Nguyên tắc ngôn ngữ & giọng điệu giao tiếp

Tuân thủ văn hóa công vụ và dịch vụ khách hàng của EVNHCMC:

1. **Chuẩn mực và tôn trọng**: Dùng đại từ xưng hô "Quý khách" hoặc "Anh/Chị", xưng
   "EVNHCMC" hoặc "Trợ lý ảo EVNHCMC". Tuyệt đối không dùng "mình", "cậu", "bạn ơi".
2. **Minh bạch và chính xác**: Cung cấp số liệu cụ thể (ngày giờ, số tiền, chỉ số kWh).
   Khi không đủ thẩm quyền giải quyết, hướng dẫn trực tiếp đến Tổng đài CSKH `1900 545454`.
3. **Định dạng dữ liệu thống nhất**:
   - Số tiền: Định dạng dấu chấm hàng nghìn kèm đơn vị (ví dụ: `1.450.000 đ`).
   - Điện năng tiêu thụ: Số kèm `kWh` (ví dụ: `320 kWh`).
   - Thời gian: `dd/mm/yyyy - HH:mm` (ví dụ: `18/09/2026 - 14:30`).

---

## 9. Danh mục biến CSS toàn cục (CSS Design Tokens)

Bộ token CSS hoàn chỉnh dưới đây được áp dụng vào giao diện duy nhất `web/index.html`:

```css
:root {
  /* 1. EVNHCMC Brand Color Ramp */
  --evn-blue-dark-3: #0C2657;
  --evn-blue-dark-2: #083C90;
  --evn-blue-dark-1: #1254B7;
  --evn-blue-base:   #016BF8; /* Primary Blue */
  --evn-blue-light-1:#0498EC; /* Electric Cyan */
  --evn-blue-light-2:#C3E7FE;
  --evn-blue-light-3:#E1F7FF;

  /* 2. Semantic Accents */
  --evn-green-base:  #00ED64;
  --evn-green-dark:  #00A35C;
  --evn-green-light: #C0FAE6;

  --evn-yellow-base: #FFC010;
  --evn-yellow-dark: #944F01;
  --evn-yellow-light:#FEF7D8;

  --evn-red-base:    #DB3030;
  --evn-red-dark:    #970606;
  --evn-red-light:   #FFEAE5;

  --evn-purple-base: #B45AF2;

  /* 3. Neutrals */
  --evn-white:       #FFFFFF;
  --evn-gray-light-3:#F9FBFA;
  --evn-gray-light-2:#E8EDEB;
  --evn-gray-light-1:#C1C7C6;
  --evn-gray-base:   #889397;
  --evn-gray-dark-1: #5C6C75;
  --evn-gray-dark-2: #3D4F58;
  --evn-bg-canvas:   #F0F4F8;

  /* 4. Semantic UI Mappings */
  --color-primary:        var(--evn-blue-base);
  --color-primary-hover:  var(--evn-blue-dark-1);
  --color-primary-active: var(--evn-blue-dark-2);
  --color-bg-app:         var(--evn-bg-canvas);
  --color-bg-surface:     var(--evn-white);
  --color-bg-card:        var(--evn-white);
  --color-border:         var(--evn-gray-light-2);
  --color-text-main:      var(--evn-gray-dark-2);
  --color-text-muted:     var(--evn-gray-dark-1);
  --color-text-dim:       var(--evn-gray-base);

  /* 5. Typography */
  --font-sans: "Lexend", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  --font-mono: "Source Code Pro", "SFMono-Regular", Consolas, monospace;

  /* 6. Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;

  /* 7. Radii */
  --radius-xs: 4px;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 24px;
  --radius-full: 9999px;

  /* 8. Shadows & Transitions */
  --shadow-sm: 0 1px 3px rgba(12, 38, 87, 0.06), 0 1px 2px rgba(12, 38, 87, 0.04);
  --shadow-md: 0 4px 12px rgba(12, 38, 87, 0.08), 0 2px 4px rgba(12, 38, 87, 0.04);
  --shadow-lg: 0 12px 24px rgba(12, 38, 87, 0.12);
  --transition-fast: 0.15s cubic-bezier(0.4, 0, 0.2, 1);
  --transition-normal: 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
```

---

## 10. Tài liệu tham khảo

- Cổng thông tin Tổng công ty Điện lực TP.HCM: <https://www.evnhcmc.vn>.
- Quy chuẩn nhận diện thương hiệu Tập đoàn Điện lực Việt Nam (EVN).
- Tiêu chuẩn khả năng tiếp cận nội dung web W3C WCAG 2.1 Level AA.

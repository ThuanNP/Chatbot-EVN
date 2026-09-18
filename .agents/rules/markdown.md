# Quy Chuẩn Định Dạng Markdown (Markdownlint Guidelines)

Mọi tệp `.md` trong dự án — tài liệu, hướng dẫn, artifacts, rule, skill — bắt buộc
tuân thủ chuẩn `markdownlint`. Quy tắc này áp dụng cho **mọi AI agent** làm việc
trong repo, không có ngoại lệ.

## 0. Nguyên tắc bắt buộc với agent

1. **Tự kiểm tra trước khi báo hoàn thành.** Sau khi tạo hoặc sửa bất kỳ tệp
   `.md` nào, agent phải chạy linter và chỉ được báo xong khi không còn lỗi.
2. **Không tự ý tắt rule.** Muốn tắt một rule phải sửa `.markdownlint.json` và
   nêu lý do, không dùng comment `markdownlint-disable` rải rác trong tài liệu.
3. **Không sửa tài liệu khác chỉ để "làm sạch lint".** Chỉ sửa tệp nằm trong
   phạm vi công việc đang làm.

### Lệnh tự kiểm tra

Globs và danh sách loại trừ đã khai báo sẵn trong `.markdownlint-cli2.jsonc`,
nên chạy không cần tham số:

```bash
npx --yes markdownlint-cli2
```

Sửa tự động những lỗi sửa được:

```bash
npx --yes markdownlint-cli2 --fix
```

`--fix` xử lý được MD004, MD005, MD009, MD010, MD012, MD030, MD047. Các lỗi còn
lại — đáng kể nhất là MD013, MD022, MD031, MD032, MD040 — phải sửa tay.

## 1. Cấu hình

Dự án dùng hai tệp cấu hình ở thư mục gốc; `markdownlint-cli2` đọc và gộp cả
hai, còn tiện ích markdownlint của VS Code đọc `.markdownlint.json`.

### 1.1. `.markdownlint.json` — các rule định dạng

```json
{
  "default": true,
  "MD013": {
    "line_length": 100,
    "code_blocks": false,
    "tables": false,
    "headings": false
  },
  "MD024": { "siblings_only": true },
  "MD033": { "allowed_elements": ["br", "kbd", "sub", "sup", "details", "summary"] },
  "MD041": false
}
```

Giải thích các tuỳ chỉnh:

- `MD013` giữ bật ở mức 100 ký tự cho văn xuôi, nhưng miễn trừ khối mã, bảng và
  tiêu đề — bảng token màu và bảng thành phần không thể bẻ dòng.
- `MD024` cho phép trùng tiêu đề ở các nhánh khác nhau (ví dụ nhiều mục con cùng
  tên "Ví dụ"), nhưng cấm trùng trong cùng một cấp cha.
- `MD033` chỉ mở một số thẻ HTML thực sự cần cho tài liệu kỹ thuật.
- `MD041` tắt vì một số tệp mở đầu bằng frontmatter hoặc badge.

### 1.2. `.markdownlint-cli2.jsonc` — phạm vi quét

Khai báo `globs` (`**/*.md`) và `ignores`. Các thư mục được loại trừ:

| Thư mục | Lý do |
| --- | --- |
| `.venv/`, `node_modules/`, `.pytest_cache/` | Mã của bên thứ ba và cache |
| `.remember/` | Bộ đệm phiên do plugin sinh tự động |
| `.agents/skills/` | Skill pack vendor, giữ nguyên định dạng gốc |

### 1.3. `prompts/.markdownlint.json` — ngoại lệ có chủ đích

Nội dung trong `prompts/` được gửi thẳng tới mô hình. Bẻ dòng để thoả MD013 sẽ
làm đổi văn bản mà mô hình nhận, nên MD013 tắt riêng trong thư mục này. Các rule
cấu trúc khác vẫn giữ nguyên.

**Không được bẻ dòng thủ công trong `prompts/`.**

## 2. Nhóm quy tắc bắt buộc

### 2.1. Khoảng trống

| Rule | Tên | Yêu cầu |
| --- | --- | --- |
| MD022 | blanks-around-headings | Một dòng trống trước và sau **mọi** tiêu đề |
| MD031 | blanks-around-fences | Một dòng trống trước và sau **mọi** khối mã |
| MD032 | blanks-around-lists | Một dòng trống trước và sau **mọi** danh sách |
| MD012 | no-multiple-blanks | Không quá một dòng trống liên tiếp |
| MD047 | single-trailing-newline | Tệp kết thúc bằng đúng một ký tự xuống dòng |

Đây là nhóm agent vi phạm nhiều nhất. Khi sinh nội dung dài, rất dễ viết nội dung
sát ngay dưới tiêu đề hoặc mở khối mã ngay sau dòng danh sách.

Khi khối mã hoặc danh sách nằm **bên trong** một mục danh sách, vẫn phải có dòng
trống ngăn cách. Khi danh sách nằm trong blockquote, dùng một dòng `>` trống làm
dòng ngăn cách.

### 2.2. Khối mã

| Rule | Tên | Yêu cầu |
| --- | --- | --- |
| MD040 | fenced-code-language | **Mọi** khối mã phải khai báo ngôn ngữ |
| MD046 | code-block-style | Chỉ dùng fenced (```), không dùng thụt lề 4 khoảng trắng |
| MD048 | code-fence-style | Chỉ dùng backtick, không dùng dấu ngã |

Nhãn ngôn ngữ hợp lệ thường dùng trong dự án: `python`, `bash`, `powershell`,
`json`, `yaml`, `sql`, `html`, `css`, `javascript`, `markdown`, `ini`, `diff`,
`text`. Khi nội dung không phải mã (cây thư mục, log, kết quả chạy), dùng `text`.

Tuyệt đối không để khối mã trần không nhãn.

### 2.3. Tiêu đề

| Rule | Tên | Yêu cầu |
| --- | --- | --- |
| MD001 | heading-increment | Tăng cấp từng bậc một, không nhảy `##` sang `####` |
| MD003 | heading-style | Chỉ dùng kiểu ATX (`#`), không dùng gạch dưới |
| MD024 | no-duplicate-heading | Không trùng tiêu đề trong cùng một cấp cha |
| MD025 | single-title | Mỗi tệp đúng một tiêu đề cấp `#` |
| MD026 | no-trailing-punctuation | Tiêu đề không kết thúc bằng `.`, `,`, `:`, `!`, `?` |
| MD036 | no-emphasis-as-heading | Không dùng dòng in đậm thay cho tiêu đề thật |

### 2.4. Danh sách

| Rule | Tên | Yêu cầu |
| --- | --- | --- |
| MD004 | ul-style | Toàn dự án dùng `-`, không trộn `*` và `+` |
| MD005 | list-indent | Các mục cùng cấp thụt lề bằng nhau |
| MD007 | ul-indent | Danh sách con thụt vào 2 khoảng trắng |
| MD029 | ol-prefix | Danh sách số dùng `1.` `2.` `3.` tăng dần |
| MD030 | list-marker-space | Đúng một khoảng trắng sau dấu đầu dòng |

### 2.5. Ký tự và độ dài dòng

| Rule | Tên | Yêu cầu |
| --- | --- | --- |
| MD009 | no-trailing-spaces | Không có khoảng trắng thừa cuối dòng |
| MD010 | no-hard-tabs | Không dùng ký tự tab, chỉ dùng khoảng trắng |
| MD013 | line-length | Văn xuôi tối đa 100 ký tự (bảng, khối mã, tiêu đề miễn trừ) |

### 2.6. Liên kết, ảnh, nhấn mạnh, HTML

| Rule | Tên | Yêu cầu |
| --- | --- | --- |
| MD034 | no-bare-urls | URL phải bọc trong `[nhãn](url)` hoặc `<url>` |
| MD042 | no-empty-links | Không để link rỗng hoặc trỏ tới `#` vô nghĩa |
| MD045 | no-alt-text | Ảnh phải có alt text tiếng Việt mô tả nội dung |
| MD049 | emphasis-style | Nhấn mạnh nghiêng dùng `_`, không dùng `*` |
| MD050 | strong-style | Nhấn mạnh đậm dùng `**` |
| MD033 | no-inline-html | Chỉ dùng thẻ HTML trong danh sách cho phép ở §1 |

## 3. Quy tắc riêng cho tài liệu tiếng Việt

- **Bẻ dòng thủ công ở mốc 100 ký tự** cho đoạn văn xuôi. Bẻ ở ranh giới từ,
  không bao giờ bẻ giữa một từ có dấu.
- **Bảng không bẻ dòng.** MD013 đã miễn trừ bảng — cứ để một dòng dài, đừng chèn
  `<br>` để né lint.
- **Tiêu đề viết hoa chữ cái đầu.** Không viết hoa toàn bộ tiêu đề tiếng Việt
  (chữ hoa toàn phần làm mất dấu về mặt thị giác).
- **Không có khoảng trắng trước dấu câu** `,` `.` `:` `;` `?` `!`.
- **Dùng dấu gạch ngang em** `—` cho câu chèn, không dùng `--`.

## 4. Mẫu đúng và sai

### 4.1. Khoảng trống quanh tiêu đề, danh sách, khối mã

Viết đúng:

````markdown
## Cài đặt

Các bước cài đặt:

- Bước một
- Bước hai

```bash
pip install -r requirements.txt
```

Chạy xong thì kiểm tra lại.
````

Viết sai:

````markdown
## Cài đặt
Các bước cài đặt:
- Bước một
- Bước hai
```
pip install -r requirements.txt
```
Chạy xong thì kiểm tra lại.
````

Bốn lỗi trong ví dụ sai: MD022 (thiếu dòng trống sau tiêu đề), MD032 (thiếu dòng
trống quanh danh sách), MD031 (thiếu dòng trống quanh khối mã), MD040 (khối mã
không có nhãn ngôn ngữ).

### 4.2. Khối mã trong danh sách

Viết đúng:

````markdown
1. Tạo môi trường ảo:

   ```bash
   python -m venv .venv
   ```

2. Kích hoạt môi trường.
````

Khối mã thụt vào 3 khoảng trắng để thuộc về mục `1.`, và có dòng trống ở cả hai
phía.

### 4.3. Danh sách trong blockquote

Viết đúng:

```markdown
> Lưu ý trước khi triển khai:
>
> - Kiểm tra biến môi trường
> - Chạy lại toàn bộ test
```

## 5. Ngoại lệ

Khi thực sự cần phá rule cho một đoạn cụ thể, dùng comment inline và **luôn kèm
lý do**:

```markdown
<!-- markdownlint-disable-next-line MD013 -->
Dòng đặc biệt dài không thể bẻ vì là một chuỗi token duy nhất.
```

Cấm dùng `<!-- markdownlint-disable -->` không có `enable` tương ứng — nó tắt
rule cho toàn bộ phần còn lại của tệp.

## 6. Ba tầng tự động sửa

Dự án đã cấu hình sửa lỗi tự động ở ba nơi. Agent không cần chạy tay trong luồng
bình thường, nhưng vẫn phải tự kiểm tra trước khi báo hoàn thành (§0).

| Tầng | Tệp cấu hình | Kích hoạt khi |
| --- | --- | --- |
| AI agent | `.claude/settings.json` | Sau mỗi lần agent dùng Write hoặc Edit lên tệp `.md` |
| Trình soạn thảo | `.vscode/settings.json` | Khi lập trình viên lưu tệp `.md` trong VS Code |
| Commit | `.pre-commit-config.yaml` | Khi `git commit` có tệp `.md` trong staging |

Tầng AI agent gọi `scripts/fix_markdown.py`: script đọc payload hook, bỏ qua tệp
không phải `.md` và tệp nằm trong vùng loại trừ, rồi chạy
`markdownlint-cli2 --fix` lên đúng tệp vừa ghi. Script luôn thoát mã 0 để không
chặn agent; nếu còn lỗi phải sửa tay thì in ra stderr để agent đọc và xử lý.

Tầng VS Code cần tiện ích `DavidAnson.vscode-markdownlint`. Tầng commit cần
`npx` trên PATH và chỉ chạy `pre-commit install` một lần cho mỗi bản sao repo.

Ba tầng dùng chung một cấu hình ở §1, nên kết quả luôn nhất quán.

## 7. Danh sách kiểm tra trước khi commit

- [ ] Đã chạy `npx --yes markdownlint-cli2` và không còn lỗi.
- [ ] Mọi khối mã đều có nhãn ngôn ngữ.
- [ ] Mọi tiêu đề, danh sách, khối mã đều có dòng trống bao quanh.
- [ ] Không còn URL trần, không còn khoảng trắng cuối dòng.
- [ ] Tệp kết thúc bằng đúng một dòng trống.
- [ ] Đoạn văn xuôi không vượt 100 ký tự.

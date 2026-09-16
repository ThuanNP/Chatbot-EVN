# Quy Chuẩn Định Dạng Markdown (Markdownlint Guidelines)

Mọi tệp tài liệu, hướng dẫn và artifacts (`.md`) trong dự án bắt buộc phải tuân thủ nghiêm ngặt các quy tắc định dạng Markdown chuẩn (markdownlint):

1. **MD022 / blanks-around-headings (Khoảng trống quanh tiêu đề)**:
   - Luôn có một dòng trống trước và một dòng trống sau tất cả các tiêu đề (`#`, `##`, `###`, `####`, v.v.).
   - Tránh việc viết nội dung hoặc danh sách ngay sát dưới dòng tiêu đề mà không có dòng trống ngăn cách.

2. **MD031 / blanks-around-fences (Khoảng trống quanh khối mã)**:
   - Luôn có dòng trống ở trước và sau tất cả các khối mã nguồn fenced code blocks (\`\`\`).
   - Ngay cả khi khối mã nằm bên trong một mục danh sách, phải có dòng trống cách biệt giữa dòng danh sách và khối mã.

3. **MD032 / blanks-around-lists (Khoảng trống quanh danh sách)**:
   - Danh sách (dạng gạch đầu dòng `-`, `*` hoặc dạng số `1.`, `2.`) luôn phải có dòng trống ở phía trước và phía sau.
   - Khi danh sách nằm trong trích dẫn blockquote (`>`), phải có một dòng blockquote trống (`>`) ngăn cách giữa đoạn văn bản và mục danh sách đầu tiên.

4. **MD040 / fenced-code-language (Chỉ định ngôn ngữ cho khối mã)**:
   - Tất cả các khối mã (fenced code blocks \`\`\`) bắt buộc phải chỉ định tên ngôn ngữ/cú pháp cụ thể (ví dụ: `python`, `bash`, `powershell`, `json`, `yaml`, `text`, v.v.).
   - Tuyệt đối không để khối mã trần không có nhãn ngôn ngữ.

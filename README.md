# ThưViệnPhápLuật Crawler

Công cụ crawl và xử lý văn bản pháp luật từ `thuvienphapluat.vn`, tập trung vào việc giữ đúng cấu trúc văn bản và xử lý các phần nội dung đặc thù như biểu mẫu, phụ lục, footnote, ảnh đính kèm và công thức toán.

## Mục Tiêu

- Crawl nội dung văn bản pháp luật từ trang nguồn.
- Giữ lại đầy đủ các phần quan trọng của văn bản sau khi render DOM.
- Chuẩn hóa output để dễ đọc, dễ search và dễ dùng lại cho downstream.
- Xử lý riêng các nhóm nội dung đã được cải thiện:
  - IV. Mẫu Đơn & Link Download
  - VI. Phụ Lục Kèm Theo
  - VIII. Văn Bản Hợp Nhất & Footnote
  - IX. Hình Ảnh Đính Kèm
  - X. Các công thức toán

## Luồng Chạy Tổng Quát

Luồng xử lý hiện tại đi theo thứ tự sau:

1. Nhận URL văn bản đầu vào.
2. Mở trang bằng Playwright, render JavaScript và chờ nội dung động hoàn tất.
3. Nếu có `cookies.txt`, hệ thống nạp cookies để truy cập được nội dung tooltip hoặc biểu mẫu cần quyền cao hơn.
4. Trích xuất nội dung HTML từ khối văn bản chính.
5. Xử lý tooltip sửa đổi, bãi bỏ, hướng dẫn, ghi chú nội dung.
6. Xử lý biểu mẫu và link download của mẫu đơn/phụ lục.
7. Chuyển bảng dữ liệu sang Markdown khi phù hợp.
8. Giữ lại ảnh đính kèm dưới dạng Markdown image.
9. Giữ cấu trúc công thức bằng cách bảo toàn `sub/sup` và chuẩn hóa một số phép toán.
10. Postprocess để tách Chương, Điều, Phụ lục và chuẩn hóa xuống dòng.
11. Ghi file output `.txt`.
12. Nếu có biểu mẫu, ghi thêm file mapping `*_data_url.json`.

## Các Điểm Đã Cải Thiện

### III. Yêu Cầu Nội Dung & Viện Dẫn

- Cập nhật cơ chế nhận diện các thẻ cần hover để hệ thống có thể lấy đầy đủ thông tin viện dẫn, sửa đổi, bổ sung hoặc bãi bỏ ngay trong quá trình crawl.
- Nội dung hover sau khi lấy về được chuẩn hóa lại format để hiển thị rõ ràng hơn trong output, tránh bị dính liền với nội dung chính.
- Bổ sung xử lý phân tách cấu trúc văn bản, giúp hệ thống nhận diện riêng phần `Chương`, `Mục`, `Điều` và định dạng lại theo từng khối nội dung rõ ràng.
- Thêm cơ chế scroll xuống toàn bộ trang trong quá trình crawl để đảm bảo các tooltip/hover ở cuối văn bản cũng được load đầy đủ, hạn chế tình trạng bỏ sót viện dẫn.
- Tối ưu cách xuống dòng và khoảng cách giữa các phần nội dung, giúp file sau khi xử lý dễ đọc, dễ kiểm tra và thuận tiện hơn cho bước chunking.
- Điều chỉnh timeout trong `batch_crawler.py` để tránh crash khi gặp các văn bản quá dài hoặc có thời gian xử lý lâu hơn bình thường.

### IV. Mẫu Đơn & Link Download

- Hệ thống đã bổ sung bước nhận diện biểu mẫu từ HTML thay vì chỉ dựa vào text hiển thị.
- Nếu link download có sẵn trong DOM, crawler sẽ lấy trực tiếp link đó.
- Nếu link không có sẵn, crawler gọi AJAX `LoadBieuMau` để lấy URL thật của file biểu mẫu.
- Có thêm cơ chế retry và xử lý rate limit để giảm lỗi khi TVPL giới hạn tần suất truy cập.
- Nếu AJAX không trả link trực tiếp, hệ thống có fallback suy luận URL theo `LawID`, `Bookmark_ID` và tên file chuẩn.
- Các link biểu mẫu lấy được sẽ được thay thế bằng Markdown link trong output và đồng thời lưu ra file JSON mapping.

### VI. Phụ Lục Kèm Theo

- Chuẩn hóa `PHỤ LỤC` khi nó bị dính liền với đoạn trước đó sau khi render HTML.
- Chỉ tách khi `PHỤ LỤC` xuất hiện ở đầu dòng, để tránh cắt nhầm các câu văn bình thường có cụm “Phụ lục I...”.
- Hỗ trợ cả phụ lục đánh số La Mã và số thường.
- Khi format, phụ lục được giữ như một phần có cấu trúc riêng, không bị hòa vào nội dung điều trước đó.

### VII. Văn Bản Sửa Đổi / Bãi Bỏ / Bổ Sung

- Tạo riêng file `format_bosung.py` để xử lý nhóm văn bản sửa đổi, bãi bỏ, bổ sung do loại văn bản này có cấu trúc phức tạp hơn so với văn bản thông thường.
- Với nhóm văn bản này, nội dung không chỉ được chia theo `Điều` mà còn được tách nhỏ hơn đến từng `khoản`, giúp mỗi chunk có phạm vi nội dung rõ ràng và chính xác hơn.
- Trước mỗi khoản, hệ thống sẽ lặp lại tên văn bản và tên điều tương ứng để đảm bảo từng chunk vẫn giữ đủ ngữ cảnh khi được xử lý độc lập.
- `format_bosung.py` kế thừa và tích hợp các phần format quan trọng từ luồng xử lý văn bản thường, bao gồm nhận diện heading, chuẩn hóa xuống dòng và làm sạch nội dung.
- Sau khi format, output có cấu trúc dễ đọc hơn, đồng thời được nâng cấp nhờ khả năng chia nhỏ nội dung theo khoản thay vì chỉ dừng ở cấp điều.
- Cách xử lý riêng này giúp văn bản sửa đổi, bãi bỏ, bổ sung giữ được đầy đủ ngữ cảnh pháp lý, đặc biệt trong các trường hợp một điều có nhiều khoản hoặc nhiều nội dung sửa đổi liên tiếp.

### VIII. Văn Bản Hợp Nhất & Footnote

- Bổ sung xử lý footnote để đưa nội dung chú thích từ cuối văn bản về đúng vị trí inline.
- Có cơ chế nhận diện định nghĩa footnote ở cuối file và xóa các block watermark/metadata thừa đi kèm.
- Với văn bản hợp nhất, phần footnote được giữ theo ngữ cảnh thật của văn bản thay vì để rơi xuống cuối file.
- Có thêm các fix format để giảm lỗi hiển thị heading Chương/Điều bị lặp hoặc dính note.

### IX. Hình Ảnh Đính Kèm

- Khi render DOM, thẻ `<img>` không bị mất mà được chuyển thành Markdown image `![](url)`.
- URL ảnh được normalize về absolute URL nếu HTML dùng link tương đối hoặc `//...`.
- Cách này giúp giữ lại hình minh họa, sơ đồ hoặc ảnh đính kèm có ý nghĩa trong văn bản gốc.

### X. Các Công Thức Toán

- Hệ thống giữ lại cấu trúc toán học cơ bản bằng cách render `<sub>` và `<sup>` thành dạng LaTeX-like `_{} / ^{}`.
- Chỉ chuẩn hóa phép nhân sang `\times` ở các dòng có dấu hiệu là công thức, tránh làm sai các đoạn text thường.
- Nhờ vậy công thức trong output dễ đọc hơn nhưng vẫn giữ được ngữ nghĩa tương đối sát bản gốc.

## Tính Năng

- Crawl nội dung văn bản pháp luật
- Trích xuất nội dung hover tooltip: sửa đổi, bãi bỏ, hướng dẫn
- Tự động format với tên văn bản trước mỗi Điều
- Tự động phát hiện tên văn bản từ URL
- Hỗ trợ đăng nhập bằng cookies
- Giữ lại biểu mẫu, phụ lục, hình ảnh và công thức trong output

## Cài Đặt

```bash
# Clone repo
git clone <repo-url>
cd thuvienphapluat-crawler

# Cài đặt dependencies với uv
uv sync

# Cài đặt Playwright browsers
uv run playwright install chromium
```

## Sử Dụng

### Pipeline Hoàn Chỉnh

```bash
# Crawl một văn bản
uv run python pipeline.py "https://thuvienphapluat.vn/van-ban/Doanh-nghiep/Nghi-dinh-47-2021-ND-CP-huong-dan-Luat-Doanh-nghiep-470561.aspx"

# Chỉ định file output
uv run python pipeline.py "https://thuvienphapluat.vn/van-ban/..." -o "nghi_dinh_47.txt"

# Chỉ định tên văn bản thủ công
uv run python pipeline.py "https://thuvienphapluat.vn/van-ban/..." --doc-name "Luật ABC 2024"

# Xem help
uv run python pipeline.py --help
```

### Sử Dụng Từng Module

```bash
# Chỉ crawl
# Chỉ crawl
uv run python main.py

# Chỉ postprocess
# Chỉ postprocess
uv run python postprocess.py
```

## Cookies

Để lấy được nội dung tooltip và một số link biểu mẫu, cần có tài khoản Pro trên `thuvienphapluat.vn`.

1. Đăng nhập vào `thuvienphapluat.vn` trên trình duyệt.
2. Export cookies bằng extension [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc).
3. Lưu file `cookies.txt` vào thư mục project.

## Output

Sau khi chạy xong, hệ thống sinh ra:

- File `.txt` đã crawl và postprocess.
- File `*_data_url.json` nếu văn bản có biểu mẫu hoặc link download cần lưu mapping.

Trong nội dung output:
Sau khi chạy xong, hệ thống sinh ra:

- File `.txt` đã crawl và postprocess.
- File `*_data_url.json` nếu văn bản có biểu mẫu hoặc link download cần lưu mapping.

Trong nội dung output:

- Tên văn bản được đưa trước mỗi Điều: `Nghị định 47/2021/NĐ-CP. Điều 1. ...`
- Tooltip được đặt trong dấu `[]`: `[Điều này bị bãi bỏ bởi...]`
- Phụ lục được tách riêng rõ ràng
- Ảnh đính kèm được giữ dưới dạng Markdown image
- Công thức toán được giữ theo cấu trúc gần với bản gốc hơn

## Cấu Trúc Project

```text
thuvienphapluat-crawler/
├── pipeline.py             # Pipeline crawl và trích xuất nội dung chính
├── batch_crawler.py        # Công cụ crawl hàng loạt nhiều URL
├── main.py                 # Module crawl độc lập
├── postprocess.py          # Module xử lý text
├── format.py               # Format văn bản thường và văn bản hợp nhất
├── format.py               # Format văn bản thường và văn bản hợp nhất
├── format_bosung.py        # Format văn bản sửa đổi, bổ sung
├── format_hopnhat.py       # Resolve footnote cho văn bản hợp nhất
├── format_hopnhat.py       # Resolve footnote cho văn bản hợp nhất
├── cookies.txt             # File cookies (tự tạo)
├── output.txt              # Output thô
└── output_processed.txt    # Output đã xử lý
```

## Luồng Xử Lý Theo Loại Văn Bản

## Luồng Xử Lý Theo Loại Văn Bản

## Luồng Xử Lý Theo Loại Văn Bản

Tùy theo loại văn bản, hệ thống đi theo luồng format khác nhau để đảm bảo output đúng cấu trúc:
Tùy theo loại văn bản, hệ thống đi theo luồng format khác nhau để đảm bảo output đúng cấu trúc:

- **Văn bản sửa đổi, bổ sung**: `batch_crawler.py` → `format_bosung.py`
- **Văn bản hợp nhất**: `batch_crawler.py` → `format.py` → `format_hopnhat.py`
- **Các văn bản còn lại**: `batch_crawler.py` → `format.py`

> Khi cần crawl nhiều URL cùng lúc, xem thêm `README_batch_crawler.md` để dùng `batch_crawler.py` với cơ chế đa luồng, retry, resume và quản lý output theo thư mục.
> Khi cần crawl nhiều URL cùng lúc, xem thêm `README_batch_crawler.md` để dùng `batch_crawler.py` với cơ chế đa luồng, retry, resume và quản lý output theo thư mục.

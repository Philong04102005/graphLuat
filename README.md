# ThưViệnPhápLuật Crawler

Công cụ crawl và xử lý văn bản pháp luật từ thuvienphapluat.vn

## Tính năng

- ✅ Crawl nội dung văn bản pháp luật
- ✅ Trích xuất nội dung hover tooltip (sửa đổi, bãi bỏ, hướng dẫn)
- ✅ Tự động format với tên văn bản trước mỗi Điều
- ✅ Tự động phát hiện tên văn bản từ URL
- ✅ Hỗ trợ đăng nhập bằng cookies

## Cài đặt

```bash
# Clone repo
git clone <repo-url>
cd thuvienphapluat-crawler

# Cài đặt dependencies với uv
uv sync

# Cài đặt Playwright browsers
uv run playwright install chromium
```

## Sử dụng

### Pipeline hoàn chỉnh (khuyên dùng)

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

### Sử dụng riêng từng module

```bash
# Chỉ crawl (không postprocess)
uv run python main.py

# Chỉ postprocess (từ output.txt có sẵn)
uv run python postprocess.py
```

## Cookies (để lấy tooltip)

Để lấy được nội dung tooltip (thông tin sửa đổi, bãi bỏ...), bạn cần có tài khoản Pro trên thuvienphapluat.vn.

1. Đăng nhập vào thuvienphapluat.vn trên trình duyệt
2. Export cookies bằng extension [Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
3. Lưu file `cookies.txt` vào thư mục project

## Output

Văn bản được format với:

- Tên văn bản trước mỗi Điều: `Nghị định 47/2021/NĐ-CP. Điều 1. ...`
- Thông tin tooltip trong dấu `[]`: `[Điều này bị bãi bỏ bởi...]`
- Phân tách Chương, Mục, Điều rõ ràng

## Cấu trúc project

```
thuvienphapluat-crawler/
├── pipeline.py             # Pipeline crawl và trích xuất nội dung chính
├── batch_crawler.py        # Công cụ crawl hàng loạt nhiều URL
├── main.py                 # Module crawl độc lập
├── postprocess.py          # Module xử lý text
├── format.py               # Format văn bản thông thường và văn bản hợp nhất
├── format_bosung.py        # Format văn bản sửa đổi, bổ sung
├── format_hopnhat.py       # Format bổ sung cho văn bản hợp nhất
├── cookies.txt             # File cookies (tự tạo)
├── output.txt              # Output thô
└── output_processed.txt    # Output đã xử lý
```

## Luồng xử lý theo loại văn bản

Tùy theo loại văn bản, sử dụng luồng xử lý phù hợp để đảm bảo nội dung được format đúng cấu trúc:

- **Văn bản sửa đổi, bổ sung**: `batch_crawler.py` → `format_bosung.py`
- **Văn bản hợp nhất**: `batch_crawler.py` → `format.py` → `format_hopnhat.py`
- **Các văn bản còn lại**: `batch_crawler.py` → `format.py`

> Khi cần crawl nhiều URL cùng lúc, xem thêm `README_batch_crawler.md` để sử dụng `batch_crawler.py` với cơ chế đa luồng, retry, resume và quản lý output theo thư mục.

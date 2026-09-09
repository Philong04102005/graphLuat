# Batch Crawler for Thuvienphapluat.vn

Multi-threaded batch crawler sử dụng **pipeline.py** để xử lý nhiều URL cùng lúc với tính năng quản lý hàng đợi, theo dõi tiến độ và phục hồi khi lỗi.

## Tính năng

- 🚀 **Multi-threaded**: Xử lý nhiều URL đồng thời với số lượng thread tùy chỉnh
- 📊 **Progress Tracking**: Hiển thị tiến độ real-time với thống kê chi tiết
- 🔄 **Resume Functionality**: Tiếp tục từ vị trí đã dừng trước đó
- 🛡️ **Error Handling**: Xử lý lỗi với cơ chế retry thông minh
- ⏱️ **Rate Limiting**: Tự động delay giữa các request để tránh bị block
- 💾 **State Management**: Lưu trạng thái để phục hồi khi cần
- 📝 **Logging**: Ghi lại URL thành công và thất bại
- 🔗 **Pipeline Integration**: Gọi trực tiếp `uv run python pipeline.py` để đảm bảo đồng bộ hoàn toàn
- 📁 **Custom Output Directory**: Tổ chức files vào thư mục riêng để dễ quản lý

## Kiến trúc

Batch crawler này **KHÔNG** implement lại logic crawl mà **gọi trực tiếp** `pipeline.py` thông qua subprocess:

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   URL Queue     │───▶│  Worker Thread 1 │───▶│  uv run python  │
│                 │    │                  │    │  pipeline.py    │
│                 │───▶│  Worker Thread 2 │───▶│                 │
│                 │    │                  │    │                 │
│                 │───▶│  Worker Thread N │───▶│                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                                   │
                                   ▼
                          ┌─────────────────┐
                          │  Output Dir/     │
                          │  crawl/          │
                          │  Nghị_định*.txt  │
                          │  failed_urls.txt│
                          └─────────────────┘
```

**Lợi ích:**
- ✅ **Đồng bộ 100%** với pipeline.py đã tối ưu
- ✅ **Không duplicate code**
- ✅ **Dễ maintain** khi update pipeline
- ✅ **Dùng lại toàn bộ features** của pipeline
- ✅ **Tổ chức files gọn gàng** trong thư mục riêng

## Cài đặt

```bash
# Install dependencies (cần cho pipeline.py)
pip install patchright beautifulsoup4

# Install Patchright browsers
patchright install chromium

# Hoặc dùng uv (recommended)
pip install uv
uv sync
```

## Sử dụng

### Cơ bản

```bash
python batch_crawler.py example_urls.txt
```

### Nâng cao

```bash
# Sử dụng 8 threads và custom output directory
python batch_crawler.py example_urls.txt --threads 8 --output-dir crawled_docs

# Tùy chỉnh cookie file
python batch_crawler.py example_urls.txt --cookies cookies.txt --output-dir legal_docs
source .venv/bin/activate
# Tùy chỉnh delay giữa các requests (2-5 giây)
python batch_crawler.py example_urls.txt --delay 2 5 --output-dir temp_crawl

# Tùy chỉnh số lần retry
python batch_crawler.py example_urls.txt --retry 5 --output-dir retry_crawl

# Tiếp tục từ lần chạy trước
python batch_crawler.py example_urls.txt --resume --output-dir continued_crawl
```

### Toàn bộ tham số

```bash
python batch_crawler.py <url_file> [options]

Arguments:
  url_file              File chứa danh sách URLs

Options:
  -t, --threads N       Số thread concurrently (default: 4)
  -c, --cookies FILE    Cookie file (default: cookies.txt)
  -d, --delay MIN MAX   Delay range giữa requests (default: 5.0 8.0)
  -r, --retry N         Số lần retry cho mỗi URL (default: 3)
  --resume              Tiếp tục từ lần chạy trước
  --state FILE          File state cho resume (default: crawl_state.json)
  -o, --output-dir DIR  Thư mục output cho files đã crawl (default: crawl)
```

## Định dạng URL file

Tạo file text với mỗi URL trên một dòng:

```
# example_urls.txt
https://thuvienphapluat.vn/van-ban/Doanh-nghiep/Nghi-dinh-47-2021-ND-CP-...
https://thuvienphapluat.vn/van-ban/Phap-luat/Doanh-nghiep-59-2020-QH14-...
# Dòng bắt đầu bằng # sẽ bị bỏ qua
```

## Output Structure

Khi chạy với `--output-dir crawl`, cấu trúc thư mục sẽ là:

```
project/
├── batch_crawler.py
├── pipeline.py
├── cookies.txt
├── example_urls.txt
├── crawl_state.json           # State file (luu ở root)
├── crawl/                     # Output directory
│   ├── Nghị_định_47-2021-NĐ-CP.txt
│   ├── Luật_Doanh_nghiệp_2020.txt
│   ├── Nghị_định_248-2025-NĐ-CP.txt
│   └── failed_urls.txt        # URLs thất bại
└── crawled_docs/              # Directory khác khi custom
    ├── ...
    └── ...
```

## Pipeline Integration

Batch crawler sử dụng command sau để gọi pipeline.py:

```bash
# Change đến output directory
cd crawl/

# Run pipeline với full path cookies
uv run python pipeline.py <URL> --cookies ../cookies.txt --doc-name "<tên_văn_bản>"

# Pipeline sẽ save file trong directory hiện tại
# -> crawl/Nghị_định_47-2021-NĐ-CP.txt
```

### Directory Management
- **Auto-create**: Thư mục output được tạo tự động nếu chưa tồn tại
- **Directory switching**: Pipeline chạy trong output directory
- **Cookie path**: Cookies path được resolved từ original directory
- **State file**: State file vẫn lưu ở root directory

## Tối ưu hiệu suất

### Tùy chỉnh số threads
- **1-4 threads**: An toàn, ít khả năng bị block
- **4-8 threads**: Cân bằng giữa tốc độ và stability
- **8+ threads**: Nhanh nhất nhưng có thể bị block

### Tùy chỉnh delay
- **1-3 giây**: Mặc định, phù hợp cho hầu hết cases
- **3-5 giây**: An toàn hơn cho server nhạy cảm
- **0.5-2 giây**: Nhanh hơn nhưng tăng rủi ro

### Output Directory Strategy
- **Theo loại văn bản**: `crawl/ Nghị_định/`, `crawl/Luật/`, `crawl/Thông_tư/`
- **Theo ngày**: `crawl/2025-01-15/`, `crawl/2025-01-16/`
- **Theo dự án**: `crawl/doanh_nghiep/`, `crawl/lao_dong/`

### Mẹo sử dụng
1. **Bắt đầu với số thread ít**: Test với 2-4 threads trước
2. **Sử dụng directory có ý nghĩa**: `--output-dir nghị_định_2025`
3. **Giảm delay nếu cần tốc độ**: Tăng dần lên khi cần
4. **Sử dụng resume**: Luôn dùng `--resume` để không phải crawl lại
5. **Monitor failed URLs**: Kiểm tra file `failed_urls.txt` trong output directory
6. **Kiểm tra pipeline.py**: Đảm bảo pipeline.py hoạt động trước khi chạy batch

## Ví dụ thực tế

```bash
# Crawl Nghị định vào thư mục riêng
python batch_crawler.py nghi_dinh_urls.txt --output-dir crawl/nghi_dinh --threads 6

# Crawl nhiều loại văn bản
python batch_crawler.py all_urls.txt --output-dir crawl/2025-01-17 --threads 8

# Crawl với cookies để tránh login
python batch_crawler.py urls.txt --cookies cookies.txt --output-dir authenticated_crawl --threads 4

# Resume sau khi bị lỗi
python batch_crawler.py urls.txt --resume --output-dir continued_crawl --threads 3

# Crawl nhanh (risk more)
python batch_crawler.py urls.txt --threads 8 --delay 0.5 1.5 --output-dir fast_crawl
```

## Troubleshooting

### Common Issues

1. **"Pipeline thất bại"**
   - Kiểm tra pipeline.py hoạt động: `uv run python pipeline.py "URL"`
   - Kiểm tra dependencies: `uv sync`
   - Xem stderr output để chi tiết lỗi

2. **"Pipeline timeout sau 5 phút"**
   - URL quá chậm hoặc server response chậm
   - Tăng timeout trong code nếu cần

3. **"Không tìm thấy file output"**
   - Pipeline output format đã thay đổi
   - Kiểm tra manual output của pipeline.py

4. **"Permission denied" khi tạo directory**
   - Kiểm tra permissions của thư mục cha
   - Chạy với appropriate user permissions

5. **Files bị lưu sai directory**
   - Kiểm tra output directory path
   - Xem log output để confirm directory đã được tạo

### Debug mode

Để debug, chạy pipeline.py manual trước:

```bash
# Test một URL trong output directory
cd crawl
uv run python ../pipeline.py "https://thuvienphapluat.vn/van-ban/..." --cookies ../cookies.txt

# Kiểm tra output directory
ls -la crawl/
```

## Performance Tips

1. **Start small**: Test với 5-10 URLs trước
2. **Monitor resources**: CPU và Memory usage
3. **Adjust based on server response**: Tăng/giảm thread và delay
4. **Use resume**: Không bắt đầu lại từ đầu
5. **Batch processing**: Chia lớn URLs thành các file nhỏ
6. **Test pipeline first**: Đảm bảo pipeline.py hoạt động trước khi chạy batch
7. **Organize by directory**: Sử dụng output directory có ý nghĩa

## Advanced Usage

### Organize by Document Type

```bash
# Tạo separate directories for different document types
python batch_crawler.py nghi_dinh_urls.txt --output-dir crawl/nghi_dinh
python batch_crawler.py luat_urls.txt --output-dir crawl/luat
python batch_crawler.py thong_tu_urls.txt --output-dir crawl/thong_tu
```

### Organize by Date

```bash
# Crawl with date-based directories
DATE=$(date +%Y-%m-%d)
python batch_crawler.py daily_urls.txt --output-dir "crawl/$DATE"
```

### Clean Old Files

```bash
# Remove old output directory before running
rm -rf crawl/
python batch_crawler.py urls.txt --output-dir crawl

# Or backup and create new
mv crawl/ "backup_$(date +%Y%m%d_%H%M%S)/"
python batch_crawler.py urls.txt --output-dir crawl
```

## Architecture Details

### Subprocess Management
- `subprocess.run()` với timeout 5 phút
- `os.chdir()` để change đến output directory
- Full path resolution cho cookies file
- Capture stdout/stderr cho debugging

### Directory Management
- `os.makedirs(output_dir, exist_ok=True)` để tạo directory
- Path resolution giữa original và output directory
- State file vẫn ở root để dễ dàng resume
- Failed URLs file lưu trong output directory

### Thread Safety
- `threading.Lock()` cho shared data structures
- `queue.Queue()` cho URL management
- Atomic operations cho statistics
- Directory switching thread-safe
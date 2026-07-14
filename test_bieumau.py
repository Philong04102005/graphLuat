#!/usr/bin/env python3
"""
Test biểu mẫu để soi vì sao pipeline không lấy được URL.
Dùng ĐÚNG môi trường pipeline: cookies.txt + Playwright (không phải trình duyệt đăng nhập của bạn).

Cách chạy:
    # Tự trích LawID + tự liệt kê hết bookmark biểu mẫu rồi thử lần lượt:
    python test_bieumau.py <url>

    # Hoặc test đúng 1 mẫu:
    python test_bieumau.py <url> <LawID> <Bookmark_ID>

Ví dụ (Thông tư liên tịch 41/2014):
    python test_bieumau.py "http://thuvienphapluat.vn/van-ban/Bao-hiem/Thong-tu-lien-tich-41-2014-TTLT-BYT-BTC-huong-dan-thuc-hien-bao-hiem-y-te-261252.aspx"
"""
import sys
import os, time, random
from playwright.sync_api import sync_playwright
# LƯU Ý: chỉ import pipeline; KHÔNG tự bọc sys.stdout ở đây.
# pipeline.py đã tự bọc stdout/stderr sang UTF-8 khi import. Nếu bọc thêm lần nữa
# sẽ có 2 TextIOWrapper trên cùng buffer -> cái cũ bị GC đóng buffer ->
# "ValueError: I/O operation on closed file".
from pipeline import (
    load_cookies_from_file,
    parse_form_ajax_response,
    extract_law_id_from_url,
)


def pause(msg="\n(Enter để đóng trình duyệt)..."):
    """input() an toàn: nếu stdin không tương tác thì chờ tạm thay vì crash."""
    try:
        input(msg)
    except (EOFError, ValueError):
        print(msg + " [không có stdin, chờ 15s]")
        time.sleep(15)

# Cùng nhịp chờ với pipeline để tái hiện đúng hành vi rate-limit
FORM_DELAY = (1.2, 2.8)


def call_load_bieumau(page, law_id, bookmark_id):
    return page.evaluate(
        """async ({ lawId, bookmarkId }) => {
            const body = new URLSearchParams({
                action: 'LoadBieuMau', LawID: lawId, Bookmark_ID: bookmarkId,
            });
            const res = await fetch('/page/ajaxcontroler.aspx', {
                method: 'POST',
                headers: {
                    'accept': '*/*',
                    'content-type': 'application/x-www-form-urlencoded; charset=UTF-8',
                    'x-requested-with': 'XMLHttpRequest',
                },
                body, credentials: 'include',
            });
            return { status: res.status, text: await res.text() };
        }""",
        {"lawId": law_id, "bookmarkId": bookmark_id},
    )


def list_bookmarks(page):
    """Liệt kê mọi cặp (LawID, Bookmark_ID) biểu mẫu trên trang — cùng logic dòng 158 pipeline."""
    return page.evaluate(
        r"""() => {
            const out = [];
            const seen = new Set();
            document.querySelectorAll('a[onclick*="LS_Tip_Type_Bookmark_bm"]').forEach(a => {
                const m = (a.getAttribute('onclick') || '')
                    .match(/LS_Tip_Type_Bookmark_bm\(['"](\d+)['"]\s*,\s*['"](\d+)['"]\)/);
                if (m) {
                    const key = m[1] + '_' + m[2];
                    if (!seen.has(key)) {
                        seen.add(key);
                        out.push({ lawId: m[1], bookmarkId: m[2],
                                   text: (a.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60) });
                    }
                }
            });
            return out;
        }"""
    )


def report(page, law_id, bookmark_id, label=""):
    resp = call_load_bieumau(page, law_id, bookmark_id)
    raw = resp.get("text", "") if isinstance(resp, dict) else str(resp)
    http_status = resp.get("status") if isinstance(resp, dict) else "?"
    url, status, detail = parse_form_ajax_response(raw)
    tag = f"[{label}] " if label else ""
    print(f"  {tag}Bookmark_ID={bookmark_id} | HTTP {http_status} | len={len(raw)} | {status} -> {url or '(RỖNG)'}")
    if status not in ("ok",):
        print(f"       ↳ 200 ký tự đầu: {' '.join(raw.split())[:200]}")
    return status


def main():
    if len(sys.argv) < 2:
        print("Dùng: python test_bieumau.py <url> [LawID] [Bookmark_ID]")
        sys.exit(1)

    url = sys.argv[1]
    law_id = sys.argv[2] if len(sys.argv) > 2 else extract_law_id_from_url(url)
    single_bookmark = sys.argv[3] if len(sys.argv) > 3 else None
    cookie_file = "cookies.txt"

    print(f"📋 LawID = {law_id}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()

        if cookie_file and os.path.exists(cookie_file):
            cookies = load_cookies_from_file(cookie_file)
            context.add_cookies(cookies)
            print(f"🍪 Đã load {len(cookies)} cookies từ {cookie_file}")
        else:
            print(f"⚠️  KHÔNG thấy {cookie_file} — chạy KHÔNG cookie (dễ bị chặn)")

        page = context.new_page()
        print(f"🌐 Mở trang: {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        title = page.title()
        print(f"   Title: {title!r}")
        if "just a moment" in title.lower():
            print("❌ Bị Cloudflare chặn ngay ở trang chính → cookie cf_clearance hết hạn.\n")

        if single_bookmark:
            print(f"\n▶ Test đúng 1 mẫu:")
            report(page, law_id, single_bookmark)
        else:
            bookmarks = list_bookmarks(page)
            print(f"\n🔎 Tìm thấy {len(bookmarks)} bookmark biểu mẫu trên trang.")
            if not bookmarks:
                print("   → Trang KHÔNG có bookmark kiểu LS_Tip_Type_Bookmark_bm.")
                print("     Nghĩa là không có biểu mẫu AJAX để lấy (hoặc link nằm trực tiếp trong HTML).")
            else:
                print("\n▶ Thử lần lượt (có delay như pipeline) để xem rate-limit có bật không:\n")
                stats = {}
                for i, bm in enumerate(bookmarks, 1):
                    st = report(page, bm["lawId"], bm["bookmarkId"], label=f"{i}/{len(bookmarks)} {bm['text']}")
                    stats[st] = stats.get(st, 0) + 1
                    time.sleep(random.uniform(*FORM_DELAY))
                print(f"\n📊 TỔNG KẾT: {stats}")
                if stats.get("rate-limit"):
                    print("   ➡️  Có rate-limit → tăng delay / giảm số mẫu gọi liên tục.")
                elif stats.get("cloudflare") or (stats.get("no-url") and not stats.get("ok")):
                    print("   ➡️  Không mẫu nào ra URL → nghi cookie/session. Cập nhật cookies.txt.")
                elif stats.get("ok"):
                    print("   ➡️  Có mẫu ra URL bình thường → môi trường pipeline OK.")

        pause()
        browser.close()


if __name__ == "__main__":
    main()

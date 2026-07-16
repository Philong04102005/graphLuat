#!/usr/bin/env python3
"""
check_bosung_scope.py — Kiểm chứng cơ chế "phần bổ sung" và quy tắc gộp.

Ý tưởng đã xác minh trên pagesource TVPL:
  - Mỗi chú thích (Bổ sung / Lưu ý) là 1 <div id="note_<base>"> với 4 field
    ngăn bởi "|~|":
        [0] = TOÀN VĂN đoạn được chú thích  (đây là "từ đâu đến đâu" đáng tin)
        [1] = câu chú thích  ("Khoản 5 được bổ sung bởi ...")
        [2] = URL văn bản sửa đổi
        [3] = "True" (Lưu ý) / "False" (Bổ sung)
  - <a name="<base>"> chỉ là ĐIỂM NEO / điểm chèn, KHÔNG phản ánh scope ngữ nghĩa.
    => Không được dùng tên anchor (dieu_/khoan_/cumtu_) để suy scope.

Quy tắc gộp (đúng yêu cầu):
  Chỉ gộp (bỏ bản trong thân, giữ bản trên tiêu đề điều) KHI VÀ CHỈ KHI:
    (a) hai chú thích cùng nằm trong MỘT điều,
    (b) câu chú thích field[1] GIỐNG HỆT nhau,
    (c) có 1 bản phủ tiêu đề/điều, và bản kia phủ TOÀN BỘ nội dung điều
        (covered text ~ trọn thân điều, KHÔNG phải một khoản/điểm/cụm con).
  Nếu bản trong thân chỉ phủ 1 phần con -> GIỮ cả hai.

Chạy:
    python check_bosung_scope.py pagesource.html
    python check_bosung_scope.py <file_html_da_render_cua_van_ban_bi_trung>
"""
import re
import sys
from bs4 import BeautifulSoup


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def classify_scope(covered: str):
    """Đoán loại scope TỪ NỘI DUNG covered (field[0]), không dùng tên anchor."""
    c = covered.lstrip()
    if re.match(r"^Điều\s+\d+", c):
        return "DIEU"          # cả điều / tiêu đề điều
    if re.match(r"^\d+\.", c):
        return "KHOAN"         # một khoản
    if re.match(r"^[a-zđ]\)", c):
        return "DIEM"          # một điểm
    return "CUM/PHAN"          # cụm từ / đoạn con


def load_notes(html: str):
    soup = BeautifulSoup(html, "html.parser")
    notes = []
    for div in soup.find_all(id=re.compile(r"^note_")):
        base = div.get("id")[len("note_"):]
        parts = re.split(r"\|~\|", div.get_text(""))
        covered = norm(parts[0]) if len(parts) > 0 else ""
        src = norm(parts[1]) if len(parts) > 1 else ""
        luuy = (parts[3].strip() == "True") if len(parts) > 3 else False
        anchor = soup.find("a", attrs={"name": base})
        notes.append({
            "base": base,
            "covered": covered,
            "src": src,
            "luuy": luuy,
            "scope": classify_scope(covered),
            "anchor": anchor,
        })
    return soup, notes


def enclosing_dieu(soup, anchor):
    """Tìm 'Điều N' gần nhất đứng TRƯỚC anchor trong dòng văn bản."""
    if anchor is None:
        return None
    cont = soup.find(id="divContentDoc") or soup
    flat = cont.get_text("\n")
    # vị trí tương đối của anchor: dùng text nó bọc làm mốc thô
    marker = norm(anchor.get_text(" ", strip=True))[:30]
    idx = flat.find(marker) if marker else -1
    if idx < 0:
        return None
    dieus = list(re.finditer(r"Điều\s+(\d+)\s*\.", flat[:idx]))
    return dieus[-1].group(0) if dieus else None


def dieu_body_text(soup, dieu_label):
    """Lấy toàn văn thân điều (để so 'toàn bộ nội dung điều')."""
    if not dieu_label:
        return ""
    cont = soup.find(id="divContentDoc") or soup
    flat = norm(cont.get_text(" "))
    m = re.search(re.escape(dieu_label), flat)
    if not m:
        return ""
    start = m.start()
    nxt = re.search(r"Điều\s+\d+\s*\.", flat[start + len(dieu_label):])
    end = start + len(dieu_label) + nxt.start() if nxt else len(flat)
    return flat[start:end]


def covers_whole_dieu(covered: str, dieu_body: str) -> bool:
    """covered có phủ ~toàn bộ thân điều không (>=85% độ dài & là con chuỗi thô)."""
    if not covered or not dieu_body:
        return False
    ratio = len(covered) / max(1, len(dieu_body))
    # so thô: phần lớn ký tự của covered nằm trong thân điều
    return ratio >= 0.85


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "pagesource.html"
    html = open(path, encoding="utf-8", errors="ignore").read()
    soup, notes = load_notes(html)

    print("=" * 72)
    print(f"FILE: {path}")
    print(f"Tổng số chú thích (note_*): {len(notes)}")
    print("=" * 72)

    for i, n in enumerate(notes):
        dieu = enclosing_dieu(soup, n["anchor"])
        n["dieu"] = dieu
        print(f"\n[{i}] base={n['base']}  loại={'LƯU Ý' if n['luuy'] else 'BỔ SUNG'}")
        print(f"    thuộc điều : {dieu or '(không xác định)'}")
        print(f"    SCOPE (từ field[0]): {n['scope']}  | covered {len(n['covered'])} ký tự")
        print(f"    covered[:70]: {n['covered'][:70]!r}")
        print(f"    câu chú thích: {n['src'][:90]!r}")

    # --- phát hiện cặp echo & áp quy tắc gộp ---
    print("\n" + "=" * 72)
    print("PHÂN TÍCH GỘP (theo quy tắc nghiêm: điều + TOÀN BỘ trong điều + giống nhau)")
    print("=" * 72)
    groups = {}
    for n in notes:
        groups.setdefault(n["src"], []).append(n)

    any_dup = False
    for src, members in groups.items():
        if len(members) < 2:
            continue
        any_dup = True
        by_dieu = {}
        for m in members:
            by_dieu.setdefault(m["dieu"], []).append(m)
        for dieu, ms in by_dieu.items():
            if len(ms) < 2:
                print(f"\n• Câu chú thích trùng nhưng KHÁC điều -> GIỮ cả hai: {src[:60]!r}")
                continue
            body = dieu_body_text(soup, dieu)
            has_title = any(m["scope"] == "DIEU" for m in ms)
            has_wholebody = any(covers_whole_dieu(m["covered"], body) for m in ms)
            decision = "GỘP (giữ bản tiêu đề)" if (has_title and has_wholebody) else "GIỮ cả hai (bản trong chỉ phủ phần con)"
            print(f"\n• Điều {dieu} — {len(ms)} bản trùng câu chú thích:")
            print(f"    câu: {src[:70]!r}")
            print(f"    có bản cấp-điều? {has_title} | có bản phủ TOÀN BỘ thân điều? {has_wholebody}")
            print(f"    => QUYẾT ĐỊNH: {decision}")

    if not any_dup:
        print("\n(Không có câu chú thích nào trùng lặp trong file này -> không có gì để gộp.)")


if __name__ == "__main__":
    main()

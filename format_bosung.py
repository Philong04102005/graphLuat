#!/usr/bin/env python3
import argparse
import re
from pathlib import Path
from typing import List, Tuple

try:
    import tiktoken
except ImportError:
    tiktoken = None


Chunk = Tuple[str, str]


def normalize_appendix_breaks(text: str) -> str:
    """Ensure PHỤ LỤC headings are split before chunk detection."""
    if not text:
        return text

    appendix_heading = r'(PHỤ\s+LỤC\s+(?:[IVXLCDM]+|\d+)\b)'
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = re.sub(r'([^\n])\s+' + appendix_heading, r'\1\n\n\2', text, flags=re.IGNORECASE | re.UNICODE)
    text = re.sub(r'\n+[ \t]*' + appendix_heading, r'\n\n\1', text, flags=re.IGNORECASE | re.UNICODE)
    text = re.sub(r'\n{3,}(?=PHỤ\s+LỤC\s+(?:[IVXLCDM]+|\d+)\b)', '\n\n', text, flags=re.IGNORECASE | re.UNICODE)
    # Unnumbered PHỤ LỤC (e.g. "PHỤ LỤC MỘT SỐ BIỂU MẪU...") merged onto previous line.
    # Strict case (no re.I) so lowercase "phụ lục" inside normal sentences is untouched.
    text = re.sub(r'([^\n]) +(PHỤ LỤC\b)', r'\1\n\n\2', text, flags=re.UNICODE)
    return text

def normalize_chapter_breaks(text: str) -> str:
    """
    Tách CHƯƠNG bị dính sau nội dung khoản/điểm ra dòng riêng.

    Ví dụ:
        ... [Khoản này được sửa đổi ...] CHƯƠNG IX THANH TRA ...

    Thành:
        ... [Khoản này được sửa đổi ...]

        CHƯƠNG IX THANH TRA ...
    """
    if not text:
        return text

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    chapter_pat = r'(CHƯƠNG\s+(?:[IVXLCDM]+|\d+)\b)'

    # Nếu trước CHƯƠNG là dấu ] hoặc dấu . thì tách CHƯƠNG ra đoạn mới
    text = re.sub(
        r'(\]|\.)\s+' + chapter_pat,
        r'\1\n\n\2',
        text,
        flags=re.IGNORECASE | re.UNICODE
    )

    # Gom lại nếu lỡ có quá nhiều dòng trắng trước CHƯƠNG
    text = re.sub(
        r'\n{3,}(?=\s*CHƯƠNG\s+(?:[IVXLCDM]+|\d+)\b)',
        '\n\n',
        text,
        flags=re.IGNORECASE | re.UNICODE
    )

    return text

def normalize_stuck_article_breaks(text: str) -> str:
    """
    Tách tiêu đề Điều bị dính ngay sau nội dung trước đó.

    Ví dụ dữ liệu crawl có thể ra:
        ... đã ký kết."Điều 2. Thay thế...

    Nếu không tách dòng trước Điều 2, split_into_chunks sẽ coi Điều 2 là
    phần cuối của Điều 1 và split khoản của văn bản sửa đổi bị sai header.
    """
    if not text:
        return text

    text = text.replace('\r\n', '\n').replace('\r', '\n')
    article_after_punctuation_re = re.compile(
        r'(?<=[.!?;:”"\]])\s*(Điều\s+\d+\w*\s*[.:]\s+)',
        flags=re.IGNORECASE | re.UNICODE
    )

    def repl(m):
        if _is_inside_quote(text, m.start(1)):
            return m.group(0)
        return '\n' + m.group(1)

    return article_after_punctuation_re.sub(repl, text)

def extract_title(text: str, filename: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    name = Path(filename).stem
    name = name.replace('_', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def build_amending_title(title: str, text: str, is_amending: bool) -> str:
    if not is_amending or re.search(r'\b(sửa\s+đổi|bổ\s+sung)\b', title, flags=re.IGNORECASE | re.UNICODE):
        return title

    citation_re = re.compile(
        r'\b(?P<kind>Luật|Nghị định|Thông tư|Quyết định)\s+'
        r'(?:số\s+)?(?P<num>\d+/\d{4}/[A-ZĐ-]+(?:-[A-ZĐ]+)*)',
        flags=re.IGNORECASE | re.UNICODE
    )

    current = citation_re.search(title)
    if not current:
        return title

    current_num = current.group('num').lower()
    for target in citation_re.finditer(text[:4000]):
        target_num = target.group('num')
        if target_num.lower() == current_num:
            continue
        kind = target.group('kind').capitalize()
        return f"{title.rstrip('.')} sửa đổi {kind} {target_num}"

    return title


def clean_chunk_lines(chunk: str, title_pattern: str) -> str:
    lines = chunk.splitlines()
    cleaned_lines = []
    noise_re = re.compile(rf'^\s*{title_pattern}\s*\.?\s*$', re.IGNORECASE | re.UNICODE)

    for line in lines:
        if noise_re.fullmatch(line):
            continue
        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def split_into_chunks(text: str) -> List[Chunk]:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = normalize_appendix_breaks(text)
    text = normalize_chapter_breaks(text)
    text = normalize_stuck_article_breaks(text)
    matches = []

    dieu_re = re.compile(r'^\s*Điều\s+(\d+\w*)\s*[.:]', re.IGNORECASE | re.UNICODE | re.MULTILINE)
    for m in dieu_re.finditer(text):
        if _is_inside_quote(text, m.start()):
            continue
        matches.append((m.start(), 'article'))
    chapter_re = re.compile(
        r'^\s*CHƯƠNG\s+(?:[IVXLCDM]+|\d+)\b[^\n]*',
        re.MULTILINE | re.UNICODE | re.IGNORECASE
    )

    for m in chapter_re.finditer(text):
        matches.append((m.start(), 'chapter'))
    phu_luc_re = re.compile(r'^PHỤ LỤC\b', re.MULTILINE | re.UNICODE)
    for m in phu_luc_re.finditer(text):
        matches.append((m.start(), 'appendix'))

    for m in re.finditer(r'^\s*MỤC LỤC\s*$', text, re.IGNORECASE | re.UNICODE | re.MULTILINE):
        matches.append((m.start(), 'toc'))

    bieu_so_re = re.compile(r'(?<!\w)Biểu số\s+(\d+)\s*:', re.IGNORECASE | re.UNICODE)
    for m in bieu_so_re.finditer(text):
        matches.append((m.start(), 'table'))

    # Chương headings are NOT independent chunks — they belong to the next Điều.
    # Track their positions so we can trim preamble/article tails and prepend to next chunk.
    chuong_re = re.compile(r'^Chương\s+(?:[IVXLCDM]+|\d+)\b[^\n]*', re.MULTILINE | re.UNICODE)
    chuong_positions = [(m.start(), m.end(), m.group(0)) for m in chuong_re.finditer(text)]

    matches = sorted(set(matches), key=lambda x: x[0])

    if not matches:
        return [('article', text.strip())]

    chunks = []
    if matches[0][0] > 0:
        preamble = text[:matches[0][0]].strip()
        if preamble:
            chunks.append(('preamble', preamble))

    for i in range(len(matches)):
        start = matches[i][0]
        kind = matches[i][1]
        end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((kind, chunk))

    # Post-process: move any trailing Chương heading from the end of one chunk
    # to the beginning of the next chunk (so it stays with its articles).
    return chunks
def is_amending_document(text: str) -> bool:
    """
    Check file có phải văn bản sửa đổi/bổ sung không.

    Cách check:
    - Lấy phần trước CHƯƠNG I hoặc Điều 1
    - Nếu phần đó có cụm 'sửa đổi' hoặc 'bổ sung' thì coi là văn bản sửa đổi/bổ sung
    """
    if not text:
        return False

    text = text.replace('\r\n', '\n').replace('\r', '\n')

    first_main_heading = re.search(
        r'^\s*(?:CHƯƠNG\s+I\b|Chương\s+I\b|Điều\s+1\s*[.:])',
        text,
        flags=re.IGNORECASE | re.UNICODE | re.MULTILINE
    )

    preamble = text[:first_main_heading.start()] if first_main_heading else text[:3000]

    return re.search(
        r'\b(sửa\s+đổi|bổ\s+sung)\b',
        preamble,
        flags=re.IGNORECASE | re.UNICODE
    ) is not None

def _is_inside_quote(text: str, pos: int) -> bool:
    quote_depth = 0
    for ch in text[:pos]:
        if ch == '“':
            quote_depth += 1
        elif ch == '”':
            quote_depth = max(0, quote_depth - 1)
        elif ch == '"':
            quote_depth = max(0, quote_depth - 1) if quote_depth else 1
    return quote_depth > 0


def split_amending_article_by_clauses(chunk: str) -> List[str]:
    """
    Với văn bản sửa đổi/bổ sung, tách 1 Điều thành nhiều chunk theo khoản nhỏ.

    Ví dụ:
        Điều 1. Sửa đổi, bổ sung một số điều...
        1) Nội dung khoản 1
        2) Nội dung khoản 2

    Thành:
        Điều 1. Sửa đổi, bổ sung một số điều...
        1) Nội dung khoản 1

        Điều 1. Sửa đổi, bổ sung một số điều...
        2) Nội dung khoản 2
    """
    if not chunk:
        return []

    chunk = chunk.strip()

    # Chỉ xử lý chunk bắt đầu bằng Điều
    if not re.match(r'^\s*Điều\s+\d+\w*\s*[.:]', chunk, flags=re.IGNORECASE | re.UNICODE):
        return [chunk]

    # Tìm các khoản dạng:
    # 1)
    # 2)
    # hoặc 1.
    # hoặc 2.
    clause_re = re.compile(
        r'(?m)^\s*(\d+)(?:\)|\.)\s+'
    )

    matches = [m for m in clause_re.finditer(chunk) if not _is_inside_quote(chunk, m.start())]

    # Không có khoản nhỏ thì giữ nguyên
    if not matches:
        return [chunk]

    article_header = chunk[:matches[0].start()].strip()
    result = []

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(chunk)

        clause_text = chunk[start:end].strip()

        if article_header:
            result.append(article_header + '\n' + clause_text)
        else:
            result.append(clause_text)

    return result

def format_article_annotation_block(content: str) -> str:
    """
    Format ghi chú sửa đổi/bổ sung nằm ngay sau tiêu đề Điều.

    Từ:
        Điều 2. Giải thích từ ngữ [Khoản 7... Điều này... Điều này...] Trong Luật này,...

    Thành:
        Điều 2. Giải thích từ ngữ
        [ Khoản 7...
        Điều này...
        Điều này... ]
        Trong Luật này,...
    """
    if not content:
        return content

    # Chỉ xử lý chunk bắt đầu bằng Điều
    if not re.match(r'^\s*Điều\s+\d+\w*\s*[.:]', content, flags=re.IGNORECASE | re.UNICODE):
        return content

    pattern = re.compile(
        r'^(?P<header>\s*Điều\s+\d+\w*\s*[.:]\s*[^\n\[]+?)\s*'
        r'\[(?P<note>.*?)\]\s*'
        r'(?P<body>.+)$',
        flags=re.IGNORECASE | re.UNICODE | re.DOTALL
    )

    m = pattern.match(content.strip())
    if not m:
        return content

    header = m.group('header').strip()
    note = m.group('note').strip()
    body = m.group('body').strip()

    # Tách các câu "Điều này được..." xuống dòng riêng
    note = re.sub(
        r'\.\s+(?=Điều này được\b)',
        '\n',
        note,
        flags=re.IGNORECASE | re.UNICODE
    )

    # Tách các câu "Khoản ... Điều này..." nếu cần
    note = re.sub(
        r'\s+(?=Khoản\s+\d+\s+Điều này\b)',
        '\n',
        note,
        flags=re.IGNORECASE | re.UNICODE
    )

    return f"{header}\n[ {note} ]\n{body}"
def fix_chapter_heading_duplicate_note(content: str) -> str:
    """
    Fix lỗi heading Chương bị dạng:

        CHƯƠNG IX [note] TÊN CHƯƠNG [note]

    thành:

        CHƯƠNG IX TÊN CHƯƠNG [note]

    Chỉ gộp khi 2 note trong [] giống hệt nhau.
    """
    if not content:
        return content

    pattern = re.compile(
        r'(?P<chapter>\bCHƯƠNG\s+(?:[IVXLCDM]+|\d+)\b)\s*'
        r'\[(?P<note1>[^\]]+)\]\s*'
        r'(?P<title>[A-ZÀ-Ỹ0-9,\s\-–—]+?)\s*'
        r'\[(?P<note2>[^\]]+)\]',
        flags=re.UNICODE | re.IGNORECASE
    )

    def repl(m):
        chapter = m.group('chapter').strip()
        note1 = re.sub(r'\s+', ' ', m.group('note1')).strip()
        note2 = re.sub(r'\s+', ' ', m.group('note2')).strip()
        title = re.sub(r'\s+', ' ', m.group('title')).strip()

        # Chỉ xử lý nếu 2 trích dẫn giống nhau
        if note1.lower() == note2.lower():
            return f"{chapter} {title} [{note2}]"

        # Nếu 2 note khác nhau thì giữ nguyên để tránh làm sai dữ liệu
        return m.group(0)

    return pattern.sub(repl, content)

def _get_token_encoder():
    if tiktoken is None:
        return None
    try:
        return tiktoken.get_encoding("cl100k_base")
    except Exception:
        try:
            return tiktoken.get_encoding("gpt2")
        except Exception:
            return None


def _count_tokens(text: str, encoder) -> int:
    if not text:
        return 0
    if encoder:
        try:
            return len(encoder.encode(text))
        except Exception:
            pass
    return len(text.split())


def _split_by_token_limit(text: str, encoder, max_tokens: int = 15000) -> List[str]:
    if not text:
        return []
    if _count_tokens(text, encoder) <= max_tokens:
        return [text.strip()]

    # 🚨 Over token detected!
    print("⚠️  Over token limit detected – splitting content further.")

    parts = re.split(r'\n\s*\n', text)
    out = []
    cur = ''

    for p in parts:
        p = p.strip()
        if not p:
            continue

        if not cur:
            if _count_tokens(p, encoder) <= max_tokens:
                cur = p
            else:
                lines = [ln for ln in p.splitlines() if ln.strip()]
                cur2 = ''
                for ln in lines:
                    cand = (cur2 + '\n' + ln) if cur2 else ln
                    if _count_tokens(cand, encoder) <= max_tokens:
                        cur2 = cand
                    else:
                        if cur2:
                            out.append(cur2.strip())
                        cur2 = ln
                if cur2:
                    out.append(cur2.strip())
                cur = ''
        else:
            cand = cur + '\n\n' + p
            if _count_tokens(cand, encoder) <= max_tokens:
                cur = cand
            else:
                out.append(cur.strip())
                if _count_tokens(p, encoder) <= max_tokens:
                    cur = p
                else:
                    lines = [ln for ln in p.splitlines() if ln.strip()]
                    cur2 = ''
                    for ln in lines:
                        cand2 = (cur2 + '\n' + ln) if cur2 else ln
                        if _count_tokens(cand2, encoder) <= max_tokens:
                            cur2 = cand2
                        else:
                            if cur2:
                                out.append(cur2.strip())
                            cur2 = ln
                    if cur2:
                        out.append(cur2.strip())
                    cur = ''

    if cur:
        out.append(cur.strip())
    return out


def fix_vb_het_hieu_luc_formatting(content: str) -> str:
    """
    Thêm đúng 1 dấu chấm '.' ngay sau cụm '(VB hết hiệu lực: ...)' 
    nếu ngay sau dấu ')' chưa có dấu chấm.
    Ví dụ: 
        (VB hết hiệu lực: 01/02/2015) → (VB hết hiệu lực: 01/02/2015).
        (VB hết hiệu lực: 15/08/2025). → giữ nguyên
    """
    # Pattern: tìm cụm "(VB hết hiệu lực: dd/mm/yyyy)" 
    # và đảm bảo không thêm chấm nếu đã có chấm ngay sau
    pattern = r'\(VB hết hiệu lực:\s*\d{1,2}/\d{1,2}/\d{4}\)(?!\.)'
    return re.sub(pattern, r'\g<0>.', content)
def remove_link_metadata_labels(text: str) -> str:
    """Remove crawler link metadata while preserving other bracketed content."""
    return re.sub(r'[ \t]*\[(?:JavaScript|ID):[^\]\r\n]*\]', '', text)


def format_file(src_path: Path, out_dir: Path) -> Tuple[Path, int, bool]:
    """Returns (master_path, total_subchunks, has_over_token)"""
    text = src_path.read_text(encoding='utf-8')
    text = remove_link_metadata_labels(text)
    is_amending = is_amending_document(text)
    source_title = extract_title(text, src_path.name)
    title = build_amending_title(source_title, text, is_amending)
    chunks = split_into_chunks(text)
    title_pattern = re.escape(source_title.strip())

    cleaned_chunks = []
    for kind, chunk in chunks:
        c = chunk.strip()
        if not c:
            continue
        c_cleaned = c if kind in {'appendix', 'toc'} else clean_chunk_lines(c, title_pattern).strip()
        if c_cleaned:
            cleaned_chunks.append((kind, c_cleaned))

    chunks = cleaned_chunks
    out_dir.mkdir(parents=True, exist_ok=True)
    master_name = src_path.stem + '.txt'
    master_path = out_dir / master_name

    encoder = _get_token_encoder()
    total_subchunks = 0
    has_over_token = False

    with master_path.open('w', encoding='utf-8') as mf:
        for kind, chunk in chunks:
            if kind in {'appendix', 'toc', 'chapter'}:
                sc_clean = chunk.strip()

                if kind == 'chapter':
                    sc_clean = fix_chapter_heading_duplicate_note(sc_clean)

                sc_clean = fix_vb_het_hieu_luc_formatting(sc_clean)

                mf.write(title.rstrip('.') + '. ' + sc_clean + '\n\n')
                total_subchunks += 1
                continue

            # Nếu là văn bản sửa đổi/bổ sung thì tách Điều thành từng khoản nhỏ
            if is_amending and kind == 'article':
                article_parts = split_amending_article_by_clauses(chunk)
            else:
                article_parts = [chunk]

            for article_part in article_parts:
                subchunks = _split_by_token_limit(article_part, encoder, max_tokens=15000)

                if len(subchunks) > 1:
                    has_over_token = True

                merged = []
                for sc in subchunks:
                    s = sc.strip()
                    if not s:
                        continue

                    first_line = s.splitlines()[0].strip() if s.splitlines() else ''
                    is_table = first_line.startswith('|')
                    is_dieu = re.match(r'^\s*Điều\s+\d+\w*\b', first_line, re.I) is not None

                    if (is_table or is_dieu) and merged:
                        merged[-1] = merged[-1].rstrip() + '\n' + s
                    else:
                        merged.append(s)

                for sc in merged:
                    sc_clean = re.sub(r'\n\s*\n\s*(\|)', r'\n\1', sc)

                    sc_clean = fix_chapter_heading_duplicate_note(sc_clean)
                    sc_clean = format_article_annotation_block(sc_clean)
                    sc_clean = fix_vb_het_hieu_luc_formatting(sc_clean)

                    mf.write(title.rstrip('.') + '. ' + sc_clean.strip() + '\n\n')
                    total_subchunks += 1
           

    return master_path, total_subchunks, has_over_token


def main():
    parser = argparse.ArgumentParser(description='Format crawled files by splitting into Điều chunks')
    parser.add_argument('--input-dir', default='crawl/bo_sung', help='Input directory with crawled .txt files')
    parser.add_argument('--output-dir', default='format/bo_sung', help='Output directory for formatted files')
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.exists() or not input_dir.is_dir():
        print(f"Input dir not found: {input_dir}")
        return

    txt_files = sorted([p for p in input_dir.glob('*.txt') if p.name.lower() != 'failed_urls.txt'])
    if not txt_files:
        print(f"No .txt files found in {input_dir}")
        return

    success_count = 0
    failure_count = 0

    for p in txt_files:
        try:
            master_path, nchunks, has_over_token = format_file(p, output_dir)
            if has_over_token:
                print(f"⚠️  Formatted with over-token split {p.name}: {nchunks} chunks -> {master_path}")
                failure_count += 1
            else:
                print(f"✅ Formatted {p.name}: {nchunks} chunks -> {master_path}")
                success_count += 1
        except Exception as e:
            print(f"❌ Error formatting {p.name}: {e}")
            failure_count += 1  # Xem lỗi runtime cũng là thất bại

    print('\n' + '='*50)
    print(f"✅ Total successful (no over-token): {success_count}")
    print(f"⚠️  Total with over-token or error: {failure_count}")
    print(f"📁 Formatted files written to: {output_dir}")


if __name__ == '__main__':
    main()

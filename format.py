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

    text = text.replace('\r\n', '\n').replace('\r', '\n')
    appendix_heading = r'PHỤ\s+LỤC\s+(?:[IVXLCDM]+|\d+)\b'

    # Only normalize actual appendix headings that start at the beginning of a line.
    # This avoids splitting normal prose such as "theo quy định tại Phụ lục I ...".
    text = re.sub(r'(?m)^[ \t]*(' + appendix_heading + r')', r'\n\n\1', text, flags=re.UNICODE)

    # Unnumbered PHỤ LỤC headings are treated the same way, but only at line start.
    text = re.sub(r'(?m)^[ \t]*(PHỤ LỤC\b)', r'\n\n\1', text, flags=re.UNICODE)

    text = re.sub(r'\n{3,}(?=\s*PHỤ\s+LỤC(?:\s+(?:[IVXLCDM]+|\d+)\b|\b))', '\n\n', text, flags=re.IGNORECASE | re.UNICODE)
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

def extract_title(text: str, filename: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    name = Path(filename).stem
    name = name.replace('_', ' ')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def clean_chunk_lines(chunk: str, title_pattern: str) -> str:
    lines = chunk.splitlines()
    cleaned_lines = []
    noise_re = re.compile(rf'^\s*{title_pattern}\s*\.?\s*$', re.IGNORECASE | re.UNICODE)

    for line in lines:
        if noise_re.fullmatch(line):
            continue
        cleaned_lines.append(line)

    return '\n'.join(cleaned_lines)


def merge_chapter_with_next_article(chunks: List[Chunk], title: str) -> List[Chunk]:
    """Keep short chapter headings in the same output chunk as the next article."""
    merged: List[Chunk] = []
    title_prefix = title.rstrip('.') + '. '
    i = 0

    while i < len(chunks):
        kind, chunk = chunks[i]
        if kind == 'chapter' and i + 1 < len(chunks) and chunks[i + 1][0] == 'article':
            next_kind, next_chunk = chunks[i + 1]
            combined = chunk.strip() + '\n' + title_prefix + next_chunk.strip()
            merged.append((next_kind, combined))
            i += 2
            continue

        merged.append((kind, chunk))
        i += 1

    return merged


def _is_inside_quote(text: str, pos: int) -> bool:
    """
    Kiểm tra vị trí pos có đang nằm TRONG một đoạn trích dẫn (ngoặc kép) hay không,
    bằng cách đếm độ sâu ngoặc kép tính từ đầu văn bản tới pos.

    Dùng để bỏ qua các "Điều N"/"CHƯƠNG ..." nằm trong trích dẫn (ví dụ văn bản
    sửa đổi trích lại nguyên văn điều luật) — chúng là nội dung, không phải tiêu đề,
    nên không được tách thành chunk riêng.
    """
    quote_depth = 0
    for ch in text[:pos]:
        if ch == '“':
            quote_depth += 1
        elif ch == '”':
            quote_depth = max(0, quote_depth - 1)
        elif ch == '"':
            quote_depth = max(0, quote_depth - 1) if quote_depth else 1
    return quote_depth > 0


def split_into_chunks(text: str) -> List[Chunk]:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    text = normalize_appendix_breaks(text)
    text = normalize_chapter_breaks(text)
    matches = []

    # TẦNG 1: nhận diện Điều theo dạng chuẩn "Điều N." / "Điều N:" (có dấu . hoặc :).
    # Bỏ qua "Điều N" nằm trong ngoặc kép (trích dẫn) — đó là nội dung, không phải tiêu đề.
    dieu_re = re.compile(r'^\s*Điều\s+(\d+\w*)\s*[.:]', re.IGNORECASE | re.UNICODE | re.MULTILINE)
    article_matches = [
        (m.start(), 'article') for m in dieu_re.finditer(text)
        if not _is_inside_quote(text, m.start())
    ]

    # TẦNG 2 (fallback): CHỈ khi cả bài KHÔNG có "Điều N." nào (có dấu) thì mới xét dạng
    # "Điều N" thiếu dấu — chỉ cần "Điều + số" ở đầu dòng (theo sau là khoảng trắng/cuối
    # dòng). Không đòi chữ IN HOA vì tiêu đề Điều không nhất thiết bắt đầu bằng chữ hoa.
    # Gate tầng 1 đã bảo đảm bài bình thường (có dấu) không đụng tới nhánh này.
    if not article_matches:
        dieu_nodot_re = re.compile(
            r'^\s*Điều\s+\d+\w*\b',
            re.IGNORECASE | re.UNICODE | re.MULTILINE
        )
        article_matches = [
            (m.start(), 'article') for m in dieu_nodot_re.finditer(text)
            if not _is_inside_quote(text, m.start())
        ]

    matches.extend(article_matches)
    chapter_re = re.compile(
        r'^\s*CHƯƠNG\s+(?:[IVXLCDM]+|\d+)\b[^\n]*',
        re.MULTILINE | re.UNICODE | re.IGNORECASE
    )

    for m in chapter_re.finditer(text):
        # Bỏ qua CHƯƠNG nằm trong ngoặc kép (trích dẫn).
        if _is_inside_quote(text, m.start()):
            continue
        matches.append((m.start(), 'chapter'))

    # Mục (tiểu mục): "Mục N" / "MỤC N" đầu dòng (số hoặc số La Mã) — cũng là ranh giới
    # để mỗi Điều mang breadcrumb Mục hiện hành. Không dùng IGNORECASE để tránh bắt nhầm
    # tham chiếu chữ thường "mục 2 ..."; "MỤC LỤC" không khớp vì "LỤC" không phải số.
    muc_re = re.compile(r'^\s*(?:Mục|MỤC)\s+(?:\d+|[IVXLCDM]+)\b[^\n]*', re.MULTILINE | re.UNICODE)
    for m in muc_re.finditer(text):
        # Bỏ qua Mục nằm trong ngoặc kép (trích dẫn).
        if _is_inside_quote(text, m.start()):
            continue
        matches.append((m.start(), 'section'))

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
        r'\[(?P<note>.*?)\](?!\()\s*'   # (?!\() : không nuốt link markdown [text](url)
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

def _find_bracket_annotations(text: str):
    """
    Tìm mọi ghi chú dạng [ ... ] ở cấp NGOÀI CÙNG (bỏ qua link markdown [text](url)).
    Xử lý được ngoặc vuông LỒNG nhau (vd nội dung viện dẫn có footnote [1]).
    Trả về list (start, end, inner_text); end là vị trí NGAY SAU dấu ']' ngoài cùng.
    """
    spans = []
    i, n = 0, len(text)
    while i < n:
        if text[i] == '[':
            depth = 1
            j = i + 1
            while j < n and depth > 0:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                j += 1
            if depth != 0:
                break  # ngoặc không cân -> dừng an toàn, không đụng gì
            end = j
            if end < n and text[end] == '(':
                # [text](url) -> link markdown, KHÔNG phải ghi chú -> bỏ qua
                i = end
                continue
            spans.append((i, end, text[i + 1:end - 1]))
            i = end
        else:
            i += 1
    return spans


def merge_article_duplicate_annotations(content: str) -> str:
    """
    Gộp ghi chú viện dẫn/bổ sung bị LẶP trong 1 chunk Điều.

    Chỉ gộp khi THỎA CẢ HAI điều kiện:
      (1) Tiêu đề Điều có 1 ghi chú [A] (viện dẫn/bổ sung) — [A] nằm ngay sau
          "Điều N. <tên điều>", trước bất kỳ khoản/nội dung nào.
      (2) MỌI ghi chú [..] khác trong nội dung Điều đều GIỐNG HỆT [A]
          (chuẩn hoá khoảng trắng), bất kể nằm ở đâu trong nội dung.
      => giữ đúng 1 [A] trên tiêu đề Điều, xoá các bản lặp trong nội dung.

    Chỉ cần có 1 ghi chú khác biệt (dù chỉ khác một chút), hoặc tiêu đề Điều
    không mang ghi chú -> GIỮ NGUYÊN toàn bộ (không đụng gì).
    """
    if not content:
        return content
    # Chấp nhận cả "Điều N." lẫn "Điều N" KHÔNG dấu chấm (vd Hiến pháp: "Điều 2 [..]").
    if not re.match(r'^\s*Điều\s+\d+\w*\b', content, flags=re.IGNORECASE | re.UNICODE):
        return content

    anns = _find_bracket_annotations(content)
    if len(anns) < 2:
        return content

    def _norm(s: str) -> str:
        return re.sub(r'\s+', ' ', s).strip()

    # (1) ghi chú ĐẦU TIÊN phải nằm TRÊN TIÊU ĐỀ Điều: phần trước nó chỉ gồm
    #     "Điều N. <tên điều>" — tên điều không được chứa khoản "N." hay ngoặc kép.
    first_start = anns[0][0]
    head = content[:first_start]
    m = re.match(r'^\s*Điều\s+\d+\w*\s*[.:]?\s*', head, flags=re.IGNORECASE | re.UNICODE)
    title_only = head[m.end():] if m else head
    if re.search(r'\d+\s*[.)]\s', title_only) or any(q in title_only for q in ('"', '“', '”')):
        return content

    a_text = _norm(anns[0][2])
    if not a_text:
        return content

    # (2) mọi ghi chú đều phải giống hệt A; chỉ cần 1 cái khác -> giữ nguyên tất
    if any(_norm(s[2]) != a_text for s in anns):
        return content

    # Gộp: giữ ghi chú đầu (trên tiêu đề), xoá các ghi chú còn lại theo offset.
    pieces = []
    prev = 0
    for s, e, _ in anns[1:]:
        pieces.append(content[prev:s])
        prev = e
    pieces.append(content[prev:])
    result = ''.join(pieces)

    # Dọn khoảng trắng thừa do chỗ xoá để lại
    result = re.sub(r'[ \t]{2,}', ' ', result)
    result = re.sub(r' +\n', '\n', result)
    result = re.sub(r'\n +', '\n', result)
    return result


_GHI_CHU_RE = re.compile(r'ghi\s*chú\s*:', re.IGNORECASE | re.UNICODE)
# Chỉ xóa phụ lục BIỂU MẪU (có chữ "mẫu": "Phụ lục 02 mẫu", "mẫu đơn", "Mẫu số"...).
# Phụ lục nội dung thường (KHÔNG có chữ "mẫu") thì GIỮ lại.
_HAS_MAU_RE = re.compile(r'mẫu', re.IGNORECASE | re.UNICODE)


def drop_appendix_chunks(chunks: List[Chunk]) -> List[Chunk]:
    """
    Xóa phần PHỤ LỤC BIỂU MẪU ở cuối văn bản — URL biểu mẫu đã lấy ở bước crawl.
    CHỈ xóa phụ lục có chữ "mẫu" (biểu mẫu); phụ lục nội dung thường thì giữ nguyên.

    Bắt đầu từ chunk 'appendix' ĐẦU TIÊN:
      - Nếu KHÔNG tìm thấy dòng "Ghi chú:" nào ở phần dưới -> xóa HẾT tới cuối văn
        bản, không dừng lại.
      - Nếu CÓ "Ghi chú:" -> xóa qua HẾT ghi chú CUỐI CÙNG (kèm nội dung của nó,
        tức tới hết chunk chứa ghi chú cuối) rồi ngưng; chỉ giữ lại nội dung thật
        (nếu có) nằm SAU ghi chú cuối cùng.

    Dùng ghi chú CUỐI (không phải ghi chú đầu) để không bỏ sót: các biểu mẫu thường
    có nhiều dòng "Ghi chú:" nằm rải rác, và đôi khi có chunk 'article'/'table' giả
    do nội dung biểu mẫu sinh ra ở giữa — mốc "ghi chú cuối" bảo đảm xóa sạch hết.
    """
    first = next((i for i, (k, c) in enumerate(chunks)
                  if k == 'appendix' and _HAS_MAU_RE.search(c)), None)
    if first is None:
        return chunks

    # Chunk CUỐI CÙNG (từ phụ lục trở đi) có chứa "Ghi chú:".
    last_ghichu = None
    for j in range(first, len(chunks)):
        if _GHI_CHU_RE.search(chunks[j][1]):
            last_ghichu = j

    # Không có "Ghi chú:" -> xóa hết tới cuối văn bản.
    if last_ghichu is None:
        return chunks[:first]

    # Có "Ghi chú:" -> xóa từ phụ lục qua hết chunk chứa ghi chú cuối rồi ngưng.
    return chunks[:first] + chunks[last_ghichu + 1:]


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


# Mẫu khoản "N." (số + '.' + khoảng trắng) và tập ranh giới câu đứng ngay trước nó.
_QUOTE_CLAUSE_RE = re.compile(r'\d+\.\s')
_QUOTE_CLAUSE_BOUNDARY = set('.;:]')


def break_numbered_items_in_quotes(text: str) -> str:
    """
    Xuống dòng cho các mục dạng "N." (1. , 2. , 10. ...) nằm BÊN TRONG ngoặc kép —
    nhưng KHÔNG coi chúng là chunk (chỉ thêm ký tự xuống dòng để dễ đọc, việc tách
    chunk vẫn bỏ qua nội dung trong ngoặc kép như cũ).

    Hai trường hợp:
      - "N." nằm giữa nội dung trong ngoặc kép (đứng sau dấu kết câu . ; : hoặc "]")
        -> chèn xuống dòng NGAY TRƯỚC "N.".
      - "N." nằm NGAY ĐẦU ngoặc kép (vd: abc. "1. Baby...") -> chèn xuống dòng
        NGAY TRƯỚC dấu mở ngoặc kép, để cả đoạn trích dẫn xuống dòng.

    Không tách khi "N." là số của "Điều N."/"khoản N." (đứng sau chữ cái) hay là năm/
    ngày (vd "... năm 2016."), vì các số này KHÔNG đứng sau ranh giới câu. Cũng không
    đụng tới nội dung bên trong ghi chú [ ... ].
    """
    if not text:
        return text

    out = []
    quote_depth = 0
    bracket_depth = 0
    i, n = 0, len(text)

    while i < n:
        ch = text[i]

        # Không tách khoản bên trong ghi chú [ ... ]
        if ch == '[':
            bracket_depth += 1
            out.append(ch)
            i += 1
            continue
        if ch == ']':
            bracket_depth = max(0, bracket_depth - 1)
            out.append(ch)
            i += 1
            continue

        is_open = (ch == '“') or (ch == '"' and quote_depth == 0)
        is_close = (ch == '”') or (ch == '"' and quote_depth > 0)

        # Dấu MỞ ngoặc kép: nếu ngay sau (bỏ qua khoảng trắng) là "N." thì xuống dòng
        # TRƯỚC dấu mở ngoặc kép.
        if is_open:
            j = i + 1
            while j < n and text[j] in ' \t':
                j += 1
            if bracket_depth == 0 and _QUOTE_CLAUSE_RE.match(text, j):
                while out and out[-1] in ' \t':
                    out.pop()
                if out and out[-1] != '\n':
                    out.append('\n')
            out.append(ch)
            quote_depth += 1
            i += 1
            continue

        if is_close:
            out.append(ch)
            quote_depth = max(0, quote_depth - 1)
            i += 1
            continue

        # Đang TRONG ngoặc kép (ngoài ghi chú): gặp "N." khoản (đứng sau ranh giới câu)
        # -> xuống dòng ngay trước nó.
        if (quote_depth > 0 and bracket_depth == 0
                and ch.isdigit() and _QUOTE_CLAUSE_RE.match(text, i)):
            k = len(out) - 1
            while k >= 0 and out[k] in ' \t':
                k -= 1
            prev = out[k] if k >= 0 else ''
            if prev in _QUOTE_CLAUSE_BOUNDARY:
                while out and out[-1] in ' \t':
                    out.pop()
                if out and out[-1] != '\n':
                    out.append('\n')

        out.append(ch)
        i += 1

    return ''.join(out)


def format_file(src_path: Path, out_dir: Path) -> Tuple[Path, int, bool]:
    """Returns (master_path, total_subchunks, has_over_token)"""
    text = src_path.read_text(encoding='utf-8')
    title = extract_title(text, src_path.name)
    chunks = split_into_chunks(text)
    title_pattern = re.escape(title.strip())

    cleaned_chunks = []
    for kind, chunk in chunks:
        c = chunk.strip()
        if not c:
            continue
        c_cleaned = c if kind in {'appendix', 'toc'} else clean_chunk_lines(c, title_pattern).strip()
        if c_cleaned:
            cleaned_chunks.append((kind, c_cleaned))

    chunks = cleaned_chunks
    # Xóa phần PHỤ LỤC (biểu mẫu) ở cuối + phần "Ghi chú:" — URL biểu mẫu đã lấy khi crawl.
    chunks = drop_appendix_chunks(chunks)
    # Chương KHÔNG còn là chunk riêng: tiêu đề chương được ghép vào tiền tố của
    # mọi Điều thuộc chương đó (xử lý trong vòng ghi bên dưới qua current_chapter).
    out_dir.mkdir(parents=True, exist_ok=True)
    master_name = src_path.stem + '.txt'
    master_path = out_dir / master_name

    encoder = _get_token_encoder()
    total_subchunks = 0
    has_over_token = False

    current_chapter = ''  # tiêu đề chương hiện hành để ghép vào tiền tố mỗi Điều
    current_muc = ''      # tiêu đề Mục hiện hành (reset mỗi khi sang chương mới)

    with master_path.open('w', encoding='utf-8') as mf:
        for kind, chunk in chunks:
            # Chương: không ghi thành chunk riêng, chỉ lưu tiêu đề để ghép vào
            # tiền tố các Điều thuộc chương này.
            if kind == 'chapter':
                # Giữ nguyên footnote/ghi chú [ ... ] dính trên chương để nó "đi theo"
                # breadcrumb của mỗi Điều; chỉ gộp lại khi note bị lặp 2 lần quanh tên chương.
                heading = fix_chapter_heading_duplicate_note(chunk.strip())
                heading = re.sub(r'\s+', ' ', heading).strip()
                # Nếu có "Mục N ..." bị DÍNH vào cuối tiêu đề chương (nguồn crawl ghép cùng
                # dòng) thì tách ra: phần trước là tên chương, phần "Mục N ..." trở thành Mục
                # hiện hành. Nhờ vậy khi sang Mục mới, Mục cũ được THAY chứ không kẹt lại
                # trong breadcrumb chương. ("MỨC" khác "MỤC" nên "MỨC PHẠT" không bị dính.)
                msec = re.search(r'(?:Mục|MỤC)\s+(?:\d+|[IVXLCDM]+)\b.*$', heading)
                if msec:
                    current_muc = msec.group(0).strip()
                    heading = heading[:msec.start()].strip()
                else:
                    current_muc = ''  # sang chương mới -> quên Mục cũ
                if heading:
                    current_chapter = heading
                continue

            # Mục: cũng không ghi thành chunk riêng, chỉ lưu tiêu đề (giữ nguyên
            # footnote/ghi chú) để ghép vào breadcrumb các Điều thuộc Mục này.
            if kind == 'section':
                heading = re.sub(r'\s+', ' ', chunk.strip()).strip()
                if heading:
                    current_muc = heading
                continue

            if kind in {'appendix', 'toc'}:
                sc_clean = break_numbered_items_in_quotes(chunk.strip())
                mf.write(title.rstrip('.') + '. ' + sc_clean + '\n\n')
                total_subchunks += 1
                continue

            # Tiền tố: "<tên văn bản>. [<chương>. ][<Mục>. ]" — chỉ Điều mới kèm chương/Mục.
            prefix = title.rstrip('.') + '. '
            if kind == 'article':
                if current_chapter:
                    prefix += current_chapter.rstrip('.') + '. '
                if current_muc:
                    prefix += current_muc.rstrip('.') + '. '

            subchunks = _split_by_token_limit(chunk, encoder, max_tokens=15000)
            if len(subchunks) > 1:
                has_over_token = True  # ✅ Flag this file as over-token

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
                # Fix lỗi CHƯƠNG IX [note] TÊN CHƯƠNG [note]
                sc_clean = fix_chapter_heading_duplicate_note(sc_clean)
                # Gộp ghi chú viện dẫn/bổ sung bị lặp: nếu tiêu đề Điều và TOÀN BỘ
                # ghi chú trong nội dung đều giống hệt nhau thì giữ 1 cái trên tiêu đề.
                sc_clean = merge_article_duplicate_annotations(sc_clean)
                # Format ghi chú nằm sau tiêu đề Điều
                sc_clean = format_article_annotation_block(sc_clean)
                # Apply the VB hết hiệu lực formatting fix
                sc_clean = fix_vb_het_hieu_luc_formatting(sc_clean)
                # Xuống dòng cho các mục "N." nằm trong ngoặc kép (không tạo chunk)
                sc_clean = break_numbered_items_in_quotes(sc_clean)
                mf.write(prefix + sc_clean.strip() + '\n\n')
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

import csv
import io
import re
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree
from pypdf import PdfReader
from docx import Document as DocxDocument
from openpyxl import load_workbook
import xlrd
from xlrd.biffh import XLRDError

SUPPORTED = {".pdf", ".docx", ".txt", ".xls", ".xlsx"}

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^\s*(Page\s+\d+|\d+\s*/\s*\d+)\s*$", "", text, flags=re.I)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)-\n(?=\w)", "", text)
    return text.strip()

def decode_bytes(raw: bytes) -> str:
    """Detect encoding and decode binary content safely."""
    if not raw:
        return ""
    # Check Byte Order Marks (BOM)
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16", errors="replace")
        except Exception:
            pass
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig", errors="replace")
        except Exception:
            pass

    # Heuristic for UTF-16LE without BOM (common in MS exports: null byte every second byte)
    if len(raw) >= 4:
        even_nulls = raw[1::2].count(b"\x00")
        if even_nulls > len(raw) // 4:
            try:
                decoded = raw.decode("utf-16le", errors="replace")
                if len(decoded) > 0 and "\x00" not in decoded[:100]:
                    return decoded
            except Exception:
                pass

    # Try UTF-8 first
    try:
        decoded = raw.decode("utf-8")
        return decoded
    except UnicodeDecodeError:
        pass

    # Try Windows-1252 / Latin-1
    for enc in ("cp1252", "latin-1", "utf-16"):
        try:
            return raw.decode(enc, errors="replace")
        except Exception:
            continue

    return raw.decode("utf-8", errors="replace")

def extract_pdf(path: Path) -> list[dict]:
    try:
        reader = PdfReader(str(path))
        blocks = []
        for page_no, page in enumerate(reader.pages, start=1):
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            text = clean_text(page_text)
            if text:
                blocks.append({"location": f"Page {page_no}", "text": text})
        return blocks
    except Exception as exc:
        raise RuntimeError(f"Failed to read PDF '{path.name}': {exc}") from exc

def extract_docx(path: Path) -> list[dict]:
    try:
        doc = DocxDocument(str(path))
        blocks = []
        for i, p in enumerate(doc.paragraphs, start=1):
            text = clean_text(p.text)
            if text:
                blocks.append({"location": f"Paragraph {i}", "text": text})
        for ti, table in enumerate(doc.tables, start=1):
            rows = []
            for row in table.rows:
                cells = [clean_text(cell.text) for cell in row.cells]
                row_str = " | ".join(c for c in cells if c)
                if row_str:
                    rows.append(row_str)
            table_text = clean_text("\n".join(rows))
            if table_text:
                blocks.append({"location": f"Table {ti}", "text": table_text})
        return blocks
    except Exception as exc:
        raise RuntimeError(f"Failed to read DOCX '{path.name}': {exc}") from exc

def extract_txt(path: Path) -> list[dict]:
    try:
        raw = path.read_bytes()
        text = clean_text(decode_bytes(raw))
        return [{"location": "Text document", "text": text}] if text else []
    except Exception as exc:
        raise RuntimeError(f"Failed to read TXT '{path.name}': {exc}") from exc

def extract_xlsx(path: Path) -> list[dict]:
    # Try openpyxl first
    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
        blocks = []
        try:
            for worksheet in workbook.worksheets:
                for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                    values = []
                    for value in row:
                        if value is None:
                            continue
                        if isinstance(value, float) and value.is_integer():
                            values.append(str(int(value)))
                        else:
                            cleaned = clean_text(str(value))
                            if cleaned:
                                values.append(cleaned)
                    text = clean_text(" | ".join(values))
                    if text:
                        blocks.append({
                            "location": f"Sheet {worksheet.title}, Row {row_number}",
                            "text": text,
                        })
        finally:
            workbook.close()
        if blocks:
            return blocks
    except Exception:
        pass

    # If openpyxl fails, it might be a binary XLS or HTML/XML saved as .xlsx
    try:
        return extract_xls(path)
    except Exception:
        return extract_textual_spreadsheet(path)

def extract_xls(path: Path) -> list[dict]:
    # 1. Try standard binary Excel (xlrd)
    try:
        workbook = xlrd.open_workbook(str(path), on_demand=True)
        blocks = []
        try:
            for sheet_number in range(workbook.nsheets):
                worksheet = workbook.sheet_by_index(sheet_number)
                for row_number in range(worksheet.nrows):
                    row_vals = worksheet.row_values(row_number)
                    values = []
                    for val in row_vals:
                        if val == "" or val is None:
                            continue
                        if isinstance(val, float) and val.is_integer():
                            values.append(str(int(val)))
                        else:
                            cleaned = clean_text(str(val))
                            if cleaned:
                                values.append(cleaned)
                    text = clean_text(" | ".join(values))
                    if text:
                        blocks.append({
                            "location": f"Sheet {worksheet.name}, Row {row_number + 1}",
                            "text": text,
                        })
        finally:
            workbook.release_resources()
        if blocks:
            return blocks
    except Exception:
        pass

    # 2. Try openpyxl in case it's actually an OpenXML .xlsx file named .xls
    try:
        blocks = extract_xlsx(path)
        if blocks:
            return blocks
    except Exception:
        pass

    # 3. Fallback to textual spreadsheet (HTML tables, XML SpreadsheetML, CSV/TSV)
    return extract_textual_spreadsheet(path)

class _RobustHTMLTableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.all_text_blocks: list[str] = []
        self._tag_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        t = tag.lower()
        self._tag_stack.append(t)
        if t == "tr":
            if self.current_row is not None and any(self.current_row):
                self.rows.append(self.current_row)
            self.current_row = []
        elif t in {"td", "th"}:
            if self.current_row is None:
                self.current_row = []
            if self.current_cell is not None:
                cell_text = clean_text(" ".join(self.current_cell))
                if cell_text:
                    self.current_row.append(cell_text)
            self.current_cell = []
        elif t in {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"}:
            if self.current_cell is not None:
                self.current_cell.append("\n")

    def handle_data(self, data: str):
        cleaned = data.strip()
        if not cleaned:
            return
        if self.current_cell is not None:
            self.current_cell.append(cleaned)
        elif self.current_row is not None:
            self.current_row.append(cleaned)
        else:
            self.all_text_blocks.append(cleaned)

    def handle_endtag(self, tag: str):
        t = tag.lower()
        if t in {"td", "th"}:
            if self.current_cell is not None:
                cell_text = clean_text(" ".join(self.current_cell))
                if cell_text and self.current_row is not None:
                    self.current_row.append(cell_text)
                self.current_cell = None
        elif t == "tr":
            if self.current_cell is not None:
                cell_text = clean_text(" ".join(self.current_cell))
                if cell_text and self.current_row is not None:
                    self.current_row.append(cell_text)
                self.current_cell = None
            if self.current_row is not None and any(self.current_row):
                self.rows.append(self.current_row)
            self.current_row = None
        if self._tag_stack and self._tag_stack[-1] == t:
            self._tag_stack.pop()

    def close(self):
        super().close()
        if self.current_cell is not None and self.current_row is not None:
            cell_text = clean_text(" ".join(self.current_cell))
            if cell_text:
                self.current_row.append(cell_text)
            self.current_cell = None
        if self.current_row is not None and any(self.current_row):
            self.rows.append(self.current_row)
            self.current_row = None

def extract_textual_spreadsheet(path: Path) -> list[dict]:
    raw = path.read_bytes()
    text = decode_bytes(raw)
    if not text.strip():
        return []

    # 1. Try HTML Table Parser
    try:
        parser = _RobustHTMLTableParser()
        parser.feed(text)
        parser.close()
        valid_rows = [
            {"location": f"Sheet 1, Row {idx}", "text": " | ".join(row)}
            for idx, row in enumerate(parser.rows, start=1)
            if any(row)
        ]
        if valid_rows:
            return valid_rows

        if parser.all_text_blocks:
            combined = clean_text("\n".join(parser.all_text_blocks))
            if combined:
                return [{"location": "Document Content", "text": combined}]
    except Exception:
        pass

    # 2. Try XML SpreadsheetML (Spreadsheet 2003 / Excel XML)
    try:
        # Regex extraction for XML rows & cells to tolerate namespaces & unescaped entities
        row_matches = re.findall(r"<(?:\w+:)?Row\b[^>]*>(.*?)</(?:\w+:)?Row>", text, flags=re.DOTALL | re.IGNORECASE)
        if row_matches:
            blocks = []
            for row_idx, row_content in enumerate(row_matches, start=1):
                data_matches = re.findall(r"<(?:\w+:)?Data\b[^>]*>(.*?)</(?:\w+:)?Data>", row_content, flags=re.DOTALL | re.IGNORECASE)
                if not data_matches:
                    data_matches = re.findall(r"<(?:\w+:)?Cell\b[^>]*>(.*?)</(?:\w+:)?Cell>", row_content, flags=re.DOTALL | re.IGNORECASE)
                cells = [clean_text(re.sub(r"<[^>]+>", "", cell)) for cell in data_matches]
                cells = [c for c in cells if c]
                if cells:
                    blocks.append({"location": f"Sheet 1, Row {row_idx}", "text": " | ".join(cells)})
            if blocks:
                return blocks
    except Exception:
        pass

    # 3. Try Standard XML parsing with ElementTree
    try:
        root = ElementTree.fromstring(text)
        rows = []
        for row in root.iter():
            if row.tag.rsplit("}", 1)[-1].lower() == "row":
                values = [clean_text("".join(cell.itertext())) for cell in row]
                values = [v for v in values if v]
                if values:
                    rows.append(values)
        if rows:
            return [
                {"location": f"Sheet 1, Row {idx}", "text": " | ".join(row)}
                for idx, row in enumerate(rows, start=1)
            ]
    except Exception:
        pass

    # 4. Try CSV / TSV / Delimited Table
    try:
        # Check first 5 lines for common delimiters
        sample = "\n".join(text.splitlines()[:10])
        delimiter = "\t" if "\t" in sample else ("," if "," in sample else None)
        if delimiter:
            reader = csv.reader(io.StringIO(text), delimiter=delimiter)
            blocks = []
            for idx, row in enumerate(reader, start=1):
                cleaned_cells = [clean_text(cell) for cell in row if clean_text(cell)]
                if cleaned_cells:
                    blocks.append({"location": f"Row {idx}", "text": " | ".join(cleaned_cells)})
            if blocks:
                return blocks
    except Exception:
        pass

    # 5. Plain text fallback: line by line
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    if lines:
        return [{"location": f"Line {idx}", "text": line} for idx, line in enumerate(lines, start=1)]

    raise ValueError(f"Unable to extract readable text or spreadsheet data from {path.name}")

def extract_blocks(path: str) -> list[dict]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext == ".pdf":
        return extract_pdf(p)
    if ext == ".docx":
        return extract_docx(p)
    if ext == ".txt":
        return extract_txt(p)
    if ext == ".xls":
        return extract_xls(p)
    if ext == ".xlsx":
        return extract_xlsx(p)
    raise ValueError(f"Unsupported file type: {p.suffix}")

def chunk_blocks(blocks: list[dict], chunk_size: int, overlap: int) -> list[dict]:
    """
    Optimized chunking: Aggregate small adjacent blocks (e.g. spreadsheet rows or paragraphs)
    into cohesive context chunks up to chunk_size with overlap, preventing excessive database rows
    and micro-chunks.
    """
    if not blocks:
        return []
    if overlap >= chunk_size:
        overlap = max(0, chunk_size // 4)

    chunks = []
    current_text_parts: list[str] = []
    current_start_loc = ""
    current_end_loc = ""
    current_len = 0

    for block in blocks:
        block_text = block["text"].strip()
        if not block_text:
            continue
        loc = block.get("location", "")

        # If a single block exceeds chunk_size, split it internally
        if len(block_text) > chunk_size:
            # Flush current accumulator first
            if current_text_parts:
                loc_label = f"{current_start_loc} – {current_end_loc}" if current_start_loc != current_end_loc else current_start_loc
                chunks.append({"text": "\n".join(current_text_parts), "location": loc_label})
                current_text_parts = []
                current_len = 0

            # Split large block
            start = 0
            while start < len(block_text):
                end = min(len(block_text), start + chunk_size)
                piece = block_text[start:end].strip()
                if piece:
                    chunks.append({"text": piece, "location": loc})
                if end >= len(block_text):
                    break
                start = end - overlap
            continue

        # Check if adding this block exceeds chunk_size
        projected = current_len + len(block_text) + (1 if current_text_parts else 0)
        if current_text_parts and projected > chunk_size:
            loc_label = f"{current_start_loc} – {current_end_loc}" if current_start_loc != current_end_loc else current_start_loc
            chunks.append({"text": "\n".join(current_text_parts), "location": loc_label})

            # Start new chunk with overlap from previous items if applicable
            current_text_parts = [block_text]
            current_start_loc = loc
            current_end_loc = loc
            current_len = len(block_text)
        else:
            if not current_text_parts:
                current_start_loc = loc
            current_text_parts.append(block_text)
            current_end_loc = loc
            current_len += len(block_text) + 1

    if current_text_parts:
        loc_label = f"{current_start_loc} – {current_end_loc}" if current_start_loc != current_end_loc else current_start_loc
        chunks.append({"text": "\n".join(current_text_parts), "location": loc_label})

    return chunks


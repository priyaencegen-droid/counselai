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
    text = text.replace("\x00", " ").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"(?m)^\s*(Page\s+\d+|\d+\s*/\s*\d+)\s*$", "", text, flags=re.I)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<!\n)-\n(?=\w)", "", text)
    return text.strip()

def extract_pdf(path: Path) -> list[dict]:
    reader = PdfReader(str(path))
    blocks = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = clean_text(page.extract_text() or "")
        if text:
            blocks.append({"location": f"Page {page_no}", "text": text})
    return blocks

def extract_docx(path: Path) -> list[dict]:
    doc = DocxDocument(str(path))
    blocks = []
    for i, p in enumerate(doc.paragraphs, start=1):
        text = clean_text(p.text)
        if text:
            blocks.append({"location": f"Paragraph {i}", "text": text})
    for ti, table in enumerate(doc.tables, start=1):
        rows = [" | ".join(clean_text(cell.text) for cell in row.cells) for row in table.rows]
        table_text = clean_text("\n".join(rows))
        if table_text:
            blocks.append({"location": f"Table {ti}", "text": table_text})
    return blocks

def extract_txt(path: Path) -> list[dict]:
    text = clean_text(path.read_text(encoding="utf-8", errors="replace"))
    return [{"location": "Text document", "text": text}] if text else []

def extract_xlsx(path: Path) -> list[dict]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    blocks = []
    try:
        for worksheet in workbook.worksheets:
            for row_number, row in enumerate(worksheet.iter_rows(values_only=True), start=1):
                values = [clean_text(str(value)) for value in row if value is not None]
                text = clean_text(" | ".join(values))
                if text:
                    blocks.append({
                        "location": f"Sheet {worksheet.title}, Row {row_number}",
                        "text": text,
                    })
    finally:
        workbook.close()
    return blocks

def extract_xls(path: Path) -> list[dict]:
    try:
        workbook = xlrd.open_workbook(path, on_demand=True)
    except XLRDError:
        return extract_textual_spreadsheet(path)
    blocks = []
    try:
        for sheet_number in range(workbook.nsheets):
            worksheet = workbook.sheet_by_index(sheet_number)
            for row_number in range(worksheet.nrows):
                values = [clean_text(str(value)) for value in worksheet.row_values(row_number) if value != ""]
                text = clean_text(" | ".join(values))
                if text:
                    blocks.append({
                        "location": f"Sheet {worksheet.name}, Row {row_number + 1}",
                        "text": text,
                    })
    finally:
        workbook.release_resources()
    return blocks

class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs):
        if tag == "tr":
            self.current_row = []
        elif tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data: str):
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str):
        if tag in {"td", "th"} and self.current_row is not None and self.current_cell is not None:
            self.current_row.append(clean_text(" ".join(self.current_cell)))
            self.current_cell = None
        elif tag == "tr" and self.current_row:
            self.rows.append(self.current_row)
            self.current_row = None

def extract_textual_spreadsheet(path: Path) -> list[dict]:
    raw = path.read_bytes()
    encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
    text = raw.decode(encoding, errors="replace")
    parser = _TableParser()
    parser.feed(text)
    if parser.rows:
        return [
            {"location": f"Sheet 1, Row {row_number}", "text": " | ".join(value for value in row if value)}
            for row_number, row in enumerate(parser.rows, start=1)
            if any(row)
        ]
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError as exc:
        raise ValueError("The .xls file is not a binary Excel workbook or readable spreadsheet HTML/XML") from exc
    rows = []
    for row in root.iter():
        if row.tag.rsplit("}", 1)[-1].lower() == "row":
            values = [clean_text("".join(cell.itertext())) for cell in row]
            if any(values):
                rows.append(values)
    return [
        {"location": f"Sheet 1, Row {row_number}", "text": " | ".join(value for value in row if value)}
        for row_number, row in enumerate(rows, start=1)
    ]

def extract_blocks(path: str) -> list[dict]:
    p = Path(path)
    if p.suffix.lower() == ".pdf": return extract_pdf(p)
    if p.suffix.lower() == ".docx": return extract_docx(p)
    if p.suffix.lower() == ".txt": return extract_txt(p)
    if p.suffix.lower() == ".xls": return extract_xls(p)
    if p.suffix.lower() == ".xlsx": return extract_xlsx(p)
    raise ValueError(f"Unsupported file type: {p.suffix}")

def chunk_blocks(blocks: list[dict], chunk_size: int, overlap: int) -> list[dict]:
    if overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
    chunks = []
    for block in blocks:
        text = block["text"]
        start = 0
        while start < len(text):
            end = min(len(text), start + chunk_size)
            piece = text[start:end].strip()
            if piece:
                chunks.append({"text": piece, "location": block["location"]})
            if end >= len(text):
                break
            start = end - overlap
    return chunks

# XploVoice | Copyright (c) 2026 Xplosys. All rights reserved. | Confidential - Proprietary to Xplosys
"""Knowledge-base ingestion (M12): malware scan, type detection from content (never from the file name),
text extraction and chunking.

Scanning: ClamAV (clamd, INSTREAM over TCP) is the scanner (Phase 0 decision). Without one configured, the
built-in development scanner is used in development and test only; in staging and production an upload is refused
until ClamAV is configured, so nothing unscanned is ever indexed."""

import io
import re
import socket
import struct
import zipfile
from dataclasses import dataclass
from urllib.parse import urlparse

from ...core.config import get_settings

MAX_BYTES = 5 * 1024 * 1024
MAX_CHARS = 500_000
MAX_PDF_PAGES = 300
MAX_DOCX_UNZIPPED = 40 * 1024 * 1024
CHUNK_CHARS = 900

# The EICAR anti-virus test file: harmless, and every scanner reports it, so it proves rejection works.
EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
EXECUTABLE_MAGIC = (b"MZ", b"\x7fELF", b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"#!")


class IngestError(Exception):
    """The file cannot be used. `code` is stable; `message` is safe to show."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ScannerUnavailableError(Exception):
    pass


@dataclass
class ScanResult:
    clean: bool
    engine: str
    detail: str


# ------------------------------------------------------------------------------------------------ scanning
def _clamd(data: bytes, url: str, timeout: float = 20.0) -> ScanResult:
    u = urlparse(url)
    if u.scheme != "tcp" or not u.hostname:
        raise ScannerUnavailableError("clamav_url must look like tcp://host:3310")
    try:
        with socket.create_connection((u.hostname, u.port or 3310), timeout=timeout) as sock:
            sock.sendall(b"zINSTREAM\0")
            for i in range(0, len(data), 64 * 1024):
                part = data[i : i + 64 * 1024]
                sock.sendall(struct.pack("!L", len(part)) + part)
            sock.sendall(struct.pack("!L", 0))
            reply = b""
            while not reply.endswith(b"\0"):
                got = sock.recv(4096)
                if not got:
                    break
                reply += got
    except OSError as e:
        raise ScannerUnavailableError(f"ClamAV unreachable ({type(e).__name__})") from None
    text = reply.rstrip(b"\0").decode(errors="replace")
    if text.endswith("OK"):
        return ScanResult(True, "clamav", "clean")
    if "FOUND" in text:
        return ScanResult(False, "clamav", text.split(":", 1)[-1].replace("FOUND", "").strip()[:120])
    raise ScannerUnavailableError(f"ClamAV error ({text[:80]})")


def _builtin(data: bytes) -> ScanResult:
    """Development and test only: rejects the EICAR test file and anything executable. Not a malware scanner."""
    if EICAR in data:
        return ScanResult(False, "builtin-dev", "EICAR test signature")
    if data.startswith(EXECUTABLE_MAGIC):
        return ScanResult(False, "builtin-dev", "executable content")
    return ScanResult(True, "builtin-dev", "clean (development scanner)")


def scan(data: bytes) -> ScanResult:
    s = get_settings()
    if s.clamav_url:
        return _clamd(data, s.clamav_url)
    if s.is_production_like:
        raise ScannerUnavailableError("Malware scanning is awaiting configuration (set XV_CLAMAV_URL)")
    return _builtin(data)


def scanner_status() -> str:
    s = get_settings()
    if s.clamav_url:
        return "clamav"
    return "awaiting_configuration" if s.is_production_like else "builtin-dev"


# ------------------------------------------------------------------------------------------------ extraction
def detect(data: bytes) -> str:
    """Type from content. Only plain text, Markdown, CSV, PDF and Word (.docx) are accepted."""
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
                if "word/document.xml" in names:
                    if sum(i.file_size for i in z.infolist()) > MAX_DOCX_UNZIPPED:
                        raise IngestError("too_large", "This Word file expands to more than 40 MB.")
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except zipfile.BadZipFile:
            pass
        raise IngestError("unsupported_type", "Only text, Markdown, CSV, PDF and Word (.docx) files can be added.")
    if b"\x00" in data[:8192]:
        raise IngestError("unsupported_type", "Only text, Markdown, CSV, PDF and Word (.docx) files can be added.")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise IngestError("unsupported_type", "Text files must be UTF-8.") from None
    return "text/plain"


def extract(data: bytes, mime: str) -> str:
    if mime == "application/pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                raise IngestError("encrypted", "Password-protected PDFs can't be read. Remove the password first.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise IngestError("too_large", f"PDFs can have at most {MAX_PDF_PAGES} pages.")
            text = "\n\n".join((p.extract_text() or "") for p in reader.pages)
        except PdfReadError:
            raise IngestError("unreadable", "This PDF couldn't be read.") from None
    elif mime.endswith("wordprocessingml.document"):
        import docx

        try:
            d = docx.Document(io.BytesIO(data))
        except Exception:  # noqa: BLE001 - any parse failure means the same thing to the user
            raise IngestError("unreadable", "This Word file couldn't be read.") from None
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text.strip() for c in row.cells))
        text = "\n\n".join(parts)
    else:
        text = data.decode("utf-8")
    text = normalise(text)
    if not text:
        raise IngestError("empty", "No readable text was found. Scanned images need text first (OCR).")
    if len(text) > MAX_CHARS:
        raise IngestError("too_large", f"Documents can hold at most {MAX_CHARS:,} characters of text.")
    return text


def normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_SENTENCE = re.compile(r"(?<=[.!?।])\s+")


def chunk(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Paragraph-aware chunks of about `size` characters. A paragraph longer than that is split at sentence
    ends; the last sentence of a split paragraph repeats at the start of the next chunk to keep context."""
    pieces: list[str] = []
    for para in (p.strip() for p in text.split("\n\n")):
        if not para:
            continue
        if len(para) <= size:
            pieces.append(para)
            continue
        cur = ""
        for sent in _SENTENCE.split(para):
            while len(sent) > size:  # one enormous "sentence": hard split
                pieces.append(sent[:size])
                sent = sent[size:]
            if cur and len(cur) + 1 + len(sent) > size:
                pieces.append(cur)
                tail = _SENTENCE.split(cur)[-1]
                cur = tail if len(tail) + 1 + len(sent) <= size else ""
            cur = f"{cur} {sent}".strip()
        if cur:
            pieces.append(cur)
    out: list[str] = []
    for p in pieces:
        if out and len(out[-1]) + 2 + len(p) <= size:
            out[-1] = f"{out[-1]}\n\n{p}"
        else:
            out.append(p)
    return out

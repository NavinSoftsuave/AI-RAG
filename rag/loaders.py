"""Load raw text out of documents (PDFs and plain text)."""

from pathlib import Path

from pypdf import PdfReader


def load_pdf(path: str | Path) -> str:
    """Extract all text from a PDF, one page after another."""
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages)


def load_txt(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8", errors="ignore")


def load_file(path: str | Path) -> str:
    """Dispatch on file extension. Returns the document's plain text."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return load_pdf(path)
    if suffix in {".txt", ".md"}:
        return load_txt(path)
    raise ValueError(f"Unsupported file type: {suffix}")

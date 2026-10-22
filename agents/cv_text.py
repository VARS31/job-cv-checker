"""Shared CV helpers used by several agents: read text from a CV PDF, and check quotes."""

import io
import re
import unicodedata

from pypdf import PdfReader
from pypdf.errors import PyPdfError

MIN_CV_CHARACTERS = 200  # less text than this means the PDF is probably a scanned image


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Plain-Python text extraction. Raises ValueError if no text can be read."""
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(page.extract_text() or "" for page in reader.pages)
    except PyPdfError as e:
        raise ValueError(f"The file could not be read as a PDF: {e}") from e
    if len(text.strip()) < MIN_CV_CHARACTERS:
        raise ValueError(
            "No text could be read from the PDF. It may be a scanned image; "
            "please send a PDF with selectable text."
        )
    return text


def _normalize(text: str) -> str:
    """Make text comparable: only words (keep + and # for C++, C#), lower case, single spaces."""
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^\w+#]+", " ", text).strip()


def quote_in_text(quote: str, text: str) -> bool:
    """True if the quote's words appear in the text in the same order.

    Ignores case, line breaks and punctuation, so 'Microsoft Azure (App Service)'
    matches the CV text 'Microsoft Azure (App Service, PostgreSQL)'.
    """
    quote = _normalize(quote)
    return bool(quote) and f" {quote} " in f" {_normalize(text)} "

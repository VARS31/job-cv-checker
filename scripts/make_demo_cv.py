"""Create the fictional demo CV as a PDF (samples/demo/cv_demo.pdf), without extra packages.

Run with:  python scripts/make_demo_cv.py
Everything in this CV is made up: the person, the companies, the school and the contact details.
Writes a simple text PDF by hand (Helvetica, A4), which pypdf can read like any other PDF.
"""

import textwrap
from pathlib import Path

OUT_FILE = Path(__file__).resolve().parent.parent / "samples" / "demo" / "cv_demo.pdf"

# "# " = heading (bold). Plain ASCII only, so the built-in PDF fonts can show every character.
CV = """\
# Jordan Example
Backend & AI Engineer  |  Hamburg, Germany  |  jordan.example@example.com
(Fictional demo CV. The person, companies and school do not exist.)

# Summary
Backend engineer with 5 years of professional experience building Python services and REST APIs. For the last two years I have built LLM features in production, including a retrieval-augmented (RAG) search assistant used by the internal support team.

# Experience
Backend Engineer, Harborline Systems GmbH, Hamburg  |  03/2022 - today
- Built and run REST APIs in Python with FastAPI and PostgreSQL for a shipment-tracking platform.
- Designed a RAG search assistant over 4,000 support articles with an open-source embedding model and pgvector; added an evaluation set of 150 real support questions to measure answer quality.
- Containerised all services with Docker and deployed them to Microsoft Azure (App Service, Azure Database for PostgreSQL) with GitHub Actions CI/CD.
- Wrote automated tests with pytest; raised test coverage of the core API from 40% to 85%.
- Mentored two junior developers and ran the team's weekly code reviews.

Junior Software Developer, Quillbyte Software GmbH, Bremen  |  09/2019 - 02/2022
- Developed Django web applications and internal REST APIs for small retail customers.
- Maintained PostgreSQL databases and wrote data migration scripts in Python.
- Took part in customer workshops to turn feature requests into user stories.

# Education
B.Sc. Computer Science, Example University of Applied Sciences, Bremen  |  2015 - 2019
Thesis: Comparing caching strategies for read-heavy REST APIs.

# Skills
Languages: Python, SQL, basic TypeScript
Frameworks: FastAPI, Django, pytest
Data: PostgreSQL, pgvector, Redis
Cloud & DevOps: Docker, Microsoft Azure, GitHub Actions, Git
AI: LLM APIs, retrieval-augmented generation (RAG), embeddings, prompt design, answer evaluation

# Languages
English: fluent (C1)
German: basic (A2)
"""

PAGE_WIDTH, PAGE_HEIGHT = 595, 842  # A4 in points
MARGIN, FONT_SIZE, LINE_HEIGHT, WRAP = 56, 10, 14, 92


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def layout(cv: str) -> list[list[tuple[str, str]]]:
    """Wrap the text into pages of (font, line) pairs. F1 = regular, F2 = bold."""
    lines = []
    for raw in cv.splitlines():
        if raw.startswith("# "):
            lines += [("F1", ""), ("F2", raw[2:])]
        elif not raw.strip():
            continue
        else:
            indent = "   " if raw.startswith("- ") else ""
            lines += [("F1", w) for w in textwrap.wrap(raw, WRAP, subsequent_indent=indent)]
    per_page = (PAGE_HEIGHT - 2 * MARGIN) // LINE_HEIGHT
    return [lines[i:i + per_page] for i in range(0, len(lines), per_page)]


def build_pdf(pages: list[list[tuple[str, str]]]) -> bytes:
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        None,  # page tree, filled in below
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    page_ids = []
    for page in pages:
        commands = ["BT", f"{LINE_HEIGHT} TL", f"{MARGIN} {PAGE_HEIGHT - MARGIN} Td"]
        for font, line in page:
            size = FONT_SIZE + (2 if font == "F2" else 0)
            commands.append(f"/{font} {size} Tf ({_escape(line)}) Tj T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("cp1252")
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_id = len(objects)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        page_ids.append(len(objects))
    kids = " ".join(f"{i} 0 R" for i in page_ids)
    objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode()

    pdf, offsets = b"%PDF-1.4\n", []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(pdf)
    pdf += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    pdf += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    pdf += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref)
    return pdf


if __name__ == "__main__":
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_bytes(build_pdf(layout(CV)))
    print(f"Wrote {OUT_FILE}")

"""Create the fictional demo CVs as PDFs in samples/demo/, without extra packages.

Run with:  python scripts/make_demo_cv.py
Everything in these CVs is made up: the people, the companies, the schools and the contact details.
Writes simple text PDFs by hand (Helvetica, A4), which pypdf can read like any other PDF.

The CVs, all for the fictional demo ad samples/demo/job_ad_demo.txt:
- cv_demo.pdf             Jordan Example: the original demo CV
- cv_jane_doe.pdf         Jane Doe: a strong fit
- cv_robin_sample.pdf     Robin Sample: a medium fit
- cv_casey_placeholder.pdf  Casey Placeholder: a weak fit
"""

import textwrap
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "samples" / "demo"

# "# " = heading (bold). Plain ASCII only, so the built-in PDF fonts can show every character.
JORDAN_EXAMPLE = """\
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

JANE_DOE = """\
# Jane Doe
Senior Backend Engineer (Python & LLMs)  |  Hamburg, Germany  |  jane.doe@example.com
(Fictional demo CV. The person, companies and university do not exist.)

# Summary
Backend engineer with 7 years of professional experience in Python. For the last three years I have built LLM features in production, including a customer-facing retrieval-augmented (RAG) assistant that answers questions from product documentation.

# Experience
Senior Backend Engineer, Cargoline Digital GmbH, Hamburg  |  01/2022 - today
- Designed and built REST APIs in Python with FastAPI and PostgreSQL for a freight booking platform used by 300 business customers.
- Built a customer-facing RAG assistant over 6,000 help articles with pgvector and an LLM API; it now answers 40% of customer questions without a support agent.
- Created an evaluation set of 300 real customer questions and a weekly report on answer quality.
- Containerised all services with Docker and run them on Kubernetes on AWS (EKS), deployed with GitLab CI/CD.
- Mentored three engineers and led the team's API design reviews.

Backend Developer, Brightquay Software GmbH, Bremen  |  09/2019 - 12/2021
- Developed Django REST APIs and PostgreSQL databases for logistics customers.
- Wrote SQL reports and data migrations; introduced automated tests with pytest.
- Took part in customer workshops to turn requirements into API designs.

# Education
M.Sc. Computer Science, Example Technical University, Hamburg  |  2017 - 2019
B.Sc. Computer Science, Example Technical University, Hamburg  |  2014 - 2017

# Skills
Languages: Python, SQL, TypeScript
Frameworks: FastAPI, Django, pytest
Data: PostgreSQL, pgvector, Redis
Cloud & DevOps: Docker, Kubernetes, AWS, GitLab CI/CD
AI: LLM APIs, retrieval-augmented generation (RAG), embeddings, evaluation of LLM answers

# Languages
English: fluent (C2)
German: fluent (C1)

# Volunteering
Maintains the website of a local rowing club.
"""

ROBIN_SAMPLE = """\
# Robin Sample
Software Developer  |  Hamburg, Germany  |  robin.sample@example.com
(Fictional demo CV. The person, companies and university do not exist.)

# Summary
Software developer with 3 years of professional experience building backend services in Java, plus Python for data scripts. I want to move into AI engineering and built a small chatbot prototype with an LLM API at a hackathon.

# Experience
Software Developer, Havenlight Insurance IT GmbH, Hamburg  |  09/2023 - today
- Develop REST APIs in Java with Spring Boot and a PostgreSQL database for an internal claims system.
- Write Python scripts that clean and import data from partner files.
- Package services with Docker; changes are built and tested with GitHub Actions and deployed to an on-premises server.

# Projects
Hackathon 2025: a chatbot prototype that answers questions about insurance terms, using an LLM API (no retrieval, no evaluation).

# Education
B.Sc. Business Informatics, Example University of Applied Sciences, Hamburg  |  2019 - 2023

# Skills
Languages: Java, Python, SQL
Frameworks: Spring Boot, Flask
Data: PostgreSQL
Tools: Docker, GitHub Actions, Git

# Languages
English: very good (C1)
German: native
"""

CASEY_PLACEHOLDER = """\
# Casey Placeholder
Frontend Developer  |  Munich, Germany  |  casey.placeholder@example.com
(Fictional demo CV. The person, companies and university do not exist.)

# Summary
Frontend developer with 2 years of experience building online shops in React and TypeScript.

# Experience
Frontend Developer, Pinecrest Commerce GmbH, Munich  |  01/2024 - today
- Build product pages and checkout flows in React and TypeScript for online shops.
- Work with designers on accessible, responsive layouts in Figma and CSS.
- Write unit tests with Jest.

Intern, Brightfield Media Agency, Munich  |  07/2023 - 12/2023
- Built landing pages with HTML, CSS and JavaScript.

# Education
B.A. Media Design, Example University of Applied Sciences, Munich  |  2020 - 2023

# Skills
Languages: TypeScript, JavaScript, HTML, CSS
Frameworks: React, Next.js, Jest
Tools: Git, Figma

# Languages
English: good (B2)
German: native
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


CVS = {
    "cv_demo.pdf": JORDAN_EXAMPLE,
    "cv_jane_doe.pdf": JANE_DOE,
    "cv_robin_sample.pdf": ROBIN_SAMPLE,
    "cv_casey_placeholder.pdf": CASEY_PLACEHOLDER,
}

if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for filename, cv in CVS.items():
        (OUT_DIR / filename).write_bytes(build_pdf(layout(cv)))
        print(f"Wrote {OUT_DIR / filename}")

"""Protocol document text extraction from .docx files.

Extracts both paragraphs and table content, preserving structural
markers (headings, table boundaries) so the LLM can understand
document organization.

Addresses PITFALL-05: python-docx ``doc.paragraphs`` alone misses
table content because tables are separate block-level elements.
"""

from pathlib import Path

from docx import Document
from docx.table import Table


def _table_to_text(table: Table) -> str:
    """Convert a python-docx Table to pipe-delimited text rows.

    Args:
        table: A python-docx Table object.

    Returns:
        Multi-line string with each row pipe-delimited.
    """
    rows: list[str] = []
    for row in table.rows:
        cells = [cell.text.strip() for cell in row.cells]
        rows.append("| " + " | ".join(cells))
    return "\n".join(rows)


def extract_protocol_text(docx_path: Path) -> str:
    """Extract all text from a .docx protocol document.

    Iterates document body elements in order, handling both
    paragraphs and tables.  Headings are marked with ``##`` prefix.
    Table rows are pipe-delimited.  This addresses PITFALL-05:
    python-docx paragraphs alone miss table content.

    Args:
        docx_path: Path to the .docx file.

    Returns:
        Full document text with structural markers.

    Raises:
        FileNotFoundError: If docx_path does not exist.
        ValueError: If file is not a valid .docx.
    """
    docx_path = Path(docx_path)
    if not docx_path.exists():
        msg = f"Protocol document not found: {docx_path}"
        raise FileNotFoundError(msg)

    try:
        doc = Document(str(docx_path))
    except Exception as exc:
        msg = f"Could not open as .docx: {docx_path}"
        raise ValueError(msg) from exc

    parts: list[str] = []

    # Iterate body children in document order to interleave paragraphs
    # and tables correctly.
    for element in doc.element.body:
        tag = element.tag

        if tag.endswith("}p"):
            # Paragraph element
            from docx.text.paragraph import Paragraph

            para = Paragraph(element, doc)
            text = para.text.strip()
            if not text:
                continue
            # Prefix headings with ## for LLM structural understanding
            style_name = (para.style.name or "") if para.style else ""
            if "Heading" in style_name:
                parts.append(f"## {text}")
            else:
                parts.append(text)

        elif tag.endswith("}tbl"):
            # Table element
            table = Table(element, doc)
            table_text = _table_to_text(table)
            if table_text.strip():
                parts.append(table_text)

    return "\n".join(parts)

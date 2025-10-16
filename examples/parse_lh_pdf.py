"""Example script for parsing LH PDF announcements."""
from __future__ import annotations

import logging
from pathlib import Path

from src.parsers import LHPDFParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

LOGGER = logging.getLogger(__name__)


def parse_lh_announcement(pdf_path: Path) -> None:
    """
    Parse an LH announcement PDF and display the structure.

    Args:
        pdf_path: Path to LH PDF file
    """
    LOGGER.info(f"Parsing LH PDF: {pdf_path}")

    # Create parser
    parser = LHPDFParser()

    # Validate PDF
    if not parser.validate_pdf(pdf_path):
        LOGGER.error(f"Invalid PDF file: {pdf_path}")
        return

    # Parse document
    try:
        document = parser.parse(pdf_path)
        LOGGER.info("Successfully parsed document")
    except Exception as e:
        LOGGER.error(f"Failed to parse PDF: {e}")
        raise

    # Display structure
    print("\n" + "=" * 80)
    print(f"Document: {pdf_path.name}")
    print("=" * 80)
    print(f"\nTotal sections: {document.metadata['total_sections']}")
    print(f"Total tables: {document.metadata['total_tables']}")
    print("\n" + "-" * 80)
    print("Document Structure:")
    print("-" * 80 + "\n")

    # Display hierarchical structure
    for section in document.sections:
        print_section(section, indent=0)


def print_section(section, indent: int = 0) -> None:
    """
    Recursively print section structure.

    Args:
        section: Section to print
        indent: Indentation level
    """
    prefix = "  " * indent
    print(f"{prefix}[Level {section.level}] {section.title}")

    # Print content summary
    if section.content:
        content_preview = " ".join(section.content)[:100]
        if len(content_preview) == 100:
            content_preview += "..."
        print(f"{prefix}  Content: {content_preview}")

    # Print tables
    if section.tables:
        for i, table in enumerate(section.tables):
            rows, cols = table.dataframe.shape
            print(
                f"{prefix}  Table {i + 1}: {rows} rows × {cols} columns "
                f"(page {table.bbox.page if table.bbox else 'unknown'})"
            )

    # Print children
    for child in section.children:
        print_section(child, indent + 1)


def main() -> None:
    """Main entry point."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python examples/parse_lh_pdf.py <path_to_pdf>")
        print("\nExample:")
        print("  python examples/parse_lh_pdf.py data/pdfs/example.pdf")
        sys.exit(1)

    pdf_path = Path(sys.argv[1])

    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        sys.exit(1)

    parse_lh_announcement(pdf_path)


if __name__ == "__main__":
    main()

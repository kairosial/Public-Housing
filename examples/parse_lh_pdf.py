"""Example script for parsing LH PDF announcements."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.parsers import LHPDFParser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

LOGGER = logging.getLogger(__name__)

# Output directory
OUTPUT_DIR = Path("output/parsed_pdfs")


def parse_lh_announcement(pdf_path: Path, save_output: bool = True) -> None:
    """
    Parse an LH announcement PDF and display/save the structure.

    Args:
        pdf_path: Path to LH PDF file
        save_output: Whether to save output to files (default: True)
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

    # Save output files
    if save_output:
        save_results(document, pdf_path)


def save_results(document, pdf_path: Path) -> None:
    """
    Save parsing results to files.

    Args:
        document: Parsed document
        pdf_path: Original PDF path
    """
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Create subdirectory for this PDF
    parent_dir_name = pdf_path.parent.name
    timestamp = datetime.now().strftime("%y%m%d_%H%M")
    output_subdir = OUTPUT_DIR / f"{timestamp}-{parent_dir_name}"
    output_subdir.mkdir(parents=True, exist_ok=True)

    # 1. Save JSON (full structure)
    json_path = output_subdir / "document.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(document.to_dict(), f, ensure_ascii=False, indent=2)
    print(f"\n✓ Saved JSON: {json_path}")

    # 2. Save all tables as CSV
    tables_dir = output_subdir / "tables"
    tables_dir.mkdir(exist_ok=True)

    table_count = 0
    for section in document.sections:
        table_count = save_section_tables(section, tables_dir, table_count)

    if table_count > 0:
        print(f"✓ Saved {table_count} tables to: {tables_dir}")

    # 3. Save text summary
    summary_path = output_subdir / "summary.txt"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write(f"Document: {pdf_path.name}\n")
        f.write("=" * 80 + "\n\n")
        f.write(f"Source: {document.source_path}\n")
        f.write(f"Total sections: {document.metadata['total_sections']}\n")
        f.write(f"Total tables: {document.metadata['total_tables']}\n")
        f.write("\n" + "-" * 80 + "\n")
        f.write("Document Structure:\n")
        f.write("-" * 80 + "\n\n")

        for section in document.sections:
            write_section_summary(f, section, indent=0)

    print(f"✓ Saved summary: {summary_path}")

    print(f"\n{'=' * 80}")
    print(f"All outputs saved to: {output_subdir}")
    print(f"{'=' * 80}\n")


def save_section_tables(section, tables_dir: Path, table_count: int) -> int:
    """
    Recursively save all tables in a section.

    Args:
        section: Section to process
        tables_dir: Directory to save tables
        table_count: Current table count

    Returns:
        Updated table count
    """
    for table in section.tables:
        table_count += 1
        csv_path = tables_dir / f"table_{table_count:03d}_page_{table.page}.csv"
        table.dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")

    for child in section.children:
        table_count = save_section_tables(child, tables_dir, table_count)

    return table_count


def write_section_summary(f, section, indent: int = 0) -> None:
    """
    Recursively write section summary to file.

    Args:
        f: File handle
        section: Section to write
        indent: Indentation level
    """
    prefix = "  " * indent
    f.write(f"{prefix}[Level {section.level}] {section.title}\n")

    if section.content:
        content_preview = " ".join(section.content)[:100]
        if len(content_preview) == 100:
            content_preview += "..."
        f.write(f"{prefix}  Content: {content_preview}\n")

    if section.tables:
        for i, table in enumerate(section.tables):
            rows, cols = table.dataframe.shape
            f.write(
                f"{prefix}  Table {i + 1}: {rows} rows × {cols} columns "
                f"(page {table.page})\n"
            )

    for child in section.children:
        write_section_summary(f, child, indent + 1)


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

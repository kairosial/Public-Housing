"""Example script for parsing LH PDF announcements."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

from src.parsers import LHPDFParser
from src.parsers.hierarchy_parser import HierarchyParser
from src.parsers.layout_analyzer import LayoutAnalyzer
from src.parsers.table_extractor import TableExtractor

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


def debug_parse_lh_announcement(
    pdf_path: Path, save_output: bool = True, interactive: bool = True
) -> None:
    """
    Parse LH announcement in debug mode with step-by-step execution.

    Args:
        pdf_path: Path to LH PDF file
        save_output: Whether to save output to files (default: True)
        interactive: Whether to pause between steps (default: True)
    """
    print("\n" + "=" * 80)
    print("DEBUG MODE: Step-by-Step PDF Parsing")
    print("=" * 80)
    print(f"\nPDF: {pdf_path}")
    print(f"File size: {pdf_path.stat().st_size / 1024:.1f} KB\n")

    # Enable DEBUG logging for parsers
    logging.getLogger("src.parsers").setLevel(logging.DEBUG)

    # Create output directory for debug files
    timestamp = datetime.now().strftime("%y%m%d_%H%M%S")
    parent_dir_name = pdf_path.parent.name
    debug_dir = OUTPUT_DIR / "debug" / f"{timestamp}-{parent_dir_name}"
    debug_dir.mkdir(parents=True, exist_ok=True)

    print(f"Debug output directory: {debug_dir}\n")

    # =========================================================================
    # STEP 1: Layout Analysis
    # =========================================================================
    print("=" * 80)
    print("STEP 1: Layout Analysis (PyMuPDF)")
    print("=" * 80)

    layout_analyzer = LayoutAnalyzer()
    layout_info = layout_analyzer.analyze(pdf_path)

    # Statistics
    total_text_blocks = sum(len(page["text_blocks"]) for page in layout_info.values())
    total_table_regions = sum(
        len(page["table_regions"]) for page in layout_info.values()
    )

    print(f"\nResults:")
    print(f"  Pages analyzed: {len(layout_info)}")
    print(f"  Total text blocks: {total_text_blocks}")
    print(f"  Detected table regions: {total_table_regions}")

    # Per-page breakdown
    print(f"\n  Per-page breakdown:")
    for page_num, page_data in sorted(layout_info.items()):
        print(
            f"    Page {page_num}: {len(page_data['text_blocks'])} blocks, "
            f"{len(page_data['table_regions'])} table regions"
        )

    # Save layout info
    if save_output:
        layout_file = debug_dir / "01_layout_info.json"
        layout_json = {}
        for page_num, page_data in layout_info.items():
            layout_json[str(page_num)] = {
                "page_num": page_data["page_num"],
                "page_size": page_data["page_size"],
                "text_blocks": [
                    {
                        "text": block.text,
                        "bbox": [block.bbox.x0, block.bbox.y0, block.bbox.x1, block.bbox.y1],
                        "font_size": block.font_size,
                        "font_name": block.font_name,
                        "is_bold": block.is_bold,
                        "is_italic": block.is_italic,
                    }
                    for block in page_data["text_blocks"]
                ],
                "table_regions": [
                    {
                        "bbox": [r.x0, r.y0, r.x1, r.y1],
                        "page": r.page,
                    }
                    for r in page_data["table_regions"]
                ],
            }
        with open(layout_file, "w", encoding="utf-8") as f:
            json.dump(layout_json, f, ensure_ascii=False, indent=2)
        print(f"\n  Saved: {layout_file}")

    if interactive:
        input("\nPress Enter to continue to Step 2...")
    else:
        print("\n→ Moving to Step 2...")

    # =========================================================================
    # STEP 2: Table Extraction
    # =========================================================================
    print("\n" + "=" * 80)
    print("STEP 2: Table Extraction (Camelot)")
    print("=" * 80)

    table_extractor = TableExtractor()

    # Extract with both flavors
    print("\n  Extracting with lattice mode...")
    lattice_tables = table_extractor.extract_tables(pdf_path, flavor="lattice")

    print(f"  Extracting with stream mode...")
    stream_tables = table_extractor.extract_tables(pdf_path, flavor="stream")

    all_tables = table_extractor.extract_tables(pdf_path, flavor="both")

    print(f"\nResults:")
    print(f"  Lattice tables: {len(lattice_tables)}")
    print(f"  Stream tables: {len(stream_tables)}")
    print(f"  Total after deduplication: {len(all_tables)}")

    # Table quality breakdown
    if all_tables:
        print(f"\n  Table quality metrics:")
        for i, table in enumerate(all_tables, 1):
            print(
                f"    Table {i} (page {table.page}): "
                f"accuracy={table.metadata.get('accuracy', 0):.1f}%, "
                f"quality={table.metadata.get('quality_score', 0):.2f}, "
                f"shape={table.dataframe.shape}, "
                f"flavor={table.metadata.get('flavor', 'unknown')}"
            )

    # Save tables
    if save_output and all_tables:
        tables_file = debug_dir / "02_tables.json"
        tables_json = []
        for i, table in enumerate(all_tables):
            tables_json.append({
                "index": i,
                "page": table.page,
                "bbox": [table.bbox.x0, table.bbox.y0, table.bbox.x1, table.bbox.y1]
                if table.bbox
                else None,
                "shape": list(table.dataframe.shape),
                "metadata": table.metadata,
                "caption": table.caption,
                "dataframe": table.dataframe.to_dict(orient="records"),
            })
        with open(tables_file, "w", encoding="utf-8") as f:
            json.dump(tables_json, f, ensure_ascii=False, indent=2)
        print(f"\n  Saved: {tables_file}")

        # Also save as CSV
        tables_csv_dir = debug_dir / "tables_csv"
        tables_csv_dir.mkdir(exist_ok=True)
        for i, table in enumerate(all_tables, 1):
            csv_file = tables_csv_dir / f"table_{i:03d}_page_{table.page}.csv"
            table.dataframe.to_csv(csv_file, index=False, encoding="utf-8-sig")

    if interactive:
        input("\nPress Enter to continue to Step 3...")
    else:
        print("\n→ Moving to Step 3...")

    # =========================================================================
    # STEP 3: Hierarchical Text Parsing
    # =========================================================================
    print("\n" + "=" * 80)
    print("STEP 3: Hierarchical Text Parsing (pdfplumber)")
    print("=" * 80)

    hierarchy_parser = HierarchyParser()

    # Get table bboxes for exclusion
    table_bboxes = [table.bbox for table in all_tables if table.bbox]
    print(f"\n  Excluding {len(table_bboxes)} table regions from text extraction")

    sections = hierarchy_parser.parse(pdf_path, exclude_regions=table_bboxes)

    print(f"\nResults:")
    print(f"  Top-level sections: {len(sections)}")

    # Count all sections recursively
    def count_sections(section_list):
        count = len(section_list)
        for section in section_list:
            count += count_sections(section.children)
        return count

    total_sections = count_sections(sections)
    print(f"  Total sections (all levels): {total_sections}")

    # Level distribution
    level_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}

    def count_levels(section_list):
        for section in section_list:
            level_counts[section.level] += 1
            count_levels(section.children)

    count_levels(sections)

    print(f"\n  Section level distribution:")
    for level in range(5):
        print(f"    Level {level}: {level_counts[level]} sections")

    print(f"\n  Hierarchical structure preview:")
    for section in sections[:3]:  # Show first 3 top-level sections
        print_section(section, indent=1)
        if len(sections) > 3:
            print("  ...")

    # Save sections
    if save_output:
        sections_file = debug_dir / "03_sections.json"

        def section_to_dict(section):
            return {
                "level": section.level,
                "title": section.title,
                "bbox": [
                    section.bbox.x0,
                    section.bbox.y0,
                    section.bbox.x1,
                    section.bbox.y1,
                    section.bbox.page,
                ]
                if section.bbox
                else None,
                "content": section.content,
                "table_count": len(section.tables),
                "children": [section_to_dict(child) for child in section.children],
            }

        sections_json = [section_to_dict(s) for s in sections]
        with open(sections_file, "w", encoding="utf-8") as f:
            json.dump(sections_json, f, ensure_ascii=False, indent=2)
        print(f"\n  Saved: {sections_file}")

    if interactive:
        input("\nPress Enter to continue to Step 4...")
    else:
        print("\n→ Moving to Step 4...")

    # =========================================================================
    # STEP 4: Merge Tables into Sections
    # =========================================================================
    print("\n" + "=" * 80)
    print("STEP 4: Merge Tables into Sections")
    print("=" * 80)

    # Use LHPDFParser's private method
    parser = LHPDFParser()
    parser._merge_tables_into_sections(sections, all_tables)

    # Count assigned tables
    def count_tables(section_list):
        count = 0
        for section in section_list:
            count += len(section.tables)
            count += count_tables(section.children)
        return count

    assigned_tables = count_tables(sections)

    print(f"\nResults:")
    print(f"  Tables assigned to sections: {assigned_tables} / {len(all_tables)}")

    if assigned_tables < len(all_tables):
        print(
            f"  WARNING: {len(all_tables) - assigned_tables} tables "
            "were not assigned to any section!"
        )

    # Show which sections got tables
    print(f"\n  Sections with tables:")

    def print_sections_with_tables(section_list, indent=1):
        for section in section_list:
            if section.tables:
                prefix = "  " * indent
                print(
                    f"{prefix}[L{section.level}] {section.title}: "
                    f"{len(section.tables)} table(s)"
                )
            print_sections_with_tables(section.children, indent + 1)

    print_sections_with_tables(sections)

    # Save merged result
    if save_output:
        merged_file = debug_dir / "04_sections_with_tables.json"

        def section_to_dict_full(section):
            return {
                "level": section.level,
                "title": section.title,
                "bbox": [
                    section.bbox.x0,
                    section.bbox.y0,
                    section.bbox.x1,
                    section.bbox.y1,
                    section.bbox.page,
                ]
                if section.bbox
                else None,
                "content": section.content,
                "tables": [
                    {
                        "page": t.page,
                        "shape": list(t.dataframe.shape),
                        "accuracy": t.metadata.get("accuracy"),
                        "quality_score": t.metadata.get("quality_score"),
                    }
                    for t in section.tables
                ],
                "children": [section_to_dict_full(child) for child in section.children],
            }

        merged_json = [section_to_dict_full(s) for s in sections]
        with open(merged_file, "w", encoding="utf-8") as f:
            json.dump(merged_json, f, ensure_ascii=False, indent=2)
        print(f"\n  Saved: {merged_file}")

    print("\n" + "=" * 80)
    print("DEBUG PARSING COMPLETE")
    print("=" * 80)
    print(f"\nAll debug files saved to: {debug_dir}")
    print(
        "\nNext steps:\n"
        "  1. Review layout_info.json to check table region detection\n"
        "  2. Review tables.json to check extraction quality\n"
        "  3. Review sections.json to check hierarchy parsing\n"
        "  4. Review sections_with_tables.json to check table assignment\n"
    )


def main() -> None:
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Parse LH announcement PDFs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python examples/parse_lh_pdf.py data/pdfs/example.pdf
  python examples/parse_lh_pdf.py data/pdfs/example.pdf --debug
  python examples/parse_lh_pdf.py data/pdfs/example.pdf --no-save
        """,
    )
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode with step-by-step execution",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Don't save output files",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="Run without pausing between steps (for automated testing)",
    )

    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: File not found: {args.pdf_path}")
        import sys

        sys.exit(1)

    if args.debug:
        debug_parse_lh_announcement(
            args.pdf_path,
            save_output=not args.no_save,
            interactive=not args.non_interactive,
        )
    else:
        parse_lh_announcement(args.pdf_path, save_output=not args.no_save)


if __name__ == "__main__":
    main()

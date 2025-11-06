"""LH-specific PDF parser integrating layout, table, and hierarchy analysis."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from src.models.document_structure import BoundingBox, Document, Section, TableData
from src.parsers.hierarchy_parser import HierarchyParser
from src.parsers.layout_analyzer import LayoutAnalyzer
from src.parsers.pdf_parser import PDFParser
from src.parsers.table_extractor import TableExtractor

LOGGER = logging.getLogger(__name__)


class LHPDFParser(PDFParser):
    """
    Integrated PDF parser for LH public housing announcements.

    This parser combines three parsing strategies:
    1. Layout analysis (PyMuPDF) - Fast detection of table regions
    2. Table extraction (Camelot) - Precise table extraction with structure
    3. Hierarchy parsing (pdfplumber) - Text structure with Korean heading detection
    """

    def __init__(self) -> None:
        """Initialize LH PDF parser with all sub-parsers."""
        self.layout_analyzer = LayoutAnalyzer()
        self.table_extractor = TableExtractor()
        self.hierarchy_parser = HierarchyParser()

    def parse(self, pdf_path: Path) -> Document:
        """
        Parse LH PDF document with hierarchical structure.

        Workflow:
        1. Analyze layout to detect potential table regions
        2. Extract tables using Camelot (both lattice and stream modes)
        3. Parse hierarchical text structure, excluding table regions
        4. Merge tables into their corresponding sections
        5. Post-process cross-page tables

        Args:
            pdf_path: Path to LH PDF file

        Returns:
            Structured Document with sections, content, and tables
        """
        LOGGER.info(f"Starting to parse LH PDF: {pdf_path}")

        # Step 1: Layout analysis - detect table regions
        LOGGER.info("Step 1: Analyzing layout and detecting table regions")
        layout_info = self.layout_analyzer.analyze(pdf_path)

        # Collect all table regions across pages
        all_table_regions: List[BoundingBox] = []
        for page_layout in layout_info.values():
            all_table_regions.extend(page_layout["table_regions"])

        LOGGER.info(f"Detected {len(all_table_regions)} potential table regions")

        # Step 2: Extract tables with both lattice and stream modes
        LOGGER.info("Step 2: Extracting tables using Camelot")
        tables = self.table_extractor.extract_tables(
            pdf_path=pdf_path,
            flavor="both"  # Use both lattice and stream modes
        )

        LOGGER.info(f"Extracted {len(tables)} tables")

        # Step 3: Parse hierarchical structure, excluding table regions
        LOGGER.info("Step 3: Parsing hierarchical text structure")

        # Get table bounding boxes for exclusion
        table_bboxes = [table.bbox for table in tables if table.bbox]

        sections = self.hierarchy_parser.parse(
            pdf_path=pdf_path,
            exclude_regions=table_bboxes
        )

        LOGGER.info(f"Parsed {len(sections)} top-level sections")

        # Step 4: Merge tables into corresponding sections
        LOGGER.info("Step 4: Merging tables into sections")
        self._merge_tables_into_sections(sections, tables)

        # Step 5: Post-process for cross-page tables
        LOGGER.info("Step 5: Processing cross-page tables")
        merged_tables = self._merge_cross_page_tables(tables)

        # Update sections with merged tables
        self._merge_tables_into_sections(sections, merged_tables)

        # Create final document
        document = Document(
            source_path=pdf_path,
            sections=sections,
            metadata={
                "total_sections": self._count_all_sections(sections),
                "total_tables": len(merged_tables),
            }
        )

        LOGGER.info(f"Successfully parsed document with {len(sections)} sections")
        return document

    def validate_pdf(self, pdf_path: Path) -> bool:
        """
        Validate if the file is a readable PDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            True if valid, False otherwise
        """
        if not pdf_path.exists():
            LOGGER.error(f"PDF file not found: {pdf_path}")
            return False

        if not pdf_path.suffix.lower() == ".pdf":
            LOGGER.error(f"File is not a PDF: {pdf_path}")
            return False

        try:
            # Try to open with layout analyzer
            layout_info = self.layout_analyzer.analyze(pdf_path)
            return len(layout_info) > 0
        except Exception as e:
            LOGGER.error(f"Failed to validate PDF: {e}")
            return False

    def _merge_tables_into_sections(
        self, sections: List[Section], tables: List[TableData]
    ) -> None:
        """
        Merge extracted tables into their corresponding sections.

        Tables are assigned to sections based on spatial proximity
        (bounding box overlap or containment).

        Args:
            sections: List of sections (will be modified in-place)
            tables: List of extracted tables
        """
        for table in tables:
            if not table.bbox:
                continue

            # Find the best matching section for this table
            best_section = self._find_best_section_for_table(sections, table)

            if best_section:
                best_section.tables.append(table)
                LOGGER.debug(
                    f"Assigned table to section '{best_section.title}' "
                    f"(page {table.bbox.page})"
                )

    def _find_best_section_for_table(
        self, sections: List[Section], table: TableData
    ) -> Optional[Section]:
        """
        Find the best matching section for a table.

        Strategy:
        1. Check if table bbox overlaps with section bbox
        2. Prefer sections on the same page
        3. Prefer sections with higher hierarchy level (more specific)
        4. If no overlap, assign to nearest section above the table

        Args:
            sections: List of sections to search
            table: Table to assign

        Returns:
            Best matching Section or None
        """
        if not table.bbox:
            return None

        best_section: Optional[Section] = None
        best_score = -1

        def score_section(section: Section, depth: int = 0) -> None:
            nonlocal best_section, best_score

            if not section.bbox:
                # Recursively check children
                for child in section.children:
                    score_section(child, depth + 1)
                return

            # Calculate matching score
            score = 0

            # Same page bonus
            if section.bbox.page == table.bbox.page:
                score += 100

            # Overlap bonus
            if section.bbox.overlaps(table.bbox):
                score += 50

            # Proximity bonus (vertical distance)
            if section.bbox.page == table.bbox.page:
                # Table below section heading
                if table.bbox.y0 >= section.bbox.y1:
                    vertical_distance = table.bbox.y0 - section.bbox.y1
                    # Closer is better (max 50 points)
                    proximity_score = max(0, 50 - vertical_distance / 10)
                    score += proximity_score

            # Depth bonus (prefer more specific sections)
            score += depth * 10

            if score > best_score:
                best_score = score
                best_section = section

            # Check children
            for child in section.children:
                score_section(child, depth + 1)

        # Score all sections
        for section in sections:
            score_section(section)

        return best_section

    def _merge_cross_page_tables(
        self, tables: List[TableData]
    ) -> List[TableData]:
        """
        Merge tables that span across multiple pages.

        Detection strategy:
        1. Tables on consecutive pages
        2. Same number of columns
        3. Similar column widths
        4. Vertical alignment (same x-coordinates)

        Args:
            tables: List of extracted tables

        Returns:
            List of tables with cross-page tables merged
        """
        if len(tables) <= 1:
            return tables

        merged: List[TableData] = []
        skip_indices = set()

        for i, table in enumerate(tables):
            if i in skip_indices:
                continue

            # Try to find continuation tables
            current_table = table
            j = i + 1

            while j < len(tables):
                next_table = tables[j]

                if self._can_merge_tables(current_table, next_table):
                    # Merge next_table into current_table
                    current_table = self._merge_two_tables(
                        current_table, next_table
                    )
                    skip_indices.add(j)
                    LOGGER.info(
                        f"Merged table from page {table.bbox.page} "
                        f"with page {next_table.bbox.page}"
                    )
                    j += 1
                else:
                    break

            merged.append(current_table)

        LOGGER.info(
            f"Merged {len(tables) - len(merged)} cross-page tables"
        )
        return merged

    def _can_merge_tables(
        self, table1: TableData, table2: TableData
    ) -> bool:
        """
        Check if two tables can be merged.

        Args:
            table1: First table
            table2: Second table (should be on next page)

        Returns:
            True if tables can be merged
        """
        if not table1.bbox or not table2.bbox:
            return False

        # Must be on consecutive pages
        if table2.bbox.page != table1.bbox.page + 1:
            return False

        # Must have same number of columns
        if len(table1.dataframe.columns) != len(table2.dataframe.columns):
            return False

        # Check horizontal alignment (x-coordinates should be similar)
        x_diff = abs(table1.bbox.x0 - table2.bbox.x0)
        if x_diff > 10:  # 10 pixel tolerance
            return False

        # Check if table2 is at top of page (continuation table indicator)
        if table2.bbox.y0 > 100:  # Should start near top of page
            return False

        return True

    def _merge_two_tables(
        self, table1: TableData, table2: TableData
    ) -> TableData:
        """
        Merge two tables into one.

        Args:
            table1: First table
            table2: Second table

        Returns:
            Merged table
        """
        import pandas as pd

        # Reset both row and column indices to avoid conflicts
        df1 = table1.dataframe.copy()
        df2 = table2.dataframe.copy()

        # Reset row index
        df1 = df1.reset_index(drop=True)
        df2 = df2.reset_index(drop=True)

        # Ensure column names are unique by resetting them if needed
        if df1.columns.duplicated().any():
            df1.columns = range(len(df1.columns))
        if df2.columns.duplicated().any():
            df2.columns = range(len(df2.columns))

        # Concatenate dataframes
        try:
            merged_df = pd.concat(
                [df1, df2],
                axis=0,
                ignore_index=True,
                sort=False
            )
        except Exception as e:
            LOGGER.warning(
                f"Failed to merge tables with error: {e}. "
                f"Using first table only."
            )
            merged_df = df1

        # Update bounding box to cover both tables
        if table1.bbox and table2.bbox:
            merged_bbox = BoundingBox(
                x0=min(table1.bbox.x0, table2.bbox.x0),
                y0=table1.bbox.y0,  # Start of first table
                x1=max(table1.bbox.x1, table2.bbox.x1),
                y1=table2.bbox.y1,  # End of second table
                page=table1.bbox.page,  # Start page
            )
        else:
            merged_bbox = table1.bbox

        # Merge metadata
        merged_metadata = table1.metadata.copy()
        merged_metadata["merged_from_pages"] = [
            table1.bbox.page if table1.bbox else -1,
            table2.bbox.page if table2.bbox else -1,
        ]

        return TableData(
            dataframe=merged_df,
            bbox=merged_bbox,
            page=table1.page,
            metadata=merged_metadata
        )

    def _count_all_sections(self, sections: List[Section]) -> int:
        """
        Count total number of sections (including nested).

        Args:
            sections: List of sections

        Returns:
            Total count
        """
        count = len(sections)
        for section in sections:
            count += self._count_all_sections(section.children)
        return count

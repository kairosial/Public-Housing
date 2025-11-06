"""Layout analyzer using PyMuPDF for fast document structure detection."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple

import fitz  # PyMuPDF

from src.models.document_structure import BoundingBox, TextBlock

LOGGER = logging.getLogger(__name__)


class LayoutAnalyzer:
    """Analyzes PDF layout to detect regions (text, tables, etc.)."""

    def __init__(self) -> None:
        """Initialize layout analyzer."""
        self.min_table_density = 0.3  # Minimum density for table detection

    def analyze(self, pdf_path: Path) -> Dict[int, Dict]:
        """
        Analyze PDF layout and detect regions.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary mapping page numbers to layout information
        """
        doc = fitz.open(str(pdf_path))
        layout_info = {}

        try:
            for page_num in range(len(doc)):
                page = doc[page_num]
                layout_info[page_num] = self._analyze_page(page, page_num)

        finally:
            doc.close()

        return layout_info

    def _analyze_page(self, page: fitz.Page, page_num: int) -> Dict:
        """
        Analyze a single page.

        Args:
            page: PyMuPDF Page object
            page_num: Page number (0-indexed)

        Returns:
            Dictionary with page layout information
        """
        # Extract text blocks with positioning
        blocks = page.get_text("dict")["blocks"]

        text_blocks = []
        table_regions = []

        for block in blocks:
            if block["type"] == 0:  # Text block
                text_blocks.extend(self._extract_text_blocks(block, page_num))
            elif block["type"] == 1:  # Image block (might indicate table)
                pass  # Handle if needed

        # Detect potential table regions based on text density and alignment
        table_regions = self._detect_table_regions(text_blocks, page)

        return {
            "page_num": page_num,
            "text_blocks": text_blocks,
            "table_regions": table_regions,
            "page_size": (page.rect.width, page.rect.height),
        }

    def _extract_text_blocks(
        self, block: Dict, page_num: int
    ) -> List[TextBlock]:
        """
        Extract text blocks from a PyMuPDF text block.

        Args:
            block: PyMuPDF block dictionary
            page_num: Page number

        Returns:
            List of TextBlock objects
        """
        text_blocks = []

        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "").strip()
                if not text:
                    continue

                bbox = BoundingBox(
                    x0=span["bbox"][0],
                    y0=span["bbox"][1],
                    x1=span["bbox"][2],
                    y1=span["bbox"][3],
                    page=page_num,
                )

                text_block = TextBlock(
                    text=text,
                    bbox=bbox,
                    font_size=span.get("size"),
                    font_name=span.get("font"),
                    is_bold="bold" in span.get("font", "").lower(),
                    is_italic="italic" in span.get("font", "").lower(),
                )

                text_blocks.append(text_block)

        return text_blocks

    def _detect_table_regions(
        self, text_blocks: List[TextBlock], page: fitz.Page
    ) -> List[BoundingBox]:
        """
        Detect potential table regions based on text alignment and density.

        Args:
            text_blocks: List of text blocks
            page: PyMuPDF Page object

        Returns:
            List of bounding boxes for potential tables
        """
        if not text_blocks:
            return []

        # Group text blocks by vertical position (rows)
        rows = self._group_into_rows(text_blocks)

        # Detect tables based on regular column alignment
        table_regions = []
        current_table_rows = []

        for row in rows:
            if self._is_table_row(row, rows):
                current_table_rows.append(row)
            else:
                if len(current_table_rows) >= 3:  # Minimum 3 rows for a table
                    bbox = self._create_table_bbox(current_table_rows)
                    table_regions.append(bbox)
                current_table_rows = []

        # Check last accumulated rows
        if len(current_table_rows) >= 3:
            bbox = self._create_table_bbox(current_table_rows)
            table_regions.append(bbox)

        return table_regions

    def _group_into_rows(
        self, text_blocks: List[TextBlock], tolerance: float = 3.0
    ) -> List[List[TextBlock]]:
        """
        Group text blocks into rows based on y-position.

        Args:
            text_blocks: List of text blocks
            tolerance: Y-position tolerance for grouping

        Returns:
            List of rows (each row is a list of text blocks)
        """
        if not text_blocks:
            return []

        # Sort by y-position
        sorted_blocks = sorted(text_blocks, key=lambda b: b.y_position)

        rows = []
        current_row = [sorted_blocks[0]]
        current_y = sorted_blocks[0].y_position

        for block in sorted_blocks[1:]:
            if abs(block.y_position - current_y) <= tolerance:
                current_row.append(block)
            else:
                rows.append(sorted(current_row, key=lambda b: b.x_position))
                current_row = [block]
                current_y = block.y_position

        if current_row:
            rows.append(sorted(current_row, key=lambda b: b.x_position))

        return rows

    def _is_table_row(
        self, row: List[TextBlock], all_rows: List[List[TextBlock]]
    ) -> bool:
        """
        Determine if a row is part of a table.

        Args:
            row: Current row to check
            all_rows: All rows for context

        Returns:
            True if row appears to be part of a table
        """
        if len(row) < 2:  # Tables have multiple columns
            return False

        # Check for regular spacing (columns)
        x_positions = [block.x_position for block in row]

        # Check if x-positions align with other rows
        alignment_count = 0
        for other_row in all_rows:
            if other_row == row:
                continue

            other_x_positions = [block.x_position for block in other_row]

            # Check for similar x-positions (column alignment)
            matches = sum(
                1
                for x1 in x_positions
                for x2 in other_x_positions
                if abs(x1 - x2) < 5.0
            )

            if matches >= 2:  # At least 2 aligned columns
                alignment_count += 1

        return alignment_count >= 2  # Aligned with at least 2 other rows

    def _create_table_bbox(
        self, table_rows: List[List[TextBlock]]
    ) -> BoundingBox:
        """
        Create a bounding box encompassing all table rows.

        Args:
            table_rows: List of rows in the table

        Returns:
            BoundingBox for the entire table
        """
        all_blocks = [block for row in table_rows for block in row]

        if not all_blocks:
            raise ValueError("Cannot create bbox from empty table")

        x0 = min(block.bbox.x0 for block in all_blocks)
        y0 = min(block.bbox.y0 for block in all_blocks)
        x1 = max(block.bbox.x1 for block in all_blocks)
        y1 = max(block.bbox.y1 for block in all_blocks)
        page = all_blocks[0].bbox.page

        return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=page)

    def extract_text_blocks(self, pdf_path: Path) -> Dict[int, List[TextBlock]]:
        """
        Extract all text blocks with positioning information.

        Args:
            pdf_path: Path to PDF file

        Returns:
            Dictionary mapping page numbers to lists of text blocks
        """
        layout_info = self.analyze(pdf_path)
        return {
            page_num: info["text_blocks"]
            for page_num, info in layout_info.items()
        }

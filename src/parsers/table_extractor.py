"""Table extraction using Camelot for complex table structures."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional, Tuple

import camelot
import pandas as pd

from src.models.document_structure import BoundingBox, TableData

LOGGER = logging.getLogger(__name__)


class TableExtractor:
    """Extracts tables from PDF using Camelot."""

    def __init__(self) -> None:
        """Initialize table extractor."""
        self.min_accuracy = 50  # Minimum table accuracy threshold (for initial filter)
        self.min_quality_score = 0.5  # Minimum comprehensive quality score (0-1)

    def extract_tables(
        self,
        pdf_path: Path,
        pages: Optional[str] = None,
        flavor: str = "lattice",
    ) -> List[TableData]:
        """
        Extract all tables from PDF.

        Args:
            pdf_path: Path to PDF file
            pages: Page range (e.g., '1-3' or 'all')
            flavor: 'lattice' for line-based tables, 'stream' for whitespace-based

        Returns:
            List of TableData objects
        """
        if pages is None:
            pages = "all"

        tables = []

        try:
            # Try lattice mode first (better for line-based tables)
            if flavor in ("lattice", "both"):
                lattice_tables = self._extract_with_flavor(
                    pdf_path, pages, "lattice"
                )
                tables.extend(lattice_tables)

            # Try stream mode (better for tables without lines)
            if flavor in ("stream", "both"):
                stream_tables = self._extract_with_flavor(
                    pdf_path, pages, "stream"
                )

                # Only add stream tables that don't overlap with lattice tables
                for stream_table in stream_tables:
                    if not self._overlaps_with_existing(stream_table, tables):
                        tables.append(stream_table)

        except Exception as exc:
            LOGGER.warning(f"Table extraction failed for {pdf_path}: {exc}")

        return tables

    def _extract_with_flavor(
        self, pdf_path: Path, pages: str, flavor: str
    ) -> List[TableData]:
        """
        Extract tables using specified Camelot flavor.

        Args:
            pdf_path: Path to PDF file
            pages: Page range
            flavor: Camelot flavor ('lattice' or 'stream')

        Returns:
            List of TableData objects
        """
        tables = []

        try:
            if flavor == "lattice":
                camelot_tables = camelot.read_pdf(
                    str(pdf_path),
                    pages=pages,
                    flavor="lattice",
                    line_scale=40,  # Sensitivity for detecting lines
                    copy_text=["v"],  # Vertical text handling
                )
            else:  # stream
                camelot_tables = camelot.read_pdf(
                    str(pdf_path),
                    pages=pages,
                    flavor="stream",
                    edge_tol=50,  # Tolerance for table edges
                    row_tol=2,  # Tolerance for row detection
                )

            for idx, table in enumerate(camelot_tables):
                # Skip low-accuracy tables
                if table.accuracy < self.min_accuracy:
                    LOGGER.debug(
                        f"Skipping low-accuracy table (accuracy: {table.accuracy:.1f}%)"
                    )
                    continue

                table_data = self._convert_to_table_data(table, idx, flavor)

                # Calculate comprehensive quality score
                quality_score = self._calculate_table_quality_score(table_data, table)
                table_data.metadata["quality_score"] = quality_score

                # Skip low-quality tables (likely text boxes misdetected as tables)
                if quality_score < self.min_quality_score:
                    LOGGER.debug(
                        f"Skipping low-quality table (quality: {quality_score:.2f}, "
                        f"accuracy: {table.accuracy:.1f}%, shape: {table_data.dataframe.shape})"
                    )
                    continue

                tables.append(table_data)

        except Exception as exc:
            LOGGER.warning(f"Camelot {flavor} extraction failed: {exc}")

        return tables

    def _convert_to_table_data(
        self, camelot_table, table_index: int, flavor: str
    ) -> TableData:
        """
        Convert Camelot table to TableData object.

        Args:
            camelot_table: Camelot Table object
            table_index: Index of table on page
            flavor: Extraction flavor used

        Returns:
            TableData object
        """
        # Get DataFrame and clean it
        df = camelot_table.df.copy()
        df = self._clean_dataframe(df)

        # Extract bounding box (Camelot uses different coordinate system)
        x0, y0, x1, y1 = camelot_table._bbox
        page_num = camelot_table.page - 1  # Camelot uses 1-indexed pages

        bbox = BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=page_num)

        metadata = {
            "accuracy": camelot_table.accuracy,
            "whitespace": camelot_table.whitespace,
            "flavor": flavor,
            "table_index": table_index,
        }

        return TableData(
            dataframe=df, bbox=bbox, page=page_num, metadata=metadata
        )

    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and normalize extracted table DataFrame.

        Args:
            df: Raw DataFrame from Camelot

        Returns:
            Cleaned DataFrame
        """
        # Remove completely empty rows and columns
        df = df.dropna(how="all").dropna(axis=1, how="all")

        # Try to detect if first row is a header
        if len(df) > 0:
            first_row = df.iloc[0]
            if self._is_header_row(first_row):
                df.columns = first_row.values
                df = df.iloc[1:].reset_index(drop=True)

        # Clean cell values
        df = df.map(lambda x: str(x).strip() if pd.notna(x) else "")

        return df

    def _is_header_row(self, row: pd.Series) -> bool:
        """
        Detect if a row is likely a header.

        Args:
            row: DataFrame row

        Returns:
            True if row appears to be a header
        """
        # Headers typically have text in most cells
        non_empty_ratio = row.notna().sum() / len(row)
        return non_empty_ratio > 0.5

    def _calculate_table_quality_score(
        self, table_data: TableData, camelot_table
    ) -> float:
        """
        Calculate comprehensive quality score for a table.

        This helps distinguish real tables from text boxes or misdetected regions.

        Scoring factors:
        - Accuracy (40%): Camelot's built-in accuracy metric
        - Structure (30%): Proper table dimensions (at least 2x2)
        - Content diversity (20%): Cells should have different values
        - Numeric content (10%): Tables often contain numbers

        Args:
            table_data: Converted TableData object
            camelot_table: Original Camelot table object

        Returns:
            Quality score between 0 and 1
        """
        score = 0.0
        df = table_data.dataframe

        # Factor 1: Accuracy (40%)
        # Camelot accuracy ranges from 0-100
        accuracy_score = (camelot_table.accuracy / 100) * 0.4
        score += accuracy_score

        # Factor 2: Structure (30%)
        # Real tables should have at least 2 rows and 2 columns
        rows, cols = df.shape
        if rows >= 2 and cols >= 2:
            # Award full points for minimum structure
            structure_score = 0.3
            # Bonus for larger tables (up to 5x5)
            size_bonus = min(rows * cols / 25, 1.0) * 0.05
            score += structure_score + size_bonus
        elif rows >= 1 and cols >= 1:
            # Partial credit for 1xN or Nx1 tables
            score += 0.1

        # Factor 3: Content diversity (20%)
        # Text boxes often have repeated values or single long text
        total_cells = rows * cols
        if total_cells > 0:
            unique_values = df.stack().nunique()
            diversity_ratio = unique_values / total_cells
            # High diversity = likely a real table
            diversity_score = min(diversity_ratio, 1.0) * 0.2
            score += diversity_score

        # Factor 4: Numeric content (10%)
        # Tables often contain numbers (vs pure text in text boxes)
        numeric_cells = 0
        for col in df.columns:
            numeric_cells += df[col].apply(
                lambda x: bool(pd.to_numeric(x, errors='coerce') is not pd.NA)
            ).sum()

        if total_cells > 0:
            numeric_ratio = numeric_cells / total_cells
            numeric_score = numeric_ratio * 0.1
            score += numeric_score

        LOGGER.debug(
            f"Table quality: {score:.2f} "
            f"(accuracy={accuracy_score:.2f}, structure={rows}x{cols}, "
            f"diversity={unique_values}/{total_cells}, numeric={numeric_cells}/{total_cells})"
        )

        return score

    def _overlaps_with_existing(
        self, table: TableData, existing_tables: List[TableData]
    ) -> bool:
        """
        Check if table overlaps with any existing table.

        Args:
            table: Table to check
            existing_tables: List of existing tables

        Returns:
            True if table overlaps with any existing table
        """
        for existing in existing_tables:
            if table.bbox.overlaps(existing.bbox):
                # Check overlap percentage
                overlap_area = self._calculate_overlap_area(
                    table.bbox, existing.bbox
                )
                table_area = table.bbox.width * table.bbox.height

                if table_area > 0 and overlap_area / table_area > 0.5:
                    return True

        return False

    def _calculate_overlap_area(
        self, bbox1: BoundingBox, bbox2: BoundingBox
    ) -> float:
        """
        Calculate overlapping area between two bounding boxes.

        Args:
            bbox1: First bounding box
            bbox2: Second bounding box

        Returns:
            Overlap area
        """
        if bbox1.page != bbox2.page:
            return 0.0

        x_overlap = max(
            0, min(bbox1.x1, bbox2.x1) - max(bbox1.x0, bbox2.x0)
        )
        y_overlap = max(
            0, min(bbox1.y1, bbox2.y1) - max(bbox1.y0, bbox2.y0)
        )

        return x_overlap * y_overlap

    def extract_table_at_region(
        self,
        pdf_path: Path,
        page: int,
        bbox: BoundingBox,
        flavor: str = "lattice",
    ) -> Optional[TableData]:
        """
        Extract table at specific region.

        Args:
            pdf_path: Path to PDF file
            page: Page number (0-indexed)
            bbox: Bounding box of table region
            flavor: Camelot flavor to use

        Returns:
            TableData if successful, None otherwise
        """
        try:
            # Camelot uses 1-indexed pages
            page_str = str(page + 1)

            # Camelot table_areas format: ["x1,y1,x2,y2"]
            table_area = f"{bbox.x0},{bbox.y1},{bbox.x1},{bbox.y0}"

            if flavor == "lattice":
                tables = camelot.read_pdf(
                    str(pdf_path),
                    pages=page_str,
                    flavor="lattice",
                    table_areas=[table_area],
                )
            else:
                tables = camelot.read_pdf(
                    str(pdf_path),
                    pages=page_str,
                    flavor="stream",
                    table_regions=[table_area],
                )

            if tables and len(tables) > 0:
                return self._convert_to_table_data(tables[0], 0, flavor)

        except Exception as exc:
            LOGGER.warning(f"Failed to extract table at region: {exc}")

        return None

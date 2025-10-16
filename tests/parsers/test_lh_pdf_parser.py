"""Tests for LH PDF parser."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from src.models.document_structure import (
    BoundingBox,
    Document,
    Section,
    TableData,
    TextBlock,
)
from src.parsers.lh_pdf_parser import LHPDFParser


@pytest.fixture
def sample_pdf_path(tmp_path: Path) -> Path:
    """Create a sample PDF file path."""
    pdf_file = tmp_path / "sample.pdf"
    # Note: This is just a path, actual PDF creation is mocked in tests
    return pdf_file


@pytest.fixture
def parser() -> LHPDFParser:
    """Create LH PDF parser instance."""
    return LHPDFParser()


class TestLHPDFParser:
    """Test suite for LHPDFParser."""

    def test_initialization(self, parser: LHPDFParser) -> None:
        """Test parser initialization."""
        assert parser.layout_analyzer is not None
        assert parser.table_extractor is not None
        assert parser.hierarchy_parser is not None

    def test_validate_pdf_nonexistent(
        self, parser: LHPDFParser, tmp_path: Path
    ) -> None:
        """Test PDF validation with nonexistent file."""
        nonexistent = tmp_path / "nonexistent.pdf"
        assert parser.validate_pdf(nonexistent) is False

    def test_validate_pdf_wrong_extension(
        self, parser: LHPDFParser, tmp_path: Path
    ) -> None:
        """Test PDF validation with wrong file extension."""
        wrong_file = tmp_path / "file.txt"
        wrong_file.touch()
        assert parser.validate_pdf(wrong_file) is False

    @patch("src.parsers.lh_pdf_parser.LayoutAnalyzer")
    @patch("src.parsers.lh_pdf_parser.TableExtractor")
    @patch("src.parsers.lh_pdf_parser.HierarchyParser")
    def test_parse_integration(
        self,
        mock_hierarchy_parser: Mock,
        mock_table_extractor: Mock,
        mock_layout_analyzer: Mock,
        parser: LHPDFParser,
        sample_pdf_path: Path,
    ) -> None:
        """Test full PDF parsing integration."""
        # Setup mocks
        mock_layout_analyzer.return_value.analyze.return_value = {
            0: {
                "text_blocks": [],
                "table_regions": [
                    BoundingBox(x0=100, y0=200, x1=400, y1=300, page=0)
                ],
            }
        }

        mock_table = TableData(
            dataframe=pd.DataFrame({"col1": ["a", "b"], "col2": ["c", "d"]}),
            bbox=BoundingBox(x0=100, y0=200, x1=400, y1=300, page=0),
            page=0,
            metadata={},
        )
        mock_table_extractor.return_value.extract_tables.return_value = [
            mock_table
        ]

        mock_section = Section(
            level=1,
            title="1. Test Section",
            bbox=BoundingBox(x0=100, y0=100, x1=400, y1=150, page=0),
            content=["Test content"],
        )
        mock_hierarchy_parser.return_value.parse.return_value = [mock_section]

        # Create actual file
        sample_pdf_path.touch()

        # Re-create parser with mocked components
        parser.layout_analyzer = mock_layout_analyzer.return_value
        parser.table_extractor = mock_table_extractor.return_value
        parser.hierarchy_parser = mock_hierarchy_parser.return_value

        # Execute parse
        document = parser.parse(sample_pdf_path)

        # Assertions
        assert isinstance(document, Document)
        assert len(document.sections) == 1
        assert document.sections[0].title == "1. Test Section"
        assert document.metadata["total_sections"] == 1
        assert document.metadata["source"] == str(sample_pdf_path)

    def test_merge_tables_into_sections(self, parser: LHPDFParser) -> None:
        """Test merging tables into sections."""
        section = Section(
            level=1,
            title="Test Section",
            bbox=BoundingBox(x0=100, y0=100, x1=400, y1=150, page=0),
        )

        table = TableData(
            dataframe=pd.DataFrame({"col1": ["a"]}),
            bbox=BoundingBox(x0=100, y0=200, x1=400, y1=300, page=0),
            page=0,
            metadata={},
        )

        parser._merge_tables_into_sections([section], [table])

        assert len(section.tables) == 1
        assert section.tables[0] == table

    def test_find_best_section_for_table_same_page(
        self, parser: LHPDFParser
    ) -> None:
        """Test finding best section for table on same page."""
        section1 = Section(
            level=1,
            title="Section 1",
            bbox=BoundingBox(x0=100, y0=100, x1=400, y1=150, page=0),
        )
        section2 = Section(
            level=1,
            title="Section 2",
            bbox=BoundingBox(x0=100, y0=100, x1=400, y1=150, page=1),
        )

        table = TableData(
            dataframe=pd.DataFrame({"col1": ["a"]}),
            bbox=BoundingBox(x0=100, y0=200, x1=400, y1=300, page=0),
            page=0,
            metadata={},
        )

        best = parser._find_best_section_for_table([section1, section2], table)

        assert best == section1

    def test_find_best_section_for_table_nested(
        self, parser: LHPDFParser
    ) -> None:
        """Test finding best section with nested sections."""
        child_section = Section(
            level=2,
            title="Child Section",
            bbox=BoundingBox(x0=100, y0=150, x1=400, y1=180, page=0),
        )

        parent_section = Section(
            level=1,
            title="Parent Section",
            bbox=BoundingBox(x0=100, y0=100, x1=400, y1=150, page=0),
            children=[child_section],
        )

        table = TableData(
            dataframe=pd.DataFrame({"col1": ["a"]}),
            bbox=BoundingBox(x0=100, y0=200, x1=400, y1=300, page=0),
            page=0,
            metadata={},
        )

        best = parser._find_best_section_for_table([parent_section], table)

        # Should prefer child section (higher depth score)
        assert best == child_section

    def test_can_merge_tables_consecutive_pages(
        self, parser: LHPDFParser
    ) -> None:
        """Test table merging criteria with consecutive pages."""
        table1 = TableData(
            dataframe=pd.DataFrame({"col1": ["a"], "col2": ["b"]}),
            bbox=BoundingBox(x0=100, y0=500, x1=400, y1=700, page=0),
            page=0,
            metadata={},
        )

        table2 = TableData(
            dataframe=pd.DataFrame({"col1": ["c"], "col2": ["d"]}),
            bbox=BoundingBox(x0=100, y0=50, x1=400, y1=150, page=1),
            page=1,
            metadata={},
        )

        assert parser._can_merge_tables(table1, table2) is True

    def test_can_merge_tables_different_columns(
        self, parser: LHPDFParser
    ) -> None:
        """Test table merging criteria with different column counts."""
        table1 = TableData(
            dataframe=pd.DataFrame({"col1": ["a"], "col2": ["b"]}),
            bbox=BoundingBox(x0=100, y0=500, x1=400, y1=700, page=0),
            page=0,
            metadata={},
        )

        table2 = TableData(
            dataframe=pd.DataFrame({"col1": ["c"]}),  # Different column count
            bbox=BoundingBox(x0=100, y0=50, x1=400, y1=150, page=1),
            page=1,
            metadata={},
        )

        assert parser._can_merge_tables(table1, table2) is False

    def test_can_merge_tables_non_consecutive_pages(
        self, parser: LHPDFParser
    ) -> None:
        """Test table merging criteria with non-consecutive pages."""
        table1 = TableData(
            dataframe=pd.DataFrame({"col1": ["a"]}),
            bbox=BoundingBox(x0=100, y0=500, x1=400, y1=700, page=0),
            page=0,
            metadata={},
        )

        table2 = TableData(
            dataframe=pd.DataFrame({"col1": ["c"]}),
            bbox=BoundingBox(x0=100, y0=50, x1=400, y1=150, page=2),
            metadata={},
        )

        assert parser._can_merge_tables(table1, table2) is False

    def test_merge_two_tables(self, parser: LHPDFParser) -> None:
        """Test merging two tables."""
        table1 = TableData(
            dataframe=pd.DataFrame({"col1": ["a"], "col2": ["b"]}),
            bbox=BoundingBox(x0=100, y0=500, x1=400, y1=700, page=0),
            page=0,
            metadata={"accuracy": 95.0},
        )

        table2 = TableData(
            dataframe=pd.DataFrame({"col1": ["c"], "col2": ["d"]}),
            bbox=BoundingBox(x0=100, y0=50, x1=400, y1=150, page=1),
            page=1,
            metadata={"accuracy": 92.0},
        )

        merged = parser._merge_two_tables(table1, table2)

        assert len(merged.dataframe) == 2
        assert list(merged.dataframe["col1"]) == ["a", "c"]
        assert list(merged.dataframe["col2"]) == ["b", "d"]
        assert merged.bbox.page == 0
        assert merged.bbox.y0 == 500
        assert merged.bbox.y1 == 150
        assert "merged_from_pages" in merged.metadata

    def test_merge_cross_page_tables(self, parser: LHPDFParser) -> None:
        """Test cross-page table merging."""
        table1 = TableData(
            dataframe=pd.DataFrame({"col1": ["a"], "col2": ["b"]}),
            bbox=BoundingBox(x0=100, y0=500, x1=400, y1=700, page=0),
            page=0,
            metadata={},
        )

        table2 = TableData(
            dataframe=pd.DataFrame({"col1": ["c"], "col2": ["d"]}),
            bbox=BoundingBox(x0=100, y0=50, x1=400, y1=150, page=1),
            page=1,
            metadata={},
        )

        table3 = TableData(
            dataframe=pd.DataFrame({"col1": ["e"], "col2": ["f"]}),
            bbox=BoundingBox(x0=100, y0=500, x1=400, y1=700, page=2),
            page=2,
            metadata={},
        )

        merged = parser._merge_cross_page_tables([table1, table2, table3])

        # table1 and table2 should be merged, table3 separate
        assert len(merged) == 2
        assert len(merged[0].dataframe) == 2  # Merged table
        assert len(merged[1].dataframe) == 1  # Separate table

    def test_count_all_sections(self, parser: LHPDFParser) -> None:
        """Test counting nested sections."""
        child1 = Section(level=2, title="Child 1")
        child2 = Section(level=2, title="Child 2")
        grandchild = Section(level=3, title="Grandchild")

        child2.children.append(grandchild)

        parent = Section(
            level=1, title="Parent", children=[child1, child2]
        )

        total = parser._count_all_sections([parent])
        assert total == 4  # parent + child1 + child2 + grandchild

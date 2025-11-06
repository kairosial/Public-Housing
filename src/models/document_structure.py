"""Document structure models for parsed PDF content."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd


class ElementType(Enum):
    """Types of document elements."""

    TITLE = "title"
    SECTION_HEADING = "section_heading"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST_ITEM = "list_item"
    EMPHASIZED = "emphasized"


@dataclass
class BoundingBox:
    """Bounding box coordinates for document elements."""

    x0: float
    y0: float
    x1: float
    y1: float
    page: int

    @property
    def width(self) -> float:
        """Calculate width of bounding box."""
        return self.x1 - self.x0

    @property
    def height(self) -> float:
        """Calculate height of bounding box."""
        return self.y1 - self.y0

    def overlaps(self, other: BoundingBox) -> bool:
        """Check if this bbox overlaps with another."""
        if self.page != other.page:
            return False

        return not (
            self.x1 < other.x0
            or self.x0 > other.x1
            or self.y1 < other.y0
            or self.y0 > other.y1
        )


@dataclass
class TextBlock:
    """A block of text with positioning information."""

    text: str
    bbox: BoundingBox
    font_size: Optional[float] = None
    font_name: Optional[str] = None
    is_bold: bool = False
    is_italic: bool = False

    @property
    def x_position(self) -> float:
        """Get x-coordinate (for detecting indentation)."""
        return self.bbox.x0

    @property
    def y_position(self) -> float:
        """Get y-coordinate (for detecting vertical order)."""
        return self.bbox.y0


@dataclass
class TableData:
    """Structured table data."""

    dataframe: pd.DataFrame
    bbox: BoundingBox
    page: int
    caption: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert table to dictionary representation."""
        return {
            "data": self.dataframe.to_dict(orient="records"),
            "columns": list(self.dataframe.columns),
            "shape": self.dataframe.shape,
            "page": self.page,
            "caption": self.caption,
            "bbox": {
                "x0": self.bbox.x0,
                "y0": self.bbox.y0,
                "x1": self.bbox.x1,
                "y1": self.bbox.y1,
            },
            "metadata": self.metadata,
        }


@dataclass
class Section:
    """A hierarchical section of the document."""

    level: int  # 1 = top level, 2 = subsection, etc.
    title: str
    bbox: Optional[BoundingBox] = None
    content: List[str] = field(default_factory=list)
    children: List[Section] = field(default_factory=list)
    tables: List[TableData] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_child(self, child: Section) -> None:
        """Add a child section."""
        self.children.append(child)

    def add_table(self, table: TableData) -> None:
        """Add a table to this section."""
        self.tables.append(table)

    def to_dict(self) -> Dict[str, Any]:
        """Convert section to dictionary representation."""
        return {
            "level": self.level,
            "title": self.title,
            "content": self.content,
            "children": [child.to_dict() for child in self.children],
            "tables": [table.to_dict() for table in self.tables],
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        """Return string representation."""
        indent = "  " * (self.level - 1)
        return f"{indent}{self.level}. {self.title} ({len(self.children)} subsections, {len(self.tables)} tables)"


@dataclass
class Document:
    """Complete parsed document structure."""

    source_path: Path
    sections: List[Section] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_section(self, section: Section) -> None:
        """Add a top-level section."""
        self.sections.append(section)

    def get_all_tables(self) -> List[TableData]:
        """Get all tables from all sections recursively."""
        tables = []

        def collect_tables(section: Section) -> None:
            tables.extend(section.tables)
            for child in section.children:
                collect_tables(child)

        for section in self.sections:
            collect_tables(section)

        return tables

    def find_section(self, title_pattern: str) -> Optional[Section]:
        """Find a section by title pattern (case-insensitive)."""
        title_lower = title_pattern.lower()

        def search(section: Section) -> Optional[Section]:
            if title_lower in section.title.lower():
                return section
            for child in section.children:
                result = search(child)
                if result:
                    return result
            return None

        for section in self.sections:
            result = search(section)
            if result:
                return result

        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert document to dictionary representation."""
        return {
            "source": str(self.source_path),
            "sections": [section.to_dict() for section in self.sections],
            "metadata": self.metadata,
            "statistics": {
                "total_sections": len(self.sections),
                "total_tables": len(self.get_all_tables()),
            },
        }

    def print_structure(self, max_depth: Optional[int] = None) -> None:
        """Print document structure in a readable format."""
        print(f"Document: {self.source_path.name}")
        print("=" * 80)

        def print_section(section: Section, depth: int = 0) -> None:
            if max_depth and depth >= max_depth:
                return

            indent = "  " * depth
            print(f"{indent}{section.level}. {section.title}")

            if section.content:
                content_preview = " ".join(section.content)[:100]
                print(f"{indent}   Content: {content_preview}...")

            if section.tables:
                print(f"{indent}   Tables: {len(section.tables)}")

            for child in section.children:
                print_section(child, depth + 1)

        for section in self.sections:
            print_section(section)
        print("=" * 80)

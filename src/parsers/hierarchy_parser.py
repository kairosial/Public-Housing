"""Hierarchical structure parsing using pdfplumber for text extraction."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pdfplumber

from src.models.document_structure import BoundingBox, Section, TextBlock

LOGGER = logging.getLogger(__name__)


class HierarchyParser:
    """Parses hierarchical document structure from PDF text."""

    def __init__(self) -> None:
        """Initialize hierarchy parser."""
        # Patterns for detecting section headings
        self.heading_patterns = [
            re.compile(r"^(\d+)\.\s+(.+)$"),  # "1. Title"
            re.compile(r"^(\d+-\d+)\.\s+(.+)$"),  # "3-1. Subtitle"
            re.compile(r"^([가-힣])\.\s+(.+)$"),  # "가. Title"
            re.compile(r"^■\s+(.+)$"),  # "■ Title"
            re.compile(r"^▶\s+(.+)$"),  # "▶ Title"
        ]

        # Threshold for detecting indentation levels
        self.indent_threshold = 20  # pixels
        self.base_x_position = None  # Will be set dynamically

    def parse(
        self,
        pdf_path: Path,
        exclude_regions: Optional[List[BoundingBox]] = None,
    ) -> List[Section]:
        """
        Parse hierarchical structure from PDF.

        Args:
            pdf_path: Path to PDF file
            exclude_regions: Bounding boxes to exclude (e.g., tables)

        Returns:
            List of top-level sections
        """
        with pdfplumber.open(pdf_path) as pdf:
            all_text_blocks = []

            for page_num, page in enumerate(pdf.pages):
                text_blocks = self._extract_text_blocks(page, page_num)

                # Filter out excluded regions
                if exclude_regions:
                    text_blocks = self._filter_excluded_regions(
                        text_blocks, exclude_regions
                    )

                all_text_blocks.extend(text_blocks)

        # Build hierarchical structure
        sections = self._build_hierarchy(all_text_blocks)

        return sections

    def _extract_text_blocks(
        self, page: pdfplumber.page.Page, page_num: int
    ) -> List[TextBlock]:
        """
        Extract text blocks with position information from a page.

        Args:
            page: pdfplumber Page object
            page_num: Page number (0-indexed)

        Returns:
            List of TextBlock objects
        """
        text_blocks = []

        # Extract words with position information
        words = page.extract_words(
            x_tolerance=3, y_tolerance=3, keep_blank_chars=True
        )

        if not words:
            return text_blocks

        # Group words into lines
        lines = self._group_words_into_lines(words, page_num)

        # Convert lines to text blocks
        for line_words in lines:
            if not line_words:
                continue

            # Combine words in line
            text = " ".join(word["text"] for word in line_words)

            # Calculate bounding box for entire line
            x0 = min(word["x0"] for word in line_words)
            y0 = min(word["top"] for word in line_words)
            x1 = max(word["x1"] for word in line_words)
            y1 = max(word["bottom"] for word in line_words)

            bbox = BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=page_num)

            # Detect formatting (approximate)
            avg_height = sum(word["height"] for word in line_words) / len(
                line_words
            )
            font_name = line_words[0].get("fontname", "")

            text_block = TextBlock(
                text=text,
                bbox=bbox,
                font_size=avg_height,
                font_name=font_name,
                is_bold="bold" in font_name.lower(),
                is_italic="italic" in font_name.lower(),
            )

            text_blocks.append(text_block)

        return text_blocks

    def _group_words_into_lines(
        self, words: List[Dict], page_num: int, tolerance: float = 3.0
    ) -> List[List[Dict]]:
        """
        Group words into lines based on vertical position.

        Args:
            words: List of word dictionaries from pdfplumber
            page_num: Page number
            tolerance: Y-position tolerance for grouping

        Returns:
            List of lines (each line is a list of words)
        """
        if not words:
            return []

        # Sort by vertical position, then horizontal
        sorted_words = sorted(words, key=lambda w: (w["top"], w["x0"]))

        lines = []
        current_line = [sorted_words[0]]
        current_y = sorted_words[0]["top"]

        for word in sorted_words[1:]:
            if abs(word["top"] - current_y) <= tolerance:
                current_line.append(word)
            else:
                lines.append(sorted(current_line, key=lambda w: w["x0"]))
                current_line = [word]
                current_y = word["top"]

        if current_line:
            lines.append(sorted(current_line, key=lambda w: w["x0"]))

        return lines

    def _filter_excluded_regions(
        self, text_blocks: List[TextBlock], exclude_regions: List[BoundingBox]
    ) -> List[TextBlock]:
        """
        Filter out text blocks in excluded regions.

        Args:
            text_blocks: List of text blocks
            exclude_regions: Regions to exclude

        Returns:
            Filtered list of text blocks
        """
        filtered = []

        for block in text_blocks:
            is_excluded = False

            for exclude_bbox in exclude_regions:
                if block.bbox.overlaps(exclude_bbox):
                    is_excluded = True
                    break

            if not is_excluded:
                filtered.append(block)

        return filtered

    def _build_hierarchy(self, text_blocks: List[TextBlock]) -> List[Section]:
        """
        Build hierarchical section structure from text blocks.

        Args:
            text_blocks: List of text blocks

        Returns:
            List of top-level sections
        """
        if not text_blocks:
            return []

        # Determine base x-position (leftmost common position)
        self.base_x_position = self._calculate_base_x_position(text_blocks)

        sections = []
        current_section_stack: List[Section] = []

        for block in text_blocks:
            # Detect if this block is a heading
            heading_info = self._detect_heading(block)

            if heading_info:
                level, title = heading_info

                # Create new section
                new_section = Section(level=level, title=title, bbox=block.bbox)

                # Find parent section based on level
                while (
                    current_section_stack
                    and current_section_stack[-1].level >= level
                ):
                    current_section_stack.pop()

                if current_section_stack:
                    # Add as child to parent
                    current_section_stack[-1].add_child(new_section)
                else:
                    # Top-level section
                    sections.append(new_section)

                current_section_stack.append(new_section)

            else:
                # Regular content - add to current section
                if current_section_stack:
                    current_section_stack[-1].content.append(block.text)

        return sections

    def _detect_heading(
        self, block: TextBlock
    ) -> Optional[Tuple[int, str]]:
        """
        Detect if text block is a heading and determine its level.

        Args:
            block: Text block to check

        Returns:
            Tuple of (level, title) if heading, None otherwise
        """
        text = block.text.strip()

        # Check numbered headings (1., 2., etc.)
        match = re.match(r"^(\d+)\.\s+(.+)$", text)
        if match:
            number = int(match.group(1))
            title = match.group(2)
            return (1, text)  # Top-level section

        # Check sub-numbered headings (3-1., 3-2., etc.)
        match = re.match(r"^(\d+)-(\d+)\.\s+(.+)$", text)
        if match:
            title = match.group(3)
            return (2, text)  # Second-level section

        # Check Korean letter headings (가., 나., etc.)
        match = re.match(r"^([가-힣])\.\s+(.+)$", text)
        if match:
            title = match.group(2)
            return (3, text)  # Third-level section

        # Check bullet points
        if text.startswith("■ "):
            return (2, text[2:].strip())

        if text.startswith("▶ "):
            return (3, text[2:].strip())

        # Check by formatting (bold, large font)
        if block.is_bold or (
            block.font_size and block.font_size > 12
        ):
            # Detect level by indentation
            level = self._detect_indentation_level(block)
            if level > 0:
                return (level, text)

        return None

    def _detect_indentation_level(self, block: TextBlock) -> int:
        """
        Detect indentation level based on x-position.

        Args:
            block: Text block

        Returns:
            Indentation level (0 = not indented, 1+ = indented)
        """
        if self.base_x_position is None:
            return 0

        indent = block.x_position - self.base_x_position

        if indent < self.indent_threshold:
            return 1  # Base level
        elif indent < self.indent_threshold * 2:
            return 2
        elif indent < self.indent_threshold * 3:
            return 3
        else:
            return 4

    def _calculate_base_x_position(
        self, text_blocks: List[TextBlock]
    ) -> float:
        """
        Calculate the base (leftmost common) x-position.

        Args:
            text_blocks: List of text blocks

        Returns:
            Base x-position
        """
        if not text_blocks:
            return 0.0

        # Find most common x-position (rounding to nearest 5 pixels)
        x_positions = [round(block.x_position / 5) * 5 for block in text_blocks]

        from collections import Counter

        counter = Counter(x_positions)
        most_common_x = counter.most_common(1)[0][0]

        return most_common_x

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

                # IMPORTANT: Filter carefully - preserve headings even in table regions
                if exclude_regions:
                    text_blocks = self._filter_excluded_regions_smart(
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

    def _filter_excluded_regions_smart(
        self, text_blocks: List[TextBlock], exclude_regions: List[BoundingBox]
    ) -> List[TextBlock]:
        """
        Smart filtering that preserves section headings but excludes table content.

        Strategy:
        1. Identify which blocks are headings
        2. Always preserve heading blocks (even if in table regions)
        3. For non-headings, calculate overlap ratio with table regions
        4. Exclude content if overlap > 50% (likely table data)

        Args:
            text_blocks: List of text blocks
            exclude_regions: Regions to exclude (e.g., table bboxes)

        Returns:
            Filtered list of text blocks with headings preserved
        """
        filtered = []

        for block in text_blocks:
            # Check if this is a heading
            is_heading = self._detect_heading(block) is not None

            if is_heading:
                # Always keep headings, even if they overlap with tables
                filtered.append(block)
                LOGGER.debug(
                    f"Preserved heading: {block.text[:50]}"
                )
            else:
                # For non-headings, check overlap with table regions
                overlap_ratio = self._calculate_max_overlap_ratio(
                    block.bbox, exclude_regions
                )

                # Strict exclusion: if >50% overlap with table, exclude it
                if overlap_ratio < 0.5:
                    filtered.append(block)
                else:
                    LOGGER.debug(
                        f"Excluded content in table region (overlap={overlap_ratio:.1%}): "
                        f"{block.text[:50]}"
                    )

        return filtered

    def _calculate_max_overlap_ratio(
        self, bbox: BoundingBox, exclude_regions: List[BoundingBox]
    ) -> float:
        """
        Calculate the maximum overlap ratio between a bbox and exclude regions.

        Args:
            bbox: Bounding box to check
            exclude_regions: List of regions to check against

        Returns:
            Maximum overlap ratio (0.0 to 1.0)
        """
        max_ratio = 0.0
        bbox_area = bbox.width * bbox.height

        if bbox_area == 0:
            return 0.0

        for exclude_bbox in exclude_regions:
            if not bbox.overlaps(exclude_bbox):
                continue

            # Calculate overlap area
            x_overlap = max(
                0, min(bbox.x1, exclude_bbox.x1) - max(bbox.x0, exclude_bbox.x0)
            )
            y_overlap = max(
                0, min(bbox.y1, exclude_bbox.y1) - max(bbox.y0, exclude_bbox.y0)
            )
            overlap_area = x_overlap * y_overlap

            # Calculate overlap ratio
            overlap_ratio = overlap_area / bbox_area
            max_ratio = max(max_ratio, overlap_ratio)

        return max_ratio

    def _build_hierarchy(self, text_blocks: List[TextBlock]) -> List[Section]:
        """
        Build hierarchical section structure from text blocks.

        Hierarchy levels:
        - Level 0: Document title (optional, large centered text)
        - Level 1: Main sections (1., 2., 3., ...)
        - Level 2: Subsections (■, sub-numbers)
        - Level 3: Sub-subsections (○, ▪, •, ▶)

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
            # First check if this is a subtitle (parenthesized text after Level 0 title)
            if self._detect_subtitle(block, sections):
                # Create subtitle as Level 1 child of the last Level 0 title
                subtitle_section = Section(
                    level=1,
                    title=block.text.strip(),
                    bbox=block.bbox
                )
                sections[-1].add_child(subtitle_section)
                LOGGER.debug(f"Detected subtitle: {block.text.strip()}")
                continue

            # Detect if this block is a heading
            heading_info = self._detect_heading(block)

            if heading_info:
                level, title = heading_info

                # Create new section
                new_section = Section(level=level, title=title, bbox=block.bbox)

                # Special handling for level 0 (document title)
                if level == 0:
                    # Document title goes to top level but doesn't affect stack
                    sections.append(new_section)
                    continue

                # Find parent section based on level
                # Pop sections with level >= current level
                while (
                    current_section_stack
                    and current_section_stack[-1].level >= level
                ):
                    current_section_stack.pop()

                if current_section_stack:
                    # Add as child to parent
                    current_section_stack[-1].add_child(new_section)
                else:
                    # Top-level section (level 1)
                    sections.append(new_section)

                current_section_stack.append(new_section)

            else:
                # Regular content - add to current section
                if current_section_stack:
                    current_section_stack[-1].content.append(block.text)
                elif sections:
                    # If no section stack but we have sections (e.g., after doc title)
                    # Add to last section
                    sections[-1].content.append(block.text)

        # Post-process: merge bullet point paragraphs
        self._consolidate_bullet_paragraphs(sections)

        return sections

    def _consolidate_bullet_paragraphs(self, sections: List[Section]) -> None:
        """
        Consolidate multi-line bullet point paragraphs into single content entries.

        Bullet paragraphs (starting with •) are often split across multiple lines.
        This method merges them back together for better readability.

        Args:
            sections: List of sections to process (modified in-place)
        """
        for section in sections:
            if section.content:
                section.content = self._merge_bullet_lines(section.content)

            # Recursively process children
            if section.children:
                self._consolidate_bullet_paragraphs(section.children)

    def _merge_bullet_lines(self, content_lines: List[str]) -> List[str]:
        """
        Merge consecutive lines that belong to the same bullet paragraph.

        Args:
            content_lines: List of content lines

        Returns:
            Merged content lines
        """
        if not content_lines:
            return content_lines

        merged = []
        current_paragraph = []

        for line in content_lines:
            stripped = line.strip()

            # Check if this is a bullet point start
            if stripped.startswith("• "):
                # Save previous paragraph if exists
                if current_paragraph:
                    merged.append(" ".join(current_paragraph))
                    current_paragraph = []

                # Start new paragraph
                current_paragraph.append(stripped)

            elif current_paragraph:
                # This is a continuation of the current bullet paragraph
                # (doesn't start with • but we have an active paragraph)
                current_paragraph.append(stripped)

            else:
                # Regular content (not part of bullet paragraph)
                merged.append(line)

        # Don't forget the last paragraph
        if current_paragraph:
            merged.append(" ".join(current_paragraph))

        return merged

    def _detect_subtitle(self, block: TextBlock, previous_sections: List[Section]) -> bool:
        """
        Detect if a block is a subtitle (should be child of previous Level 0 title).

        Subtitles are typically:
        - Parenthesized text: (입주자모집공고일 : 2025.09.29)
        - Appear immediately after a Level 0 document title
        - Have medium-large font but not as large as main title

        Args:
            block: Text block to check
            previous_sections: List of previously parsed sections

        Returns:
            True if this is a subtitle that should be attached to previous title
        """
        text = block.text.strip()

        # Pattern 1: Parenthesized date/metadata
        if re.match(r"^\([^)]{5,80}\)$", text):
            # Check if previous section was a Level 0 title
            if previous_sections and previous_sections[-1].level == 0:
                # Check if there are no children yet (subtitle should be first child)
                if len(previous_sections[-1].children) == 0:
                    return True

        return False

    def _detect_heading(
        self, block: TextBlock
    ) -> Optional[Tuple[int, str]]:
        """
        Detect if text block is a heading and determine its level.

        Strategy:
        1. Check indentation and font size FIRST
        2. Then apply pattern matching
        3. For numbered patterns with indentation/small font, use indentation-based level

        Args:
            block: Text block to check

        Returns:
            Tuple of (level, title) if heading, None otherwise
        """
        text = block.text.strip()

        # Calculate indentation level for this block
        indent_level = self._detect_indentation_level(block)
        is_small_font = block.font_size and block.font_size < 10
        is_indented = indent_level > 1  # Level 2+ means indented

        # Check numbered headings (1., 2., etc.)
        match = re.match(r"^(\d+)\.\s+(.+)$", text)
        if match:
            number = int(match.group(1))
            title = match.group(2).strip()

            # INDENTATION-FIRST LOGIC:
            # If small font OR indented, use indentation level instead of default Level 1
            if is_small_font or is_indented:
                # Use indentation level (but ensure it's at least 3 for sub-items)
                detected_level = max(3, indent_level)
                LOGGER.debug(
                    f"Numbered item '{number}. {title[:30]}...' detected with "
                    f"indent_level={indent_level}, font_size={block.font_size}, "
                    f"assigned level={detected_level}"
                )
                return (detected_level, f"{number}. {title}")
            else:
                # Large font + no indentation = main section (Level 1)
                return (1, f"{number}. {title}")

        # Check sub-numbered headings (3-1., 3-2., etc.)
        match = re.match(r"^(\d+)-(\d+)\.\s+(.+)$", text)
        if match:
            title = match.group(3).strip()
            prefix = f"{match.group(1)}-{match.group(2)}"
            return (2, f"{prefix}. {title}")  # Second-level section

        # Check Korean letter headings (가., 나., etc.)
        match = re.match(r"^([가-힣])\.\s+(.+)$", text)
        if match:
            letter = match.group(1)
            title = match.group(2).strip()
            return (3, f"{letter}. {title}")  # Third-level section

        # Check bullet points - multiple types
        # ■ (Black square) - Level 2
        if text.startswith("■ "):
            return (2, text.strip())

        # ▪ (Small black square) - Level 3
        if text.startswith("▪ ") or text.startswith("▪"):
            return (3, text.strip())

        # ○ (White circle) - Level 3
        if text.startswith("○ "):
            return (3, text.strip())

        # NOTE: • (Bullet point) is NO LONGER treated as heading
        # It will be parsed as regular content to keep paragraphs together

        # ▶ (Triangle) - Level 3
        if text.startswith("▶ "):
            return (3, text.strip())

        # Check by formatting (bold, large font) for potential main title
        # Large centered text could be document title (level 0)
        if block.font_size and block.font_size > 14:
            # Very large font - likely document title
            return (0, text)
        elif block.is_bold or (block.font_size and block.font_size > 12):
            # Moderately large/bold - detect level by indentation
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

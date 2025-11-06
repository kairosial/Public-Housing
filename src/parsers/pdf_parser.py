"""Base PDF parser interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from src.models.document_structure import Document


class PDFParser(ABC):
    """Abstract base class for PDF parsers."""

    @abstractmethod
    def parse(self, pdf_path: Path) -> Document:
        """
        Parse a PDF file and return structured document.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            Parsed Document with hierarchical structure
        """
        pass

    @abstractmethod
    def validate_pdf(self, pdf_path: Path) -> bool:
        """
        Validate if the file is a readable PDF.

        Args:
            pdf_path: Path to the PDF file

        Returns:
            True if valid, False otherwise
        """
        pass

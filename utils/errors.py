"""
Custom exceptions with user-friendly messages.
"""


class TaxCalcError(Exception):
    """Base exception for all tax calculator errors."""

    def __init__(self, title: str, message: str, suggestion: str = None):
        self.title = title
        self.message = message
        self.suggestion = suggestion or "Please try again or contact support."
        super().__init__(self.message)

    def to_dict(self):
        return {
            "title": self.title,
            "message": self.message,
            "suggestion": self.suggestion,
        }


class PDFParsingError(TaxCalcError):
    """Raised when PDF cannot be parsed."""

    def __init__(self, filename: str, reason: str):
        super().__init__(
            title="Cannot Read PDF",
            message=f"File '{filename}' could not be read: {reason}",
            suggestion="Check that the file is a valid N26 PDF and not corrupted.",
        )


class OCRError(TaxCalcError):
    """Raised when OCR fails."""

    def __init__(self, filename: str):
        super().__init__(
            title="OCR Failed",
            message=f"Could not extract text from '{filename}'.",
            suggestion="This might be a scanned or unusual PDF. Try re-downloading from N26.",
        )


class CoordinateExtractionError(TaxCalcError):
    """Raised when expected data not found at expected coordinates."""

    def __init__(self, filename: str, field: str):
        super().__init__(
            title="Data Not Found",
            message=f"Could not find '{field}' in '{filename}'.",
            suggestion="This might be a different N26 document format. Check the document is a transaction or dividend statement.",
        )


class NonEURError(TaxCalcError):
    """Raised when non-EUR transaction detected."""

    def __init__(self, filename: str):
        super().__init__(
            title="Non-EUR Transaction",
            message=f"Document '{filename}' contains a non-EUR transaction.",
            suggestion="This tool only supports EUR transactions. Exclude this file or ensure all transactions are in EUR.",
        )


class NoValidDocumentsError(TaxCalcError):
    """Raised when no valid documents found."""

    def __init__(self, count: int):
        super().__init__(
            title="No Valid Documents Found",
            message=f"Uploaded {count} files but none matched N26 document patterns.",
            suggestion="Files should be named: buy_order_*.pdf, sell_order_*.pdf, or income_distribution_*.pdf",
        )

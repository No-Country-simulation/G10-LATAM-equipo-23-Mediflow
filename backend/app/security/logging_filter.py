"""Redact credentials and common personal identifiers before log handlers emit."""

import logging
import re


class SensitiveDataFilter(logging.Filter):
    """Redact secret-like values from rendered log messages and arguments."""

    PATTERNS = (
        re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*"),
        re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        re.compile(
            r"(?i)\b(?:access[_-]?token|refresh[_-]?token|api[_-]?key|"
            r"password|senha|authorization)\s*[:=]\s*[^,\s;&]+"
        ),
        re.compile(r"\b(?:gsk_[A-Za-z0-9_-]{12,}|sk-[A-Za-z0-9_-]{12,})\b"),
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        re.compile(
            r"(?i)\b(?:cpf|nif|niss|bi|identifica[cç][aã]o)\s*[:#-]?\s*"
            r"[A-Z0-9./-]{5,24}\b"
        ),
        re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b\d{9}[A-Z]{2}\d{3}\b"),
        re.compile(
            r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,3}\)|\d{2,3})"
            r"[\s.-]?\d{3,5}[\s.-]\d{3,4}(?!\w)"
        ),
        re.compile(
            r"(?i)\b(?:paciente|nome\s+do\s+paciente|utente)\s*[:=]\s*"
            r"[^,\n;|]{2,100}"
        ),
    )

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for pattern in self.PATTERNS:
            message = pattern.sub("[REDACTED]", message)
        record.msg = message
        record.args = ()
        return True


def install_sensitive_data_filter() -> None:
    """Install one redaction filter on configured root and application handlers."""
    root = logging.getLogger()
    if any(isinstance(item, SensitiveDataFilter) for item in root.filters):
        return
    redactor = SensitiveDataFilter()
    root.addFilter(redactor)
    loggers = [root]
    loggers.extend(
        logger
        for logger in logging.Logger.manager.loggerDict.values()
        if isinstance(logger, logging.Logger)
    )
    for logger in loggers:
        logger.addFilter(redactor)
        for handler in logger.handlers:
            handler.addFilter(redactor)
    if logging.lastResort is not None:
        logging.lastResort.addFilter(redactor)

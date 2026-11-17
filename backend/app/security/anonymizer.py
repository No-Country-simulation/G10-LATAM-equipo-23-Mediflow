"""Local Regex + NER masking for personally identifying document content."""

import os
import re
from functools import lru_cache
from typing import Any


class PrivacyPipelineError(RuntimeError):
    """Raised when the required local PII detection pipeline is unavailable."""


@lru_cache(maxsize=2)
def _load_ner(model_name: str) -> Any:
    """Load the local spaCy model when it is installed."""
    try:
        import spacy

        return spacy.load(model_name, exclude=["parser", "lemmatizer"])
    except (ImportError, OSError) as exc:
        raise PrivacyPipelineError(
            "O modelo NER local não está disponível. Instale as dependências "
            "e o modelo indicado por MEDIFLOW_NER_MODEL."
        ) from exc


class ClinicalDataAnonymizer:
    """Replace detected identifiers with reversible, request-scoped tokens."""

    PATTERNS = (
        (
            "PACIENTE",
            re.compile(
                r"(?i)\b(?:paciente|nome\s+do\s+paciente|nome\s+do\s+utente|"
                r"utente|patient)\s*[:#-]\s*"
                r"(?P<value>[^\n,;|]{2,100}?)"
                r"(?=\s*(?:[,;|\n]|$|\b(?:nasc(?:imento)?|idade|sexo|cpf|nif)\b))"
            ),
            "value",
        ),
        (
            "IDENTIFICACAO",
            re.compile(
                r"(?i)\b(?:cpf|nif|niss|bi|bilhete\s+de\s+identidade|"
                r"n[uú]mero\s+de\s+utente|cart[aã]o\s+de\s+utente|"
                r"id\s+(?:do\s+)?paciente|"
                r"cart[aã]o\s+de\s+cidad[aã]o|passaporte|documento\s+de\s+"
                r"identifica[cç][aã]o|n[uú]mero\s+de\s+identifica[cç][aã]o|"
                r"identification\s+(?:number|no\.?))\s*(?:n[º°.]?\s*)?[:#-]?\s*"
                r"(?P<value>[A-Z0-9][A-Z0-9./-]{3,23})"
            ),
            "value",
        ),
        (
            "IDENTIFICACAO",
            re.compile(
                r"(?P<value>\b\d{3}\.\d{3}\.\d{3}-\d{2}\b"
                r"|\b\d{9}[A-Z]{2}\d{3}\b"
                r"|\b\d{9,14}\b)"
            ),
            "value",
        ),
        (
            "EMAIL",
            re.compile(
                r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE
            ),
            None,
        ),
        (
            "TELEFONE",
            re.compile(
                r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{2,3}\)|\d{2,3})"
                r"[\s.-]?\d{3,5}[\s.-]\d{3,4}(?!\w)"
            ),
            None,
        ),
        (
            "DATA",
            re.compile(
                r"(?<!\d)(?:"
                r"\d{4}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01])"
                r"|(?:0?[1-9]|[12]\d|3[01])[-/.](?:0?[1-9]|1[0-2])"
                r"[-/.](?:\d{2}|\d{4})"
                r")(?!\d)"
            ),
            None,
        ),
        (
            "MORADA",
            re.compile(
                r"(?i)\b(?:morada|endereço|endereco|address|residência|residencia)"
                r"\s*[:#-]\s*(?P<value>[^\n;|]{4,160}?)"
                r"(?=\s*(?:[;|\n]|$))"
            ),
            "value",
        ),
    )

    def __init__(self, ner_model: str | None = None) -> None:
        self.ner_model = ner_model or os.getenv(
            "MEDIFLOW_NER_MODEL", "pt_core_news_sm"
        )

    def anonymize_text(self, text: str) -> tuple[str, dict[str, str]]:
        """Mask Regex and locally recognized person spans, returning a local map."""
        if not isinstance(text, str):
            raise TypeError("O texto a anonimizar deve ser uma string.")

        spans: list[tuple[int, int, str]] = []
        for entity_type, pattern, group_name in self.PATTERNS:
            for match in pattern.finditer(text):
                start, end = match.span(group_name) if group_name else match.span()
                if start < end:
                    spans.append((start, end, entity_type))

        try:
            entities = _load_ner(self.ner_model)(text).ents
        except PrivacyPipelineError:
            entities = ()
        except Exception:
            entities = ()
        for entity in entities:
            if (
                entity.label_ in {"PERSON", "PER"}
                and entity.start_char < entity.end_char
            ):
                spans.append((entity.start_char, entity.end_char, "PACIENTE"))

        # Prefer specific, longer detections when recognizers overlap.
        spans.sort(key=lambda span: (span[0], -(span[1] - span[0]), span[2]))
        selected: list[tuple[int, int, str]] = []
        for span in spans:
            if selected and span[0] < selected[-1][1]:
                continue
            selected.append(span)

        mapping: dict[str, str] = {}
        token_by_value: dict[tuple[str, str], str] = {}
        counters: dict[str, int] = {}
        pieces: list[str] = []
        cursor = 0
        for start, end, entity_type in selected:
            original = text[start:end]
            identity = (entity_type, original)
            token = token_by_value.get(identity)
            if token is None:
                counters[entity_type] = counters.get(entity_type, 0) + 1
                token = f"[{entity_type}_{counters[entity_type]:02d}]"
                token_by_value[identity] = token
                mapping[token] = original
            pieces.extend((text[cursor:start], token))
            cursor = end
        pieces.append(text[cursor:])
        return "".join(pieces), mapping

    @staticmethod
    def deanonymize_text(text: str, mapping_registry: dict[str, str]) -> str:
        """Restore tokens only in the current request's explicitly chosen output."""
        restored = text
        for placeholder, original_value in mapping_registry.items():
            restored = restored.replace(placeholder, original_value)
        return restored

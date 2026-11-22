"""Fail-closed input and schema validation for the external language model."""

import re
import unicodedata
from typing import NamedTuple

from pydantic import ValidationError

from app.schemas.schemas import DocumentoExtraido


class GuardrailVerdict(NamedTuple):
    is_safe: bool
    risk_score: float
    reason: str


class PromptGuardrail:
    """Detect common direct/indirect prompt attacks and enforce output schema."""

    MAX_INPUT_CHARS = 20_000
    MAX_OUTPUT_CHARS = 30_000
    SUSPICIOUS_PATTERNS = (
        (
            re.compile(
                r"\bignore\s+(?:all\s+)?(?:previous|prior|above|system)\s+"
                r"(?:instructions?|prompts?|rules?)\b",
                re.IGNORECASE,
            ),
            0.99,
            "Tentativa de substituir instruções do sistema",
        ),
        (
            re.compile(
                r"\b(?:ignore|desconsidere|ignora|ignorar)\b.{0,80}\b"
                r"(?:instru[cç][oõ]es|regras|prompt|seguran[cç]a)\b",
                re.IGNORECASE,
            ),
            0.95,
            "Tentativa de injeção de prompt",
        ),
        (
            re.compile(
                r"\b(?:reveal|show|print|repeat|exiba|mostre|revele)\b.{0,80}"
                r"\b(?:system\s+prompt|instru[cç][oõ]es?\s+(?:do\s+)?sistema|"
                r"chave\s+secreta|api[_ -]?key)\b",
                re.IGNORECASE,
            ),
            0.95,
            "Tentativa de extração de instruções ou segredos",
        ),
        (
            re.compile(
                r"\b(?:you\s+are\s+now|act\s+as|aja\s+como|finja\s+ser)\b",
                re.IGNORECASE,
            ),
            0.90,
            "Tentativa de alterar a função do agente",
        ),
        (
            re.compile(
                r"\b(?:bypass|disable|desativar|contornar)\b.{0,60}\b"
                r"(?:safety|security|guardrail|seguran[cç]a|prote[cç][aã]o)\b",
                re.IGNORECASE,
            ),
            0.95,
            "Tentativa de contornar salvaguardas",
        ),
        (
            re.compile(
                r"\[(?:SYSTEM|ADMIN|DEVELOPER)\]|<\|(?:im_start|im_sep|"
                r"im_end|fim_prefix|ghissue)\|>|```(?:system|assistant)\b",
                re.IGNORECASE,
            ),
            0.99,
            "Marcador de controlo de modelo detetado",
        ),
        (
            re.compile(r"\b(?:eval|exec)\s*\(", re.IGNORECASE),
            0.85,
            "Instrução de execução de código detetada",
        ),
    )

    @staticmethod
    def _normalize(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        return "".join(
            character
            for character in normalized
            if character not in {"\u200b", "\u200c", "\u200d", "\ufeff"}
        )

    def validate_input(self, input_text: str) -> GuardrailVerdict:
        """Validate bounded extracted text before it reaches any model request."""
        if not isinstance(input_text, str):
            return GuardrailVerdict(False, 1.0, "O conteúdo extraído não é texto.")
        clean_text = self._normalize(input_text).strip()
        if not clean_text:
            return GuardrailVerdict(False, 1.0, "O conteúdo extraído está vazio.")
        if len(clean_text) > self.MAX_INPUT_CHARS:
            return GuardrailVerdict(False, 1.0, "O documento excede o limite permitido.")
        if any(
            ord(character) < 32 and character not in "\n\r\t"
            for character in clean_text
        ):
            return GuardrailVerdict(
                False, 0.9, "O documento contém caracteres de controlo inválidos."
            )

        for pattern, score, reason in self.SUSPICIOUS_PATTERNS:
            if pattern.search(clean_text):
                return GuardrailVerdict(False, score, reason)

        return GuardrailVerdict(True, 0.0, "Entrada validada.")

    def validate_output(
        self, output_text: str
    ) -> tuple[GuardrailVerdict, DocumentoExtraido | None]:
        """Parse and reject output outside the strict application schema."""
        if not isinstance(output_text, str) or not output_text.strip():
            return GuardrailVerdict(False, 1.0, "O agente retornou conteúdo vazio."), None
        if len(output_text) > self.MAX_OUTPUT_CHARS:
            return GuardrailVerdict(False, 1.0, "A resposta excede o limite permitido."), None

        try:
            document = DocumentoExtraido.model_validate_json(output_text)
        except ValidationError:
            return (
                GuardrailVerdict(
                    False,
                    1.0,
                    "A resposta do agente não corresponde ao esquema esperado.",
                ),
                None,
            )

        for value in document.model_dump().values():
            strings = value if isinstance(value, list) else [value]
            for item in strings:
                if isinstance(item, dict):
                    strings.extend(item.values())
                elif isinstance(item, str):
                    verdict = self.validate_input(item)
                    if not verdict.is_safe:
                        return (
                            GuardrailVerdict(
                                False,
                                verdict.risk_score,
                                "A resposta contém conteúdo inseguro.",
                            ),
                            None,
                        )

        return GuardrailVerdict(True, 0.0, "Saída validada pelo esquema."), document

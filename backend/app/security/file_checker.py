"""Validate upload size, true signatures, and document active content."""

from io import BytesIO
from typing import Tuple

import pymupdf
from PIL import Image, UnidentifiedImageError


class SecureFileValidator:
    """Allow only bounded, parseable document formats without active content."""

    MAGIC_BYTES = {
        "pdf": b"%PDF",
        "png": b"\x89PNG\r\n\x1a\n",
        "jpeg": b"\xff\xd8\xff",
    }

    ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg"}
    TEXT_EXTENSIONS = {"txt", "json"}
    MAX_FILE_SIZE_MB = 10
    PDF_ACTIVE_CONTENT = (
        b"/javascript",
        b"/js",
        b"/openaction",
        b"/aa",
        b"/launch",
        b"/embeddedfiles",
        b"/filespec",
        b"/af",
        b"/ef",
        b"/xfa",
        b"/richmedia",
        b"/gotor",
        b"/gotoe",
        b"/movie",
        b"/sound",
        b"/3d",
        b"/submitform",
        b"/importdata",
    )

    @classmethod
    def validate_upload(cls, filename: str, file_bytes: bytes) -> Tuple[bool, str]:
        if not isinstance(file_bytes, bytes) or not file_bytes:
            return False, "O arquivo está vazio ou não contém bytes válidos."

        if len(file_bytes) > cls.MAX_FILE_SIZE_MB * 1024 * 1024:
            return False, (
                f"Arquivo excede o tamanho máximo permitido "
                f"({cls.MAX_FILE_SIZE_MB} MB)."
            )

        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in cls.ALLOWED_EXTENSIONS | cls.TEXT_EXTENSIONS:
            return False, f"Extensão de arquivo não permitida: '.{ext}'"

        if ext in cls.TEXT_EXTENSIONS:
            try:
                text = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                return False, "Arquivo de texto não está codificado em UTF-8."
            if "\x00" in text:
                return False, "Arquivo de texto contém bytes nulos."
            return True, "Arquivo de texto validado com sucesso."

        expected_magic = cls.MAGIC_BYTES["jpeg"] if ext in {"jpg", "jpeg"} else cls.MAGIC_BYTES[ext]
        if not file_bytes.startswith(expected_magic):
            return False, "Assinatura do arquivo (Magic Bytes) incompatível com a extensão informada. Upload rejeitado por segurança."

        if ext == "pdf":
            return cls._validate_pdf(file_bytes)

        if ext in {"png", "jpg", "jpeg"}:
            try:
                with Image.open(BytesIO(file_bytes)) as image:
                    if image.width * image.height > 40_000_000:
                        return False, "Imagem excede o limite de 40 megapixels."
                    actual_format = image.format
                    if (ext == "png" and actual_format != "PNG") or (
                        ext in {"jpg", "jpeg"} and actual_format != "JPEG"
                    ):
                        return False, "O formato real da imagem não corresponde à extensão."
                    image.verify()
            except Image.DecompressionBombError:
                return False, "Imagem excede o limite de pixels permitido."
            except (UnidentifiedImageError, OSError):
                return False, "A imagem está corrompida ou em formato inválido."

        return True, "Arquivo validado com sucesso."

    @classmethod
    def _validate_pdf(cls, file_bytes: bytes) -> Tuple[bool, str]:
        """Parse all PDF objects and reject JavaScript, actions, and attachments."""
        try:
            with pymupdf.open(stream=file_bytes, filetype="pdf") as document:
                if document.is_encrypted or document.is_repaired:
                    return False, "PDF cifrado ou estruturalmente inválido."
                for xref in range(1, document.xref_length()):
                    object_text = document.xref_object(xref, compressed=False)
                    normalized = object_text.lower().encode("latin-1", errors="ignore")
                    if any(marker in normalized for marker in cls.PDF_ACTIVE_CONTENT):
                        return False, (
                            "PDF contém JavaScript, ações automáticas ou anexos "
                            "ativos e foi rejeitado."
                        )
                if document.embfile_count():
                    return False, "PDF com ficheiros incorporados não é permitido."
        except (pymupdf.FileDataError, RuntimeError, ValueError):
            return False, "Não foi possível validar a estrutura do PDF."
        return True, "PDF validado e sem conteúdo ativo conhecido."
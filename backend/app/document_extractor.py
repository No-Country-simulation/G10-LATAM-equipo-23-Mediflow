"""Bounded local text extraction and OCR for supported clinical document uploads."""

from io import BytesIO
import os
from pathlib import Path

import pymupdf
import pytesseract
from PIL import Image, UnidentifiedImageError

from app.security.anonymizer import ClinicalDataAnonymizer

MAX_PDF_PAGES = 10
MAX_IMAGE_PIXELS = 40_000_000
MAX_EXTRACTED_TEXT_CHARS = 20_000
_USER_OCR_ROOT = Path.home() / ".local" / "opt" / "mediflow-ocr" / "usr"
_USER_TESSERACT = _USER_OCR_ROOT / "bin" / "tesseract"
_USER_TESSDATA = _USER_OCR_ROOT / "share" / "tesseract-ocr" / "5" / "tessdata"

if _USER_TESSERACT.is_file():
    pytesseract.pytesseract.tesseract_cmd = str(_USER_TESSERACT)
    os.environ["TESSDATA_PREFIX"] = str(_USER_TESSDATA)
    native_libraries = str(_USER_OCR_ROOT / "lib" / "x86_64-linux-gnu")
    existing_libraries = os.environ.get("LD_LIBRARY_PATH")
    os.environ["LD_LIBRARY_PATH"] = (
        f"{native_libraries}:{existing_libraries}"
        if existing_libraries
        else native_libraries
    )


class OCRConfigurationError(RuntimeError):
    pass


class DocumentExtractionError(ValueError):
    pass


def _ocr_image(image: Image.Image) -> str:
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise DocumentExtractionError(
            "A imagem excede o limite de 40 megapixels."
        )
    try:
        text = pytesseract.image_to_string(
            image.convert("RGB"),
            lang="por+eng",
            timeout=30,
        )
    except pytesseract.TesseractNotFoundError as exc:
        raise OCRConfigurationError(
            "O OCR local não está instalado. Instale o Tesseract com os idiomas "
            "português e inglês."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise OCRConfigurationError(
            "O Tesseract não conseguiu iniciar. Confira a instalação e os idiomas "
            "português e inglês."
        ) from exc
    except RuntimeError as exc:
        raise DocumentExtractionError(
            "O OCR não conseguiu processar a imagem dentro do limite de tempo."
        ) from exc
    return text.strip()


def extract_document_text(filename: str, content: bytes) -> str:
    """Extract text locally; callers must mask it before any external processing."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension in {"txt", "json"}:
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentExtractionError(
                "O arquivo de texto não está codificado em UTF-8."
            ) from exc
    elif extension == "pdf":
        text = _extract_pdf_text(content)
    elif extension in {"jpg", "jpeg", "png"}:
        try:
            with Image.open(BytesIO(content)) as image:
                image.load()
                text = _ocr_image(image)
        except UnidentifiedImageError as exc:
            raise DocumentExtractionError(
                "Não foi possível decodificar a imagem enviada."
            ) from exc
        except Image.DecompressionBombError as exc:
            raise DocumentExtractionError(
                "A imagem excede o limite de pixels permitido."
            ) from exc
        except OSError as exc:
            raise DocumentExtractionError(
                "A imagem está corrompida ou em formato inválido."
            ) from exc
    else:
        raise DocumentExtractionError("Formato de arquivo não suportado.")

    text = text.strip()
    if not text:
        raise DocumentExtractionError(
            "Não foi possível extrair texto legível deste documento."
        )
    if len(text) > MAX_EXTRACTED_TEXT_CHARS:
        raise DocumentExtractionError(
            f"O documento excede o limite de {MAX_EXTRACTED_TEXT_CHARS} caracteres "
            "após a extração."
        )
    return text


def extract_and_anonymize_document_text(
    filename: str, content: bytes
) -> tuple[str, dict[str, str]]:
    """Extrair localmente e aplicar regex com NER local opcional antes de devolver."""
    extracted_text = extract_document_text(filename, content)
    return ClinicalDataAnonymizer().anonymize_text(extracted_text)


def _extract_pdf_text(content: bytes) -> str:
    """Use embedded PDF text first, then render sparse pages for local OCR."""
    try:
        with pymupdf.open(stream=content, filetype="pdf") as document:
            if document.page_count > MAX_PDF_PAGES:
                raise DocumentExtractionError(
                    f"O PDF excede o limite de {MAX_PDF_PAGES} páginas."
                )
            pages = []
            for page in document:
                page_text = page.get_text("text").strip()
                if len(page_text) < 20:
                    scale = 1.5
                    rendered_pixels = (
                        page.rect.width * scale * page.rect.height * scale
                    )
                    if rendered_pixels > MAX_IMAGE_PIXELS:
                        scale *= (MAX_IMAGE_PIXELS / rendered_pixels) ** 0.5
                    pixmap = page.get_pixmap(
                        matrix=pymupdf.Matrix(scale, scale), alpha=False
                    )
                    with Image.open(BytesIO(pixmap.tobytes("png"))) as image:
                        page_text = _ocr_image(image)
                if page_text:
                    pages.append(page_text)
            return "\n\n".join(pages)
    except DocumentExtractionError:
        raise
    except (pymupdf.FileDataError, RuntimeError) as exc:
        raise DocumentExtractionError(
            "Não foi possível abrir ou ler o PDF enviado."
        ) from exc

from typing import Literal
from pydantic import BaseModel


class DocumentoEntrada(BaseModel):
    """Corpo do POST /triagem (JSON/texto), igual ao exemplo do edital."""
    documento_id: str
    tipo_arquivo: Literal["PDF", "IMAGEM", "JSON", "TEXTO"]
    documento_texto: str | None = None
    canal_origem: str | None = None


class DocumentoIngerido(BaseModel):
    """Contrato entre a ingestão (sua colega) e o agente."""
    documento_id: str
    nome_original: str | None = None
    tipo_arquivo: Literal["PDF", "IMAGEM", "JSON", "TEXTO"]
    metodo_ingestao: Literal["texto_direto", "pdf_texto", "pdf_imagem", "imagem"]
    texto: str | None = None             # caminhos de texto
    imagens: list[bytes] | None = None   # caminhos multimodais
    canal_origem: str | None = None
    erro: str | None = None              # arquivo ilegível, corrompido etc.
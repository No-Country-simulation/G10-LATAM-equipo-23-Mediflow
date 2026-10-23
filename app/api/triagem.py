from fastapi import APIRouter

from app.agent.provisorio import triar  # trocar pelo agente real depois
from app.models import (
    DecisaoRoteamento,
    Destino,
    DocumentoEntrada,
    DocumentoIngerido,
    RespostaTriagem,
)

router = APIRouter(tags=["triagem"])


@router.post("/triagem", response_model=RespostaTriagem)
def triagem(entrada: DocumentoEntrada) -> RespostaTriagem:
    doc = DocumentoIngerido(
        documento_id=entrada.documento_id,
        tipo_arquivo=entrada.tipo_arquivo,
        metodo_ingestao="texto_direto",
        texto=entrada.documento_texto,
        canal_origem=entrada.canal_origem,
        erro=None if entrada.documento_texto else "documento_texto ausente",
    )
    try:
        return triar(doc)
    except Exception:
        # Qualquer falha cai em revisão humana, nunca em erro 500 silencioso
        return RespostaTriagem(
            status="revisao_humana",
            documento_id=entrada.documento_id,
            decisao_roteamento=DecisaoRoteamento(
                destino_principal=Destino.REVISAO_HUMANA,
                requer_auditoria_humana=True,
                justificativa_roteamento="Falha interna durante a triagem.",
            ),
        )
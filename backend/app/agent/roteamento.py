"""Regras de encaminhamento que mantêm a revisão humana no centro do fluxo."""

from app.schemas.schemas import DocumentoExtraido

LIMITE_CONFIANCA = 0.80

def rotear(doc: DocumentoExtraido) -> dict:
    """Retain model suggestions, but never let model output bypass human review."""
    c = doc.classificacao

    duvida = (
        c.score_confianca < LIMITE_CONFIANCA
        or c.tipo_documento == "Desconhecido"
        or c.nivel_prioridade == "Indefinido"
        or len(doc.campos_ilegiveis) > 0
    )

    # Urgency from the model highlights a queue; it is not a clinical decision.
    if c.nivel_prioridade == "Urgente":
        return {
            "destino_principal": "Fila_Emergencia_Medica",
            "requer_auditoria_humana": True,
            "justificativa_roteamento": (
                "Prioridade sugerida como urgente: requer confirmação humana imediata."
            ),
        }

    return {
        "destino_principal": "Auditoria_Humana",
        "requer_auditoria_humana": True,
        "justificativa_roteamento": (
            "Toda extração assistida por IA exige revisão humana antes de qualquer "
            "processamento; confira também a baixa confiança ou os campos ilegíveis."
            if duvida
            else "A extração é uma sugestão da IA e exige revisão humana antes de uso."
        ),
    }

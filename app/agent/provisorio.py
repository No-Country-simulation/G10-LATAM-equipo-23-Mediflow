import unicodedata

from app.models import (
    Classificacao,
    DecisaoRoteamento,
    Destino,
    DocumentoIngerido,
    NivelPrioridade,
    Notificacao,
    RespostaTriagem,
    TipoDocumento,
)

# Rede de segurança determinística (versão mínima; será ampliada no Passo 7)
PALAVRAS_URGENCIA = [
    "tep agudo",
    "embolia pulmonar",
    "correlacao clinica urgente",
    "infarto agudo",
]
TAMANHO_MINIMO_TEXTO = 30


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def _revisao_humana(doc: DocumentoIngerido, motivo: str) -> RespostaTriagem:
    return RespostaTriagem(
        status="revisao_humana",
        documento_id=doc.documento_id,
        metodo_ingestao=doc.metodo_ingestao,
        decisao_roteamento=DecisaoRoteamento(
            destino_principal=Destino.REVISAO_HUMANA,
            requer_auditoria_humana=True,
            justificativa_roteamento=motivo,
        ),
    )


def triar(doc: DocumentoIngerido) -> RespostaTriagem:
    """PROVISÓRIO: será substituído pelo grafo do agente real."""
    if doc.erro:
        return _revisao_humana(doc, f"Falha na ingestão: {doc.erro}")

    if not doc.texto or len(doc.texto.strip()) < TAMANHO_MINIMO_TEXTO:
        return _revisao_humana(doc, "Texto ausente ou insuficiente para análise.")

    texto = _normalizar(doc.texto)

    if "ilegivel" in texto:
        return _revisao_humana(doc, "Documento com trechos ilegíveis.")

    urgente = any(p in texto for p in PALAVRAS_URGENCIA)

    classificacao = Classificacao(
        tipo_documento=TipoDocumento.INDEFINIDO,
        nivel_prioridade=NivelPrioridade.URGENTE if urgente else NivelPrioridade.ROTINA,
        score_confianca_classificacao=0.5,  # valor fixo provisório
    )

    if urgente:
        decisao = DecisaoRoteamento(
            destino_principal=Destino.EMERGENCIA,
            requer_auditoria_humana=False,
            justificativa_roteamento="Termo de urgência detectado no texto.",
            notificacao_gerada=Notificacao(
                canal="Alerta_Plantao_Medico",
                mensagem=f"ALERTA URGENTE: documento {doc.documento_id} requer atenção imediata.",
            ),
        )
    else:
        decisao = DecisaoRoteamento(
            destino_principal=Destino.PRONTUARIO,
            requer_auditoria_humana=False,
            justificativa_roteamento="Documento de rotina, sem sinais de urgência.",
        )

    return RespostaTriagem(
        status="processado",
        documento_id=doc.documento_id,
        metodo_ingestao=doc.metodo_ingestao,
        classificacao=classificacao,
        decisao_roteamento=decisao,
    )
from app.models import (
    RespostaTriagem,
    Classificacao,
    DadosExtraidos,
    DecisaoRoteamento,
    TipoDocumento,
    NivelPrioridade,
    Destino,
)


def test_resposta_exemplo_do_edital():
    resposta = RespostaTriagem(
        status="processado",
        documento_id="DOC-CLIN-2026-8942",
        classificacao=Classificacao(
            tipo_documento=TipoDocumento.LAUDO_IMAGEM,
            especialidade="Radiologia / Pneumologia",
            nivel_prioridade=NivelPrioridade.URGENTE,
            score_confianca_classificacao=0.99,
        ),
        dados_extraidos=DadosExtraidos(),
        decisao_roteamento=DecisaoRoteamento(
            destino_principal=Destino.EMERGENCIA,
            requer_auditoria_humana=False,
            justificativa_roteamento="Achado critico de alta gravidade.",
        ),
    )
    assert resposta.decisao_roteamento.destino_principal.value == "Fila_Emergencia_Medica"
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _enviar(documento_id: str, texto: str | None, canal: str = "Ambulatorio"):
    return client.post(
        "/triagem",
        json={
            "documento_id": documento_id,
            "tipo_arquivo": "PDF",
            "documento_texto": texto,
            "canal_origem": canal,
        },
    )


def test_rotina():
    r = _enviar(
        "DOC-ROTINA-1",
        "Receita: paciente Maria Souza, 40 anos. Dipirona 500 mg a cada 6 horas por 3 dias. Dra. Ana CRM-SP 123456.",
    )
    corpo = r.json()
    assert r.status_code == 200
    assert corpo["status"] == "processado"
    assert corpo["decisao_roteamento"]["requer_auditoria_humana"] is False
    assert corpo["classificacao"]["nivel_prioridade"] == "Rotina"


def test_urgencia():
    r = _enviar(
        "DOC-CLIN-2026-8942",
        "HOSPITAL SANTA LUCIA - LAUDO. Paciente: Carlos Eduardo Mendes, 52 anos. "
        "Conclusao: Quadro compativel com Tromboembolismo Pulmonar. TEP agudo. "
        "Sugere-se correlacao clinica urgente.",
        canal="Pronto_Socorro",
    )
    corpo = r.json()
    assert corpo["decisao_roteamento"]["destino_principal"] == "Fila_Emergencia_Medica"
    assert corpo["decisao_roteamento"]["notificacao_gerada"] is not None


def test_ambiguo_vai_para_revisao_humana():
    r = _enviar("DOC-AMBIGUO-1", "Receita manuscrita com medicamento ilegivel e dose nao identificada.")
    corpo = r.json()
    assert corpo["status"] == "revisao_humana"
    assert corpo["decisao_roteamento"]["requer_auditoria_humana"] is True


def test_sem_texto_vai_para_revisao_humana():
    r = _enviar("DOC-VAZIO-1", None)
    assert r.status_code == 200
    assert r.json()["decisao_roteamento"]["destino_principal"] == "Revisao_Humana"
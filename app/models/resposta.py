from pydantic import BaseModel, Field
from app.models.enums import TipoDocumento, NivelPrioridade, Destino
from app.models.extracao import DadosExtraidos


class Classificacao(BaseModel):
    tipo_documento: TipoDocumento
    especialidade: str | None = None
    nivel_prioridade: NivelPrioridade
    score_confianca_classificacao: float = Field(ge=0.0, le=1.0)


class Notificacao(BaseModel):
    canal: str
    mensagem: str


class DecisaoRoteamento(BaseModel):
    destino_principal: Destino
    requer_auditoria_humana: bool
    justificativa_roteamento: str
    notificacao_gerada: Notificacao | None = None


class ArmazenamentoOCI(BaseModel):
    bucket: str
    caminho_objeto: str
    status_backup: str


class RespostaTriagem(BaseModel):
    status: str
    documento_id: str
    metodo_ingestao: str | None = None
    classificacao: Classificacao | None = None
    dados_extraidos: DadosExtraidos | None = None
    score_confianca_final: float | None = Field(default=None, ge=0.0, le=1.0)
    decisao_roteamento: DecisaoRoteamento | None = None
    armazenamento_oci: ArmazenamentoOCI | None = None
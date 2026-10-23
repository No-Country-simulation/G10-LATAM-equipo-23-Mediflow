from pydantic import BaseModel, Field


class Paciente(BaseModel):
    nome: str | None = None
    idade: int | None = Field(default=None, ge=0, le=130)


class MedicoSolicitante(BaseModel):
    nome: str | None = None
    crm: str | None = None  # formato final "145892-SP"; validado no Passo 6


class Medicamento(BaseModel):
    nome: str | None = None
    dosagem: str | None = None
    via: str | None = None
    frequencia: str | None = None
    duracao: str | None = None


class DadosExtraidos(BaseModel):
    paciente: Paciente = Field(default_factory=Paciente)
    medico_solicitante: MedicoSolicitante = Field(default_factory=MedicoSolicitante)
    exame_realizado: str | None = None
    exames_solicitados: list[str] = Field(default_factory=list)
    medicamentos: list[Medicamento] = Field(default_factory=list)
    diagnostico_principal: str | None = None
    cid_sugerido: str | None = None
    achados: str | None = None
    conclusao: str | None = None
    campos_ilegiveis: list[str] = Field(default_factory=list)
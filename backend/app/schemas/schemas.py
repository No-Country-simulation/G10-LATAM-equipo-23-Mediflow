"""Pydantic contracts shared by extraction, validation, and UI responses."""

from typing import Optional, Literal

from pydantic import BaseModel, ConfigDict, Field

class Paciente(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    nome: Optional[str] = None
    idade: Optional[int] = None

class Medico(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    nome: Optional[str] = None
    crm: Optional[str] = None

class Medicamento(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    nome: str
    dosagem: Optional[str] = None
    posologia: Optional[str] = None

class Classificacao(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    tipo_documento: Literal[
        "Receituario", "Laudo Laboratorial", "Laudo de Imagem",
        "Guia de Procedimento", "Relatorio de Alta", "Atestado", "Desconhecido"
    ]
    nivel_prioridade: Literal["Rotina", "Urgente", "Indefinido"]
    score_confianca: float = Field(ge=0, le=1)
    especialidade_sugerida: Optional[str] = None

class DocumentoExtraido(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    classificacao: Classificacao
    paciente: Paciente = Field(default_factory=Paciente)
    medico_solicitante: Medico = Field(default_factory=Medico)
    diagnostico_principal: Optional[str] = None
    cid_sugerido: Optional[str] = None
    medicamentos: list[Medicamento] = Field(default_factory=list)
    exames_solicitados: list[str] = Field(default_factory=list)
    campos_ilegiveis: list[str] = Field(default_factory=list)
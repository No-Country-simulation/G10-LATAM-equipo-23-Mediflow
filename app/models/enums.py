from enum import Enum


class TipoDocumento(str, Enum):
    RECEITUARIO = "Receituário Médico"
    LAUDO_LABORATORIAL = "Laudo de Exame Laboratorial"
    LAUDO_IMAGEM = "Laudo de Exame de Imagem"
    GUIA_PROCEDIMENTO = "Guia de Solicitação de Procedimento"
    RELATORIO_ALTA = "Relatório de Alta/Internação"
    ATESTADO = "Atestado Médico"
    INDEFINIDO = "Indefinido"


class NivelPrioridade(str, Enum):
    URGENTE = "Urgente"
    ALTA = "Alta"
    ROTINA = "Rotina"


class Destino(str, Enum):
    EMERGENCIA = "Fila_Emergencia_Medica"
    AUDITORIA_AUTORIZACOES = "Auditoria_Autorizacoes"
    FARMACIA = "Farmacia_Hospitalar"
    PRONTUARIO = "Prontuario_Eletronico"
    REVISAO_HUMANA = "Revisao_Humana"
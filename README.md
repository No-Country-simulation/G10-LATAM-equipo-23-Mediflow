# 🏥 MediFlow – Agente Autônomo para Triagem, Extração e Roteamento de Documentos Clínicos

> **Hackathon ONE Grupo 10** | Oracle Next Education & Alura  
> **Repositório:** `G10-LATAM-equipo-23-Mediflow`

---

## 📋 Sobre o Projeto

O **MediFlow** é uma solução inteligente baseada em IA Multimodal e Agentes Autônomos desenvolvida para resolver o gargalo do processamento manual de documentos na área da saúde (HealthTech / Gestão Hospitalar)[cite: 1]. 

Diariamente, hospitais e clínicas lidam com milhares de documentos heterogêneos (PDFs digitalizados, imagens de exames/receitas, laudos e guias TISS/TUSS)[cite: 1, 2]. O MediFlow automatiza a **classificação, extração precisa de dados clínicos** e o **roteamento condicional**, reduzindo erros de digitação e acelerando significativamente o atendimento a pacientes e autorizações médicas[cite: 1, 2].

---

## 💡 Principais Funcionalidades

* **Ingestão Multimodal:** Recebe arquivos em PDF, Imagem ou payloads JSON[cite: 1, 2].
* **Classificação Automática:** Identifica o tipo de documento (Receituário, Laudo de Imagem, Guia TISS/TUSS, Relatório de Alta, Atestado)[cite: 1].
* **Extração de Entidades Clínicas:** Extrai dados de identificação do paciente, CRM do profissional, diagnósticos (CID-10), exames, medicamentos, dosagens e grau de urgência com altíssima precisão[cite: 1, 2].
* **Grafo de Decisão Condicional:** Avalia o score de confiança da extração e aplica regras de roteamento dinâmicas[cite: 1, 2].
* **Tratamento de Urgências:** Notifica e roteia imediatamente quadros críticos (ex: Tromboembolismo Pulmonar Agudo) para filas de emergência[cite: 2, 4].
* **Human-in-the-Loop (HitL):** Encaminha automaticamente documentos ambíguos ou com baixa confiança para revisão por auditores humanos[cite: 1, 2].
* **Integração com OCI Object Storage:** Armazena e segrega os documentos e payload JSON por status (`/recebidos`, `/processados`, `/auditoria_humana`) na camada Always Free da Oracle Cloud Infrastructure.

---

## 🏗️ Arquitetura e Fluxo do Agente

```text
               +----------------------------------+
               | Ingestão (PDF / Imagem / JSON)   |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               |  IA Multimodal (LLM / Vision)    |
               | Classificação + Extração JSON   |
               +----------------------------------+
                                |
                                v
               +----------------------------------+
               | Grafo de Decisão (LangGraph/n8n) |
               +----------------------------------+
                 /              |               \
                /               |                \
               v                v                 v
     [ Score Confiança OK ] [ Urgência Médica ] [ Ambíguo / Falha ]
               |                |                 |
               v                v                 v
      +-----------------+ +---------------+ +------------------+
      |  Fila Padrão /  | |   Alerta de   | |   Auditoria      |
      |  Sistema PEP    | |  Plantão/UTI  | |  Humana (HitL)   |
      +-----------------+ +---------------+ +------------------+
               \                |                /
                +---------------+---------------+
                                |
                                v
               +----------------------------------+
               | Integration: OCI Object Storage  |
               |     (Camada Always Free)         |
               +----------------------------------+

# MediFlow — Triagem e Roteamento de Documentos Clínicos

> **Hackathon ONE — Grupo 10** | Oracle Next Education (ONE) e Alura  
> **Repositório:** `G10-LATAM-equipo-23-Mediflow`

## Sobre o projeto

O **MediFlow** é um projeto em desenvolvimento que propõe automatizar etapas do tratamento de documentos clínicos, como a classificação, a extração de informações relevantes e o encaminhamento para o fluxo adequado.

A proposta é ajudar hospitais e clínicas a lidar com documentos de diferentes formatos, reduzindo tarefas manuais e facilitando a organização das informações. Como se trata de uma aplicação relacionada à saúde, qualquer resultado gerado automaticamente deverá ser validado de acordo com as regras do projeto e, quando necessário, encaminhado para revisão humana.

> **Estado atual:** a estrutura inicial do repositório foi criada, incluindo a pasta `app/` e arquivos de configuração e dependências. As funcionalidades descritas como objetivo abaixo não devem ser consideradas concluídas até que estejam implementadas e testadas.

## Objetivos e funcionalidades planejadas

- **Recebimento de documentos:** preparar a aplicação para receber documentos e dados de entrada.
- **Classificação documental:** identificar categorias de documentos, como receitas, laudos, atestados e guias.
- **Extração de informações:** estruturar os dados relevantes encontrados nos documentos.
- **Validação dos dados:** utilizar modelos Pydantic para validar a estrutura e os tipos dos dados recebidos, conforme forem implementados.
- **Roteamento condicional:** encaminhar os documentos de acordo com regras definidas pelo projeto.
- **Revisão humana:** prever um fluxo de revisão para casos ambíguos, incompletos ou que precisem de validação.
- **Armazenamento e integrações:** avaliar integrações futuras, incluindo Oracle Cloud Infrastructure (OCI), se fizerem parte do escopo final.

Esses itens representam os objetivos do projeto; o status de cada funcionalidade deve ser atualizado conforme o desenvolvimento avança.

## Estrutura atual do repositório

```text
.
├── app/              # Código da aplicação
├── .env.example      # Exemplo de variáveis de ambiente
├── .gitignore        # Arquivos e diretórios ignorados pelo Git
├── README.md         # Documentação do projeto
└── requirements.txt  # Dependências Python
```

A estrutura interna de `app/` poderá ser documentada aqui quando os módulos e o ponto de entrada estiverem definidos.

## Tecnologias

- **Python** — linguagem principal do projeto.
- **FastAPI** — framework para construção da API.
- **Pydantic** — validação e estruturação de dados, conforme os modelos forem implementados.
- **Git e GitHub** — versionamento do código e colaboração da equipe.

Outras tecnologias, como ferramentas de orquestração de agentes ou serviços da OCI, devem ser listadas como dependências do projeto somente quando estiverem efetivamente definidas e integradas.

## Como configurar o ambiente

### Pré-requisitos

- Python instalado em uma versão compatível com as dependências do projeto.
- Git.
- Acesso ao repositório.

### 1. Clonar o repositório

```bash
git clone <URL_DO_REPOSITORIO>
cd G10-LATAM-equipo-23-Mediflow
```

Substitua `<URL_DO_REPOSITORIO>` pela URL real do repositório no GitHub.

### 2. Criar e ativar um ambiente virtual

No Windows, usando PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

No macOS ou Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instalar as dependências

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

Consulte o arquivo `.env.example` para identificar as variáveis necessárias. Se a aplicação utilizar um arquivo `.env`, crie-o localmente e preencha os valores apropriados.

**Não envie credenciais, tokens ou outros segredos ao GitHub.** O arquivo `.env` deve permanecer fora do controle de versão.

### 5. Executar a aplicação

O comando de inicialização depende do arquivo que contém a instância do FastAPI. Depois de confirmar o módulo e o nome da variável da aplicação, documente aqui o comando correto. Por exemplo, se existir `app/main.py` com uma instância chamada `app`, o comando será:

```bash
uvicorn app.main:app --reload
```

Nesse exemplo, a documentação interativa da API fica disponível em `http://127.0.0.1:8000/docs`.

## Organização do trabalho no GitHub

O repositório utiliza branches para separar frentes de desenvolvimento:

- `feat/estrutura-inicial` — estrutura e configuração inicial do projeto.
- `feat/modelos-pydantic` — trabalho relacionado aos modelos e à validação de dados.
- `feat/api-triagem` — trabalho relacionado à API de triagem.

Os nomes indicam o foco aparente de cada branch; consulte as Issues e os Pull Requests para verificar o escopo, o andamento e o que já foi concluído.

### Fluxo de contribuição sugerido

1. Crie ou consulte uma Issue para entender a tarefa.
2. Trabalhe na branch correspondente à funcionalidade.
3. Faça commits com mensagens claras e específicas.
4. Abra um Pull Request descrevendo as alterações e como testá-las.
5. Solicite revisão da equipe antes de integrar as mudanças à branch principal.

## Testes e validação

A configuração e a execução da aplicação ainda precisam ser verificadas no ambiente de desenvolvimento. À medida que os testes forem criados, registre nesta seção:

- como executar os testes;
- quais cenários são cobertos;
- eventuais limitações conhecidas.

Não considere uma funcionalidade concluída apenas porque o código foi enviado ao repositório: valide também seu comportamento.

## Segurança e responsabilidade

- Utilize apenas documentos de teste ou dados devidamente autorizados.
- Não publique dados pessoais ou informações clínicas identificáveis em commits, Issues, Pull Requests ou logs.
- Não armazene segredos no repositório.
- Resultados automatizados relacionados a documentos clínicos devem ser tratados com cuidado e não substituem a avaliação de profissionais habilitados.

## Próximas etapas

- [ ] Revisar a estrutura interna de `app/`.
- [ ] Confirmar e documentar o ponto de entrada da aplicação.
- [ ] Validar a instalação das dependências.
- [ ] Testar a inicialização da API.
- [ ] Implementar e testar os modelos de dados.
- [ ] Implementar e testar os endpoints de triagem.
- [ ] Atualizar este README conforme as funcionalidades forem concluídas.

## Equipe e contexto

Projeto desenvolvido no contexto do **Hackathon ONE — Grupo 10**, associado ao Oracle Next Education e à Alura.

"""API autenticada para processamento documental com revisão humana."""

import ipaddress
import json
import logging
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from openai import APIStatusError
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.concurrency import run_in_threadpool

from app.agent.Agente import AgentConfigurationError, extrair
from app.agent.roteamento import rotear
from app.auth.security import (
    DuplicateUserError,
    InvalidRefreshToken,
    REFRESH_TOKEN_TTL_SECONDS,
    auth_is_configured,
    authenticate_user,
    configured_role,
    create_session_tokens,
    get_current_user,
    register_user,
    revoke_refresh_token,
    rotate_refresh_token,
)
from app.auth.setup import configure_login
from app.document_extractor import (
    DocumentExtractionError,
    OCRConfigurationError,
    extract_and_anonymize_document_text,
)
from app.schemas.schemas import DocumentoExtraido
from app.security.anonymizer import ClinicalDataAnonymizer, PrivacyPipelineError
from app.security.file_checker import SecureFileValidator
from app.security.guardrails import PromptGuardrail
from app.security.logging_filter import install_sensitive_data_filter
from app.storage.object_storage import (
    ObjectStorage,
    StorageConfigurationError,
    StorageOperationError,
)

logger = logging.getLogger(__name__)
install_sensitive_data_filter()
MAX_TEXT_LENGTH = 20_000
MAX_UPLOAD_SIZE = SecureFileValidator.MAX_FILE_SIZE_MB * 1024 * 1024
REFRESH_COOKIE_NAME = "mediflow_refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"
FRONTEND_ORIGINS = tuple(
    dict.fromkeys(
        origin.strip().rstrip("/")
        for origin in (
            "https://g10-latam-equipo-23-mediflow.netlify.app",
            "http://localhost:5500",
            "http://127.0.0.1:5500",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            *os.getenv("ALLOWED_ORIGINS", "").split(","),
            *os.getenv("MEDIFLOW_FRONTEND_ORIGINS", "").split(","),
        )
        if origin.strip() and origin.strip() != "*"
    )
)
_early_rate_lock = threading.Lock()
_early_rate_events: dict[tuple[str, str], list[float]] = {}
CONTENT_TYPES = {
    "txt": "text/plain",
    "json": "application/json",
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

app = FastAPI(
    title="MediFlow API - Processamento Documental",
    version="1.4.0",
    description=(
        "Protótipo académico para extração documental e encaminhamento "
        "administrativo com revisão humana obrigatória."
    ),
)

limiter = Limiter(key_func=get_remote_address, default_limits=[])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

guardrail = PromptGuardrail()
anonymizer = ClinicalDataAnonymizer()


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class SetupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=12, max_length=1024)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=128)
    password: str = Field(min_length=12, max_length=1024)
    role: Literal["operador", "medico_auditor"]


def _set_refresh_cookie(
    response: Response, token: str, request: Request
) -> None:
    hostname = (request.url.hostname or "").lower()
    is_local_http = (
        request.url.scheme == "http" and hostname in {"localhost", "127.0.0.1", "::1"}
    )
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=REFRESH_TOKEN_TTL_SECONDS,
        httponly=True,
        secure=not is_local_http,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _assert_allowed_origin(request: Request, *, required: bool = False) -> None:
    origin = request.headers.get("origin")
    if (required and not origin) or (origin and origin not in FRONTEND_ORIGINS):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origem não autorizada.",
        )


def _early_rate_limited(request: Request, route: str, limit: int) -> bool:
    """Limita autenticação e uploads antes de o FastAPI ler o corpo do pedido."""
    host = request.client.host if request.client else "unknown"
    now = time.monotonic()
    key = (route, host)
    with _early_rate_lock:
        recent = [item for item in _early_rate_events.get(key, []) if now - item < 60]
        if len(recent) >= limit:
            _early_rate_events[key] = recent
            return True
        recent.append(now)
        _early_rate_events[key] = recent
        if len(_early_rate_events) > 2048:
            expired = [
                stored_key
                for stored_key, values in _early_rate_events.items()
                if not values or now - values[-1] >= 60
            ]
            for stored_key in expired:
                _early_rate_events.pop(stored_key, None)
            while len(_early_rate_events) > 2048:
                _early_rate_events.pop(next(iter(_early_rate_events)))
    return False


@app.middleware("http")
async def add_security_headers_and_limit_early_requests(
    request: Request, call_next
):
    """Define proteções do navegador e limita pedidos antes de analisar os corpos."""
    path = request.url.path
    early_limits = {
        "/api/v1/auth/setup": 3,
        "/api/v1/auth/login": 5,
        "/api/v1/auth/register": 5,
        "/api/v1/triage/text": 10,
        "/api/v1/triage/file": 10,
    }
    limit = early_limits.get(path) if request.method == "POST" else None
    if limit is not None and _early_rate_limited(request, path, limit):
        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"detail": "Demasiadas tentativas. Tente novamente mais tarde."},
        )
    elif (
        path == "/api/v1/triage/file"
        and request.method == "POST"
        and request.headers.get("content-length", "").isdigit()
        and int(request.headers["content-length"]) > MAX_UPLOAD_SIZE + 1024 * 1024
    ):
        response = JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "O upload excede o limite de 10 MB."},
        )
    elif (
        path == "/api/v1/triage/text"
        and request.method == "POST"
        and request.headers.get("content-length", "").isdigit()
        and int(request.headers["content-length"]) > MAX_TEXT_LENGTH + 64 * 1024
    ):
        response = JSONResponse(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            content={"detail": "O texto excede o limite permitido."},
        )
    else:
        response = await call_next(request)

    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.scheme == "https":
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
    return response


@app.get("/health", tags=["Healthcheck"])
def health_check():
    return {"status": "ok", "service": "MediFlow Core API"}


@app.get("/api/v1/auth/status", tags=["Autenticação"])
def authentication_status():
    return {"configured": auth_is_configured()}


@app.post("/api/v1/auth/setup", tags=["Autenticação"])
@limiter.limit("3/minute")
def setup_first_login(
    credentials: SetupRequest,
    request: Request,
    response: Response,
):
    _assert_allowed_origin(request)
    client_host = request.client.host if request.client else ""
    try:
        is_local = ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        is_local = False
    if not is_local:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A configuração inicial só pode ser feita neste computador.",
        )
    if auth_is_configured():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="O acesso já está configurado. Entre com sua conta.",
        )
    try:
        configure_login(credentials.username, credentials.password)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except SystemExit as exc:
        logger.error("Falha ao persistir a configuração inicial de acesso.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Não foi possível salvar as credenciais no .env.",
        ) from exc

    try:
        tokens = create_session_tokens(credentials.username, configured_role())
    except (RuntimeError, ValueError) as exc:
        logger.error("Falha ao criar a sessão de autenticação.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível iniciar a sessão.",
        ) from exc
    _set_refresh_cookie(response, tokens.pop("refresh_token"), request)
    return tokens


@app.post("/api/v1/auth/login", tags=["Autenticação"])
@limiter.limit("5/minute")
def login(credentials: LoginRequest, request: Request, response: Response):
    _assert_allowed_origin(request)
    if not auth_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticação não configurada.",
        )

    user = authenticate_user(credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        tokens = create_session_tokens(user["username"], user["role"])
    except (RuntimeError, ValueError) as exc:
        logger.error("Falha ao criar a sessão de autenticação.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível iniciar a sessão.",
        ) from exc
    _set_refresh_cookie(response, tokens.pop("refresh_token"), request)
    return tokens


@app.post("/api/v1/auth/register", tags=["Autenticação"])
@limiter.limit("5/minute")
def register(
    credentials: RegisterRequest,
    request: Request,
    response: Response,
):
    _assert_allowed_origin(request)
    if not auth_is_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configure o acesso inicial antes de registar novas contas.",
        )
    try:
        user = register_user(
            credentials.username,
            credentials.password,
            credentials.role,
        )
        tokens = create_session_tokens(user["username"], user["role"])
    except DuplicateUserError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except (RuntimeError, OSError, sqlite3.Error) as exc:
        logger.error("Falha ao criar a conta do utilizador.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível criar a conta.",
        ) from exc
    _set_refresh_cookie(response, tokens.pop("refresh_token"), request)
    return tokens


@app.post("/api/v1/auth/refresh", tags=["Autenticação"])
@limiter.limit("10/minute")
def refresh_session(request: Request, response: Response):
    _assert_allowed_origin(request, required=True)
    refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    try:
        tokens = rotate_refresh_token(refresh_token or "")
    except InvalidRefreshToken as exc:
        response.delete_cookie(
            REFRESH_COOKIE_NAME,
            path=REFRESH_COOKIE_PATH,
            httponly=True,
            secure=True,
            samesite="strict",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão de renovação inválida ou expirada.",
        ) from exc
    except RuntimeError as exc:
        logger.error("Falha ao validar a sessão de renovação.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível renovar a sessão.",
        ) from exc
    _set_refresh_cookie(response, tokens.pop("refresh_token"), request)
    return tokens


@app.post("/api/v1/auth/logout", tags=["Autenticação"])
@limiter.limit("10/minute")
def logout(request: Request, response: Response):
    _assert_allowed_origin(request, required=True)
    try:
        revoke_refresh_token(request.cookies.get(REFRESH_COOKIE_NAME))
    except RuntimeError as exc:
        logger.error("Falha ao revogar a sessão de renovação.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Não foi possível encerrar a sessão de forma segura.",
        ) from exc
    response.delete_cookie(
        REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )
    return {"success": True}


@app.get("/api/v1/auth/me", tags=["Autenticação"])
def current_session(user: dict[str, str] = Depends(get_current_user)):
    return {"username": user["username"], "role": user["role"]}


def _process_clinical_text(
    texto: str,
    source_content: bytes,
    extension: str,
    content_type: str,
    pii_mapping: dict[str, str] | None = None,
):
    """Valida, persiste, analisa e finaliza um documento segundo o seu estado."""
    if not texto.strip():
        raise HTTPException(
            status_code=422,
            detail="O texto do documento não pode estar vazio.",
        )
    if len(texto) > MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"O texto excede o limite de {MAX_TEXT_LENGTH} caracteres.",
        )

    if pii_mapping is None:
        try:
            texto_anonimizado, mapa_pii = anonymizer.anonymize_text(texto)
        except PrivacyPipelineError as exc:
            logger.error("Pipeline local de privacidade indisponível.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="O mascaramento Regex + NER não está disponível.",
            ) from exc
    else:
        texto_anonimizado, mapa_pii = texto, pii_mapping

    verdict = guardrail.validate_input(texto_anonimizado)
    if not verdict.is_safe:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "erro": "Inspeção de segurança rejeitou o texto",
                "motivo": verdict.reason,
                "risk_score": verdict.risk_score,
            },
        )

    document_id = str(uuid4())
    try:
        storage = ObjectStorage()
        storage.store_received(
            document_id,
            extension,
            source_content,
            content_type,
        )
    except (StorageConfigurationError, StorageOperationError) as exc:
        logger.error("Falha de armazenamento: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    try:
        documento_extraido: DocumentoExtraido = extrair(texto_anonimizado)
    except PrivacyPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O mascaramento Regex + NER não está disponível.",
        ) from exc
    except AgentConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O agente não está configurado. Defina GROQ_API_KEY.",
        ) from exc
    except APIStatusError as exc:
        if exc.status_code == 402:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="A conta Groq está sem créditos ou o pagamento foi recusado.",
            ) from exc
        if exc.status_code in (401, 403):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="A API Groq recusou a chave ou o acesso ao modelo.",
            ) from exc
        if exc.status_code == 429:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Limite de requisições da API Groq atingido. Tente novamente.",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="A API Groq não conseguiu processar o documento.",
        ) from exc
    except Exception as exc:
        logger.error("Falha ao processar documento pelo agente: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="O agente não conseguiu processar o documento.",
        ) from exc

    decisao_roteamento = rotear(documento_extraido)
    if documento_extraido.paciente.nome:
        documento_extraido.paciente.nome = anonymizer.deanonymize_text(
            documento_extraido.paciente.nome, mapa_pii
        )

    final_status = (
        "auditoria_humana"
        if decisao_roteamento["requer_auditoria_humana"]
        else "processados"
    )
    result_object_key = f"{final_status}/{document_id}/resultado.json"
    response_data = {
        "sucesso": True,
        "id_documento": document_id,
        "status": final_status,
        "especialidade_sugerida": (
            documento_extraido.classificacao.especialidade_sugerida
        ),
        "alerta": (
            documento_extraido.classificacao.nivel_prioridade == "Urgente"
            or decisao_roteamento["requer_auditoria_humana"]
        ),
        "seguranca": {
            "input_sanitizado": True,
            "pii_mascarada": len(mapa_pii) > 0,
            "extracao_local": extension in {"pdf", "jpg", "jpeg", "png"},
        },
        "dados_extraidos": documento_extraido.model_dump(),
        "decisao_roteamento": decisao_roteamento,
        "armazenamento": {
            "status": "confirmado",
            "backend": storage.backend,
            "object_key": result_object_key,
        },
    }
    try:
        storage.finalize(
            document_id,
            extension,
            source_content,
            response_data,
            final_status,
            content_type,
        )
    except (StorageConfigurationError, StorageOperationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return response_data


@app.post("/api/v1/triage/text", tags=["Triagem"])
@limiter.limit("10/minute")
def process_clinical_text(
    request: Request,
    texto: str = Form(...),
):
    return _process_clinical_text(texto, texto.encode("utf-8"), "txt", "text/plain")


@app.post("/api/v1/triage/file", tags=["Triagem"])
@limiter.limit("10/minute")
async def process_clinical_file(
    request: Request,
    file: UploadFile = File(...),
):
    """Valida e extrai um ficheiro antes de entrar no fluxo partilhado."""
    contents = await file.read(MAX_UPLOAD_SIZE + 1)
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"O arquivo excede o limite de "
                f"{SecureFileValidator.MAX_FILE_SIZE_MB} MB."
            ),
        )

    filename = file.filename or ""
    valido, msg_erro = SecureFileValidator.validate_upload(filename, contents)
    if not valido:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail={"erro": "Ficheiro Rejeitado", "motivo": msg_erro},
        )

    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "json":
        try:
            json.loads(contents.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=422,
                detail="O arquivo de texto não está codificado em UTF-8.",
            ) from exc
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="O arquivo JSON está malformado.",
            ) from exc

    try:
        extracted_text, pii_mapping = await run_in_threadpool(
            extract_and_anonymize_document_text, filename, contents
        )
    except OCRConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except PrivacyPipelineError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="O mascaramento Regex + NER não está disponível.",
        ) from exc
    except DocumentExtractionError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    return await run_in_threadpool(
        _process_clinical_text,
        extracted_text,
        contents,
        extension,
        CONTENT_TYPES[extension],
        pii_mapping,
    )

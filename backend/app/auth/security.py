"""Hash de senhas, tokens JWT de acesso e sessões rotativas de renovação."""

import base64
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator
from uuid import uuid4

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

ACCESS_TOKEN_TTL_SECONDS = 15 * 60
REFRESH_TOKEN_TTL_SECONDS = 7 * 24 * 60 * 60
TOKEN_TTL_SECONDS = ACCESS_TOKEN_TTL_SECONDS
PASSWORD_SCRYPT_N = 2**14
VALID_ROLES = {"admin", "medico_auditor", "operador"}
PROJECT_ROOT = Path(__file__).resolve().parents[3]
_bearer = HTTPBearer(auto_error=False)


class InvalidRefreshToken(ValueError):
    """Indica que o token de renovação expirou, foi revogado ou já foi usado."""


class DuplicateUserError(ValueError):
    """Indica que já existe uma conta para o e-mail solicitado."""


def hash_password(password: str) -> str:
    """Guardar um hash scrypt adaptativo com um novo salt aleatório."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_SCRYPT_N,
        r=8,
        p=1,
        dklen=32,
    )
    return "scrypt${}${}".format(
        base64.urlsafe_b64encode(salt).decode("ascii").rstrip("="),
        base64.urlsafe_b64encode(digest).decode("ascii").rstrip("="),
    )


_DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def verify_password(password: str, password_hash: str) -> bool:
    """Comparar uma senha com o hash guardado sem expor diferenças de tempo."""
    try:
        algorithm, salt_value, digest_value = password_hash.split("$", 2)
        if algorithm != "scrypt":
            return False
        salt = _decode_base64url(salt_value)
        expected = _decode_base64url(digest_value)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=PASSWORD_SCRYPT_N,
            r=8,
            p=1,
            dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode_base64url(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _auth_secret() -> str:
    return os.getenv("MEDIFLOW_AUTH_SECRET", "")


def _credential_version() -> str:
    return "mediflow-auth-v1"


def _signing_key(secret: str) -> bytes:
    return hmac.new(
        secret.encode("utf-8"),
        _credential_version().encode("ascii"),
        hashlib.sha256,
    ).digest()


def _credential_fingerprint(username: str, password_hash: str, secret: str) -> str:
    value = f"{username.lower()}\0{password_hash}".encode("utf-8")
    return hmac.new(secret.encode("utf-8"), value, hashlib.sha256).hexdigest()


def auth_is_configured() -> bool:
    return len(_auth_secret()) >= 32 and (
        bool(os.getenv("MEDIFLOW_USERNAME") and os.getenv("MEDIFLOW_PASSWORD_HASH"))
        or _user_count() > 0
    )


def configured_role() -> str:
    role = os.getenv("MEDIFLOW_ROLE", "operador")
    if role not in VALID_ROLES:
        raise ValueError("MEDIFLOW_ROLE não corresponde a uma role permitida.")
    return role


def create_access_token(
    username: str,
    secret: str | None = None,
    role: str | None = None,
) -> str:
    """Criar um JWT HS256 de curta duração com a role atual da conta."""
    signing_secret = secret or _auth_secret()
    if len(signing_secret) < 32:
        raise ValueError("MEDIFLOW_AUTH_SECRET deve ter pelo menos 32 caracteres.")
    user = get_user(username)
    token_role = role or (user["role"] if user else configured_role())
    if token_role not in VALID_ROLES:
        raise ValueError("Role de utilizador inválida.")
    if user and token_role != user["role"]:
        raise ValueError("A role pedida não corresponde à conta.")
    now = int(time.time())
    return jwt.encode(
        {
            "sub": username,
            "role": token_role,
            "cv": (
                _credential_fingerprint(
                    user["username"], user["password_hash"], signing_secret
                )
                if user
                else "legacy"
            ),
            "typ": "access",
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL_SECONDS,
            "iss": "mediflow",
            "aud": "mediflow-api",
        },
        _signing_key(signing_secret),
        algorithm="HS256",
    )


def _decode_token(token: str, expected_type: str) -> dict[str, Any] | None:
    signing_secret = _auth_secret()
    if len(signing_secret) < 32:
        return None
    try:
        payload = jwt.decode(
            token,
            _signing_key(signing_secret),
            algorithms=["HS256"],
            issuer="mediflow",
            audience="mediflow-api",
            options={"require": ["sub", "exp", "iat", "typ", "role", "cv"]},
        )
    except (jwt.PyJWTError, TypeError, ValueError):
        return None
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject:
        return None
    user = get_user(subject)
    if user is None:
        return None
    if (
        payload.get("typ") != expected_type
        or payload.get("role") not in VALID_ROLES
        or payload["role"] != user["role"]
        or not isinstance(payload.get("cv"), str)
        or not hmac.compare_digest(
            payload["cv"],
            _credential_fingerprint(
                user["username"], user["password_hash"], signing_secret
            ),
        )
    ):
        return None
    return payload


def decode_access_token(token: str, secret: str | None = None) -> str | None:
    """Devolver o utilizador apenas se a assinatura e a validade forem corretas."""
    if secret is not None and secret != _auth_secret():
        return None
    payload = _decode_token(token, "access")
    return payload["sub"] if payload else None


def _session_db_path() -> Path:
    configured = os.getenv("MEDIFLOW_AUTH_SESSION_DB")
    return Path(configured).expanduser() if configured else (
        PROJECT_ROOT / "backend" / "data" / "auth_sessions.sqlite3"
    )


def _connect_session_db() -> sqlite3.Connection:
    path = _session_db_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink() or path.is_symlink():
        raise RuntimeError("O armazenamento de sessões não pode usar links simbólicos.")
    os.chmod(path.parent, 0o700)
    connection = sqlite3.connect(path, timeout=5, isolation_level=None)
    os.chmod(path, 0o600)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS refresh_sessions (
            token_id TEXT PRIMARY KEY,
            username TEXT NOT NULL,
            role TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS users_role_idx ON users(role)"
    )
    os.chmod(path, 0o600)
    return connection


@contextmanager
def _session_connection() -> Iterator[sqlite3.Connection]:
    connection = _connect_session_db()
    try:
        yield connection
    finally:
        connection.close()


def _ensure_legacy_user(connection: sqlite3.Connection) -> None:
    username = os.getenv("MEDIFLOW_USERNAME", "").strip().lower()
    password_hash = os.getenv("MEDIFLOW_PASSWORD_HASH", "")
    role = os.getenv("MEDIFLOW_ROLE", "admin")
    admin_email = os.getenv("MEDIFLOW_ADMIN_EMAIL", "").strip().lower()
    if not username or not password_hash or role not in VALID_ROLES:
        return
    if admin_email and username != admin_email and role == "admin":
        role = "operador"
    connection.execute(
        "INSERT OR IGNORE INTO users(username, password_hash, role, created_at) "
        "VALUES (?, ?, ?, ?)",
        (username, password_hash, role, int(time.time())),
    )
    connection.execute(
        "UPDATE users SET password_hash = ?, role = ? "
        "WHERE username = ? COLLATE NOCASE",
        (password_hash, role, username),
    )
    if admin_email and username != admin_email:
        connection.execute(
            "UPDATE users SET role = 'operador' "
            "WHERE username = ? COLLATE NOCASE AND role = 'admin'",
            (username,),
        )


def _user_count() -> int:
    if len(_auth_secret()) < 32:
        return 0
    try:
        with _session_connection() as connection:
            _ensure_legacy_user(connection)
            row = connection.execute("SELECT COUNT(*) FROM users").fetchone()
            return int(row[0]) if row else 0
    except (OSError, sqlite3.Error, RuntimeError):
        return 0


def get_user(username: str) -> dict[str, str] | None:
    normalized = username.strip().lower()
    if not normalized:
        return None
    with _session_connection() as connection:
        _ensure_legacy_user(connection)
        row = connection.execute(
            "SELECT username, password_hash, role FROM users "
            "WHERE username = ? COLLATE NOCASE",
            (normalized,),
        ).fetchone()
    if not row:
        return None
    return {"username": row[0], "password_hash": row[1], "role": row[2]}


def register_user(username: str, password: str, role: str) -> dict[str, str]:
    normalized = username.strip().lower()
    if (
        len(normalized) > 128
        or not re.fullmatch(r"[^@\s]{1,64}@[^@\s.]+(?:\.[^@\s.]+)+", normalized)
    ):
        raise ValueError("Informe um endereço de e-mail válido.")
    if role not in {"operador", "medico_auditor"}:
        raise ValueError("O registo público permite apenas operador ou medico_auditor.")
    if len(password) < 12:
        raise ValueError("Use uma senha com pelo menos 12 caracteres.")
    if len(password) > 1024:
        raise ValueError("A senha excede o limite permitido.")

    password_hash = hash_password(password)
    with _session_connection() as connection:
        _ensure_legacy_user(connection)
        try:
            connection.execute(
                "INSERT INTO users(username, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?)",
                (normalized, password_hash, role, int(time.time())),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateUserError("Já existe uma conta com este e-mail.") from exc
    return {"username": normalized, "role": role}


def authenticate_user(username: str, password: str) -> dict[str, str] | None:
    user = get_user(username)
    password_matches = verify_password(
        password,
        user["password_hash"] if user else _DUMMY_PASSWORD_HASH,
    )
    if user is None or not password_matches:
        return None
    return {"username": user["username"], "role": user["role"]}


def _new_refresh_token(username: str, role: str) -> tuple[str, str, int]:
    user = get_user(username)
    if user is None or user["role"] != role:
        raise ValueError("A conta não existe ou a role não corresponde.")
    now = int(time.time())
    expires_at = now + REFRESH_TOKEN_TTL_SECONDS
    token_id = uuid4().hex
    token = jwt.encode(
        {
            "sub": username,
            "role": role,
            "cv": _credential_fingerprint(
                user["username"], user["password_hash"], _auth_secret()
            ),
            "typ": "refresh",
            "jti": token_id,
            "iat": now,
            "exp": expires_at,
            "iss": "mediflow",
            "aud": "mediflow-api",
        },
        _signing_key(_auth_secret()),
        algorithm="HS256",
    )
    return token, token_id, expires_at


def _register_refresh_token(username: str, role: str) -> str:
    token, token_id, expires_at = _new_refresh_token(username, role)
    with _session_connection() as connection:
        connection.execute(
            "DELETE FROM refresh_sessions WHERE expires_at <= ?",
            (int(time.time()),),
        )
        connection.execute(
            "INSERT INTO refresh_sessions(token_id, username, role, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token_id, username, role, expires_at),
        )
    return token


def create_session_tokens(username: str, role: str | None = None) -> dict[str, Any]:
    user = get_user(username)
    selected_role = role or (user["role"] if user else configured_role())
    if user and selected_role != user["role"]:
        raise ValueError("A role pedida não corresponde à conta.")
    return {
        "access_token": create_access_token(username, role=selected_role),
        "refresh_token": _register_refresh_token(username, selected_role),
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
    }


def rotate_refresh_token(token: str) -> dict[str, Any]:
    payload = _decode_token(token, "refresh")
    if not payload or not isinstance(payload.get("jti"), str):
        raise InvalidRefreshToken("Sessão de renovação inválida ou expirada.")

    replacement, replacement_id, replacement_expiry = _new_refresh_token(
        payload["sub"], payload["role"]
    )
    now = int(time.time())
    try:
        with _session_connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                "UPDATE refresh_sessions SET revoked = 1 "
                "WHERE token_id = ? AND username = ? AND role = ? "
                "AND expires_at > ? AND revoked = 0",
                (payload["jti"], payload["sub"], payload["role"], now),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                raise InvalidRefreshToken(
                    "Sessão de renovação inválida, expirada ou já utilizada."
                )
            connection.execute(
                "INSERT INTO refresh_sessions(token_id, username, role, expires_at) "
                "VALUES (?, ?, ?, ?)",
                (
                    replacement_id,
                    payload["sub"],
                    payload["role"],
                    replacement_expiry,
                ),
            )
            connection.commit()
    except sqlite3.Error as exc:
        raise RuntimeError("Não foi possível validar a sessão de renovação.") from exc

    return {
        "access_token": create_access_token(payload["sub"], role=payload["role"]),
        "refresh_token": replacement,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_TTL_SECONDS,
    }


def revoke_refresh_token(token: str | None) -> None:
    if not token:
        return
    payload = _decode_token(token, "refresh")
    if not payload or not isinstance(payload.get("jti"), str):
        return
    with _session_connection() as connection:
        connection.execute(
            "UPDATE refresh_sessions SET revoked = 1 WHERE token_id = ?",
            (payload["jti"],),
        )


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, str]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        demo_mode = os.getenv("MEDIFLOW_LOCAL_DEMO_MODE", "true").lower() == "true"
        if credentials is None and demo_mode:
            return {"username": "Dr. Equipa 23 (Demo)", "role": "admin"}
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Autenticação necessária.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = _decode_token(credentials.credentials, "access")
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada. Entre novamente.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user(payload["sub"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Conta não encontrada ou desativada.",
        )
    return {"username": user["username"], "role": user["role"]}


def require_roles(*allowed_roles: str) -> Callable[..., dict[str, str]]:
    """Criar uma dependência FastAPI que valida a role em cada pedido."""
    if not allowed_roles or not set(allowed_roles) <= VALID_ROLES:
        raise ValueError("Roles permitidas inválidas.")

    def role_dependency(
        user: dict[str, str] = Depends(get_current_user),
    ) -> dict[str, str]:
        if user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="A role atual não permite esta operação.",
            )
        return user

    return role_dependency


require_audit_access = require_roles("medico_auditor", "admin")

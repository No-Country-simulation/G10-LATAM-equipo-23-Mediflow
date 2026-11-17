"""Configuração local inicial de uma conta protegida por senha."""

import os
import re
import secrets
import tempfile
from getpass import getpass
from pathlib import Path

from app.auth.security import hash_password

PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = PROJECT_ROOT / ".env"


def configure_login(username: str, password: str) -> dict[str, str]:
    """Guardar um hash de credenciais validado e invalidar sessões anteriores."""
    if not re.fullmatch(r"[A-Za-z0-9._@-]{1,128}", username):
        raise ValueError(
            "Use de 1 a 128 caracteres: letras, números, ponto, hífen, _ ou @."
        )
    admin_email = os.getenv("MEDIFLOW_ADMIN_EMAIL", "").strip().lower()
    if admin_email and username.strip().lower() != admin_email:
        raise ValueError(
            "O primeiro administrador deve usar o endereço MEDIFLOW_ADMIN_EMAIL."
        )
    if len(password) < 12:
        raise ValueError("Use uma senha com pelo menos 12 caracteres.")
    if len(password) > 1024:
        raise ValueError("A senha excede o limite permitido.")

    values = {
        "MEDIFLOW_USERNAME": username,
        "MEDIFLOW_PASSWORD_HASH": hash_password(password),
        "MEDIFLOW_AUTH_SECRET": secrets.token_urlsafe(48),
        "MEDIFLOW_ROLE": "admin",
    }
    _update_env_file(values)
    os.environ.update(values)
    return values


def _update_env_file(values: dict[str, str]) -> None:
    """Atualizar o ficheiro env atomicamente e preservar as restantes chaves."""
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
        updated_lines = lines[:]
        for key, value in values.items():
            pattern = re.compile(rf"^\s*(?:export\s+)?{re.escape(key)}\s*=")
            replacement = f"{key}={value}"
            matching_lines = [
                index for index, line in enumerate(updated_lines) if pattern.match(line)
            ]
            if matching_lines:
                updated_lines[matching_lines[0]] = replacement
                for index in reversed(matching_lines[1:]):
                    updated_lines.pop(index)
            else:
                updated_lines.append(replacement)

        content = "\n".join(updated_lines).rstrip() + "\n"
        descriptor, temporary_name = tempfile.mkstemp(
            dir=ENV_FILE.parent, prefix=".env-", text=True
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, ENV_FILE)
        except OSError:
            Path(temporary_name).unlink(missing_ok=True)
            raise
    except OSError as exc:
        raise SystemExit(
            "Não foi possível atualizar o .env. Confira as permissões da pasta."
        ) from exc


def main() -> None:
    username = input("Usuário do MediFlow [operador]: ").strip() or "operador"
    password = getpass("Senha (mínimo 12 caracteres): ")
    confirmation = getpass("Confirme a senha: ")
    if password != confirmation:
        raise SystemExit("As senhas não coincidem.")
    try:
        configure_login(username, password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("Acesso configurado no .env (permissão restrita ao usuário atual).")


if __name__ == "__main__":
    main()

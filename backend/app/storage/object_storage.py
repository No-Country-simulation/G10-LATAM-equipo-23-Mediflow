"""Status-based local or OCI Object Storage for originals and triage results."""

import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ENV_FILES = (PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env")
ENCRYPTED_FILE_PREFIX = b"MEDIFLOW-FERNET-V1:"
ENCRYPTED_LOCAL_PREFIXES = {"recebidos", "auditoria_humana"}


class StorageConfigurationError(RuntimeError):
    pass


class StorageOperationError(RuntimeError):
    pass


class ObjectStorage:
    """Keep uploaded originals and result JSON under an explicit workflow status."""

    VALID_STATUSES = {"processados", "auditoria_humana"}

    def __init__(self) -> None:
        self.backend = os.getenv("MEDIFLOW_STORAGE_BACKEND", "local").lower()
        if self.backend == "local":
            default_path = Path(__file__).resolve().parents[2] / "data" / "storage"
            self.root = Path(
                os.getenv("MEDIFLOW_LOCAL_STORAGE_DIR") or str(default_path)
            ).expanduser()
            self._fernet = self._create_fernet()
            self._harden_local_storage()
            self._encrypt_existing_documents()
            return
        if self.backend != "oci":
            raise StorageConfigurationError(
                "MEDIFLOW_STORAGE_BACKEND deve ser 'local' ou 'oci'."
            )

        config_path = os.path.expanduser(
            os.getenv("OCI_CONFIG_FILE", "~/.oci/config")
        )
        profile = os.getenv("OCI_CONFIG_PROFILE", "DEFAULT")
        self.bucket = os.getenv("OCI_BUCKET_NAME", "")
        self.namespace = os.getenv("OCI_NAMESPACE", "")
        if not self.bucket:
            raise StorageConfigurationError(
                "Defina OCI_BUCKET_NAME para usar o OCI Object Storage."
            )
        try:
            import oci

            config = oci.config.from_file(config_path, profile)
            self.client = oci.object_storage.ObjectStorageClient(config)
            if not self.namespace:
                self.namespace = self.client.get_namespace().data
        except Exception as exc:
            raise StorageConfigurationError(
                "Não foi possível configurar o cliente OCI Object Storage. "
                "Confira OCI_CONFIG_FILE, OCI_CONFIG_PROFILE, OCI_NAMESPACE e "
                "as permissões do usuário."
            ) from exc

    @staticmethod
    def _create_fernet() -> Fernet:
        """Load the local encryption key without logging or exposing its value."""
        key = os.getenv("STORAGE_ENCRYPTION_KEY")
        if not key:
            for env_file in reversed(ENV_FILES):
                value = dotenv_values(env_file).get("STORAGE_ENCRYPTION_KEY")
                if value:
                    key = value
                    break
        if not key:
            raise StorageConfigurationError(
                "Defina STORAGE_ENCRYPTION_KEY no ambiente ou no backend/.env "
                "para usar o armazenamento local."
            )
        try:
            return Fernet(key.encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise StorageConfigurationError(
                "STORAGE_ENCRYPTION_KEY não é uma chave Fernet válida."
            ) from exc

    def store_received(
        self,
        document_id: str,
        extension: str,
        content: bytes,
        content_type: str,
    ) -> str:
        """Record the original in the temporary received prefix."""
        object_key = f"recebidos/{document_id}/original.{extension}"
        if self.backend == "local":
            self._write_local(object_key, content)
            return object_key
        try:
            self.client.put_object(
                self.namespace,
                self.bucket,
                object_key,
                content,
                content_type=content_type,
            )
        except Exception as exc:
            raise StorageOperationError(
                "Não foi possível salvar o documento recebido no OCI Object Storage."
            ) from exc
        return object_key

    def finalize(
        self,
        document_id: str,
        extension: str,
        content: bytes,
        result: dict[str, Any],
        status_name: str,
        content_type: str,
    ) -> str:
        """Move the original and persist its result under the final review status."""
        if status_name not in self.VALID_STATUSES:
            raise ValueError(f"Status de armazenamento inválido: {status_name}")
        folder = f"{status_name}/{document_id}"
        original_key = f"{folder}/original.{extension}"
        result_key = f"{folder}/resultado.json"
        result_bytes = json.dumps(
            result, ensure_ascii=False, indent=2
        ).encode("utf-8")

        if self.backend == "local":
            self._write_local(original_key, content)
            received = self.root / "recebidos" / document_id
            try:
                if received.exists():
                    for item in received.iterdir():
                        item.unlink()
                    received.rmdir()
            except OSError as exc:
                raise StorageOperationError(
                    "Não foi possível mover o documento para seu status final."
                ) from exc
            self._write_local(result_key, result_bytes)
            return result_key

        try:
            self.client.put_object(
                self.namespace,
                self.bucket,
                original_key,
                content,
                content_type=content_type,
            )
            self.client.delete_object(
                self.namespace,
                self.bucket,
                f"recebidos/{document_id}/original.{extension}",
            )
            self.client.put_object(
                self.namespace,
                self.bucket,
                result_key,
                result_bytes,
                content_type="application/json",
            )
        except Exception as exc:
            raise StorageOperationError(
                "Não foi possível finalizar o armazenamento do documento no OCI."
            ) from exc
        return result_key

    def _write_local(self, object_key: str, content: bytes) -> None:
        """Encrypt protected files and atomically persist local objects."""
        target = self._local_path(object_key)
        if self._is_encrypted_local_path(object_key):
            content = self._encrypt(content)
        self._atomic_write_local(target, content)

    def _read_local(self, object_key: str) -> bytes:
        """Read a local object and decrypt protected data only in process memory."""
        target = self._local_path(object_key)
        try:
            content = target.read_bytes()
        except OSError as exc:
            raise StorageOperationError(
                "Não foi possível ler o objeto do armazenamento local."
            ) from exc
        if self._is_encrypted_local_path(object_key):
            return self._decrypt(content)
        return content

    def _encrypt_existing_documents(self) -> None:
        """Migrate existing plaintext files in protected folders in place."""
        for folder in ENCRYPTED_LOCAL_PREFIXES:
            status_path = self.root / folder
            if status_path.is_symlink():
                raise StorageConfigurationError(
                    "Pastas de documentos protegidas não podem ser links simbólicos."
                )
            if not status_path.is_dir():
                continue
            for current, directories, filenames in os.walk(
                status_path, followlinks=False
            ):
                current_path = Path(current)
                for directory in directories:
                    if (current_path / directory).is_symlink():
                        raise StorageConfigurationError(
                            "Pastas internas de documentos não podem ser links simbólicos."
                        )
                for filename in filenames:
                    path = current_path / filename
                    try:
                        if path.is_symlink() or not stat.S_ISREG(
                            path.lstat().st_mode
                        ):
                            continue
                        content = path.read_bytes()
                        if content.startswith(ENCRYPTED_FILE_PREFIX):
                            self._decrypt(content)
                            continue
                        self._atomic_write_local(path, self._encrypt(content))
                    except StorageOperationError as exc:
                        raise StorageConfigurationError(
                            "Não foi possível migrar documentos existentes para "
                            "o armazenamento criptografado."
                        ) from exc
                    except OSError as exc:
                        raise StorageConfigurationError(
                            "Não foi possível migrar documentos existentes para "
                            "o armazenamento criptografado."
                        ) from exc

    def _encrypt(self, content: bytes) -> bytes:
        return ENCRYPTED_FILE_PREFIX + self._fernet.encrypt(content)

    def _decrypt(self, encrypted_content: bytes) -> bytes:
        if not encrypted_content.startswith(ENCRYPTED_FILE_PREFIX):
            raise StorageOperationError(
                "O objeto protegido não está criptografado."
            )
        try:
            return self._fernet.decrypt(
                encrypted_content[len(ENCRYPTED_FILE_PREFIX) :]
            )
        except InvalidToken as exc:
            raise StorageOperationError(
                "Não foi possível autenticar ou descriptografar o objeto protegido."
            ) from exc

    @staticmethod
    def _is_encrypted_local_path(object_key: str) -> bool:
        parts = object_key.split("/")
        return bool(parts and parts[0] in ENCRYPTED_LOCAL_PREFIXES)

    def _local_path(self, object_key: str) -> Path:
        parts = object_key.split("/")
        if (
            not object_key
            or object_key.startswith("/")
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise StorageOperationError("Caminho de objeto local inválido.")
        return self.root.joinpath(*parts)

    @staticmethod
    def _atomic_write_local(target: Path, content: bytes) -> None:
        """Atomically replace a local object to avoid partially written files."""
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(target.parent, 0o700)
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".tmp-", delete=False
            ) as temporary:
                temporary.write(content)
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, target)
        except OSError as exc:
            if "temporary_path" in locals():
                temporary_path.unlink(missing_ok=True)
            raise StorageOperationError(
                "Não foi possível salvar o documento no armazenamento local."
            ) from exc

    def _harden_local_storage(self) -> None:
        """Restrict existing local records to this user without opening their contents."""
        try:
            self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
            if self.root.is_symlink():
                raise StorageConfigurationError(
                    "O diretório local de armazenamento não pode ser um link simbólico."
                )
            os.chmod(self.root, 0o700)
            for current, directories, filenames in os.walk(
                self.root, followlinks=False
            ):
                current_path = Path(current)
                for directory in directories:
                    path = current_path / directory
                    if not path.is_symlink():
                        os.chmod(path, 0o700)
                for filename in filenames:
                    path = current_path / filename
                    if not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode):
                        os.chmod(path, 0o600)
        except StorageConfigurationError:
            raise
        except OSError as exc:
            raise StorageConfigurationError(
                "Não foi possível restringir as permissões do armazenamento local."
            ) from exc

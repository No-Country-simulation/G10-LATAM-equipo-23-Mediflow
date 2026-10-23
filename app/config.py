from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = ""
    oci_namespace: str = ""
    oci_bucket: str = "mediflow-documentos-clinicos"
    oci_config_file: str = "~/.oci/config"
    n8n_webhook_url: str = ""
    confidence_threshold: float = 0.80

settings = Settings()
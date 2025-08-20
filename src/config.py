from pydantic_settings import BaseSettings
from pydantic import Field, field_validator
from typing import Optional, List
from pathlib import Path


class MT5Settings(BaseSettings):
    """Validated configuration for MetaTrader5 Docker"""

    # Wine configuration
    wine_prefix: str = Field(default="/config/.wine")
    wine_version: str = Field(default="win10")

    # MT5 configuration
    mt5_port: int = Field(default=8001, gt=1024, lt=65535)
    mt5_version: str = Field(default="5.0.5200")

    # Download URLs
    mono_url: str = Field(
        default="https://dl.winehq.org/wine/wine-mono/10.2.0/wine-mono-10.2.0-x86.msi"
    )
    python_url: str = Field(
        default="https://www.python.org/ftp/python/3.13.7/python-3.13.7.exe"
    )
    mt5_download_url: str = Field(
        default="https://download.mql5.com/cdn/web/metaquotes.ltd/mt5/mt5setup.exe"
    )

    # VNC configuration
    vnc_port: int = Field(default=3000, gt=1024, lt=65535)
    custom_user: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)

    # Python packages
    required_packages: List[str] = Field(
        default=["MetaTrader5==5.0.5200", "mt5linux", "pyxdg"]
    )

    # Timeouts and retries
    download_timeout: int = Field(default=300, gt=0)
    max_retries: int = Field(default=3, gt=0)

    # Logging
    log_level: str = Field(default="INFO")

    # Cache
    cache_enabled: bool = Field(default=True)
    cache_ttl_days: int = Field(default=7, gt=0)

    # Performance
    download_chunk_size: int = Field(default=8192, gt=0)
    startup_timeout: int = Field(default=300, gt=0)

    @field_validator("password")
    def password_strength(cls, v):
        if v and len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        return v

    @field_validator("wine_version")
    def validate_wine_version(cls, v):
        allowed = ["win10", "win7", "winxp"]
        if v not in allowed:
            raise ValueError(f"Wine version must be one of {allowed}")
        return v

    @field_validator("log_level")
    def validate_log_level(cls, v):
        allowed = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in allowed:
            raise ValueError(f"Log level must be one of {allowed}")
        return v.upper()

    def get_cache_dir(self) -> Path:
        """Get cache directory"""
        return Path(self.wine_prefix).parent / ".cache"

    model_config = {"env_file": ".env", "case_sensitive": False}


# Global configuration instance
settings = MT5Settings()

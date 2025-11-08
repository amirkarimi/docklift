"""Configuration schema for docklift."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class VPSConfig(BaseModel):
    """VPS connection configuration."""

    host: str = Field(..., description="VPS IP address or hostname")
    user: str = Field(..., description="SSH user")
    ssh_key_path: str = Field(..., description="Path to SSH private key")
    port: int = Field(default=22, description="SSH port")
    email: str | None = Field(
        default=None,
        description="Email for Let's Encrypt notifications (optional but recommended)",
    )

    @field_validator("ssh_key_path")
    @classmethod
    def validate_ssh_key_path(cls, v: str) -> str:
        """Validate that SSH key path exists."""
        path = Path(v).expanduser()
        if not path.exists():
            raise ValueError(f"SSH key not found at: {v}")
        return str(path)


class ServiceConfig(BaseModel):
    """Docker compose service configuration."""

    image: str | None = Field(None, description="Docker image name")
    environment: dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )
    volumes: list[str] = Field(default_factory=list, description="Volume mounts")
    ports: list[str] = Field(default_factory=list, description="Port mappings")
    depends_on: list[str] = Field(
        default_factory=list, description="Service dependencies"
    )
    extra: dict[str, Any] = Field(
        default_factory=dict, description="Additional docker compose options"
    )


class ApplicationConfig(BaseModel):
    """Application deployment configuration."""

    name: str = Field(..., description="Application name (used for container naming)")
    domain: str = Field(..., description="Domain name for the application")
    dockerfile: str = Field(
        default="./Dockerfile", description="Path to Dockerfile relative to context"
    )
    context: str = Field(
        default=".", description="Build context path (local directory to upload)"
    )
    port: int | None = Field(
        None,
        description="Internal port the app listens on (auto-assigned if not specified)",
    )
    environment: dict[str, str] = Field(
        default_factory=dict, description="Environment variables for the app"
    )
    dependencies: dict[str, ServiceConfig] = Field(
        default_factory=dict,
        description="Additional services (databases, caches, etc.)",
    )


class DockLiftConfig(BaseModel):
    """Main docklift configuration."""

    vps: VPSConfig
    application: ApplicationConfig

    @classmethod
    def from_yaml(cls, path: str | Path) -> "DockLiftConfig":
        """Load configuration from YAML file."""
        yaml_path = Path(path)
        if not yaml_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")

        with open(yaml_path) as f:
            data = yaml.safe_load(f)

        return cls(**data)

    def to_yaml(self, path: str | Path) -> None:
        """Save configuration to YAML file."""
        yaml_path = Path(path)
        yaml_path.parent.mkdir(parents=True, exist_ok=True)

        with open(yaml_path, "w") as f:
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False)

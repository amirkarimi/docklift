"""Configuration schema for docklift."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


def _load_env_file(env_path: Path) -> dict[str, str]:
    """Load environment variables from .env file.

    Supports basic .env format:
    - KEY=value
    - KEY="value"
    - KEY='value'
    - Comments with #
    - Empty lines

    Args:
        env_path: Path to .env file

    Returns:
        Dictionary of environment variables
    """
    env_vars = {}

    with open(env_path) as f:
        for line in f:
            line = line.strip()

            # Skip empty lines and comments
            if not line or line.startswith("#"):
                continue

            # Parse KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                env_vars[key] = value

    return env_vars


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
    environment: dict[str, str] | list[str] | None = Field(
        None, description="Environment variables"
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
    env_file: str | None = Field(
        None,
        description="Path to .env file with additional environment variables (merged with environment)",
    )
    dependencies: dict[str, ServiceConfig] = Field(
        default_factory=dict,
        description="Additional services (databases, caches, etc.)",
    )

    def get_merged_environment(self) -> dict[str, str]:
        """Get environment variables merged with .env file.

        Variables defined in the YAML config take precedence over .env file.

        Returns:
            Merged environment variables
        """
        merged_env = {}

        # Load from .env file first (if specified)
        if self.env_file:
            env_path = Path(self.env_file).expanduser()
            if env_path.exists():
                merged_env.update(_load_env_file(env_path))

        # Override with explicit environment variables from config
        merged_env.update(self.environment)

        # Add port as environment variable
        if self.port is not None:
            merged_env.setdefault("PORT", str(self.port))

        return merged_env


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

"""SSH connection management using Fabric."""

from pathlib import Path
from typing import Any

from fabric import Connection
from invoke import Result
from rich.console import Console

from .config import VPSConfig

console = Console()


class VPSConnection:
    """Manages SSH connection to VPS."""

    def __init__(self, config: VPSConfig):
        """Initialize VPS connection.

        Args:
            config: VPS configuration with connection details
        """
        self.config = config
        self._connection: Connection | None = None

    def __enter__(self) -> "VPSConnection":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()

    def connect(self) -> None:
        """Establish SSH connection."""
        if self._connection is not None:
            return

        console.print(
            f"[cyan]Connecting to {self.config.user}@{self.config.host}...[/cyan]"
        )

        connect_kwargs = {
            "key_filename": self.config.ssh_key_path,
        }

        self._connection = Connection(
            host=self.config.host,
            user=self.config.user,
            port=self.config.port,
            connect_kwargs=connect_kwargs,
        )

        # Test connection
        self._connection.run("echo 'Connection established'", hide=True)
        console.print("[green]✓ Connected successfully[/green]")

    def close(self) -> None:
        """Close SSH connection."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> Connection:
        """Get active connection."""
        if self._connection is None:
            raise RuntimeError("Not connected. Call connect() first.")
        return self._connection

    def run(
        self, command: str, hide: bool = False, warn: bool = False
    ) -> Result:
        """Run command on remote VPS.

        Args:
            command: Shell command to execute
            hide: Hide command output
            warn: Don't raise exception on failure

        Returns:
            Command result
        """
        return self.connection.run(command, hide=hide, warn=warn)

    def sudo(
        self, command: str, hide: bool = False, warn: bool = False
    ) -> Result:
        """Run command with sudo on remote VPS.

        Args:
            command: Shell command to execute
            hide: Hide command output
            warn: Don't raise exception on failure

        Returns:
            Command result
        """
        return self.connection.sudo(command, hide=hide, warn=warn)

    def put(self, local: str | Path, remote: str) -> None:
        """Upload file to VPS.

        Args:
            local: Local file path
            remote: Remote file path
        """
        console.print(f"[cyan]Uploading {local} -> {remote}[/cyan]")
        self.connection.put(str(local), remote)

    def file_exists(self, path: str) -> bool:
        """Check if file exists on VPS.

        Args:
            path: Remote file path

        Returns:
            True if file exists
        """
        result = self.run(f"test -f {path}", warn=True, hide=True)
        return result.ok

    def dir_exists(self, path: str) -> bool:
        """Check if directory exists on VPS.

        Args:
            path: Remote directory path

        Returns:
            True if directory exists
        """
        result = self.run(f"test -d {path}", warn=True, hide=True)
        return result.ok

    def command_exists(self, command: str) -> bool:
        """Check if command exists on VPS.

        Args:
            command: Command name

        Returns:
            True if command exists
        """
        result = self.run(f"command -v {command}", warn=True, hide=True)
        return result.ok

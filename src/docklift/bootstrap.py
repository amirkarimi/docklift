"""Bootstrap VPS with Docker, Caddy, and shared network."""

from pathlib import Path
from tempfile import NamedTemporaryFile

from rich.console import Console

from .connection import VPSConnection

console = Console()

DOCKLIFT_DIR = "/opt/docklift"
CADDY_COMPOSE_FILE = f"{DOCKLIFT_DIR}/caddy-compose.yml"
CADDYFILE_PATH = f"{DOCKLIFT_DIR}/Caddyfile"
SHARED_NETWORK = "docklift-network"


def bootstrap(conn: VPSConnection, email: str | None = None) -> None:
    """Bootstrap VPS with required infrastructure.

    This is idempotent and can be run multiple times safely.

    Args:
        conn: VPS connection
        email: Email for Let's Encrypt notifications (optional)
    """
    console.print("\n[bold cyan]Starting VPS Bootstrap[/bold cyan]\n")

    _install_docker(conn)
    _create_shared_network(conn)
    _setup_caddy(conn, email)

    console.print("\n[bold green]✓ Bootstrap completed successfully![/bold green]\n")


def _install_docker(conn: VPSConnection) -> None:
    """Install Docker and Docker Compose if not present.

    Args:
        conn: VPS connection
    """
    console.print("[cyan]Checking Docker installation...[/cyan]")

    if conn.command_exists("docker"):
        console.print("[green]✓ Docker already installed[/green]")
    else:
        console.print("[yellow]Installing Docker...[/yellow]")

        # Install Docker using official installation script
        conn.sudo(
            "apt-get update && apt-get install -y curl ca-certificates", hide=True
        )
        conn.run(
            "curl -fsSL https://get.docker.com -o /tmp/get-docker.sh", hide=True
        )
        conn.sudo("sh /tmp/get-docker.sh", hide=True)
        conn.run("rm /tmp/get-docker.sh", hide=True)

        # Add user to docker group
        conn.sudo(f"usermod -aG docker {conn.config.user}", warn=True)

        console.print("[green]✓ Docker installed successfully[/green]")

    # Check Docker Compose (modern Docker includes it as a plugin)
    result = conn.run("docker compose version", warn=True, hide=True)
    if result.ok:
        console.print("[green]✓ Docker Compose available[/green]")
    else:
        console.print("[red]✗ Docker Compose not found[/red]")
        raise RuntimeError(
            "Docker Compose not available. Please install Docker version 20.10+."
        )


def _create_shared_network(conn: VPSConnection) -> None:
    """Create shared Docker network for all applications.

    Args:
        conn: VPS connection
    """
    console.print(f"[cyan]Creating shared network '{SHARED_NETWORK}'...[/cyan]")

    # Check if network exists
    result = conn.run(
        f"docker network ls --filter name=^{SHARED_NETWORK}$ --format '{{{{.Name}}}}'",
        hide=True,
        warn=True,
    )

    if SHARED_NETWORK in result.stdout:
        console.print("[green]✓ Shared network already exists[/green]")
    else:
        conn.run(f"docker network create {SHARED_NETWORK}", hide=True)
        console.print("[green]✓ Shared network created[/green]")


def _setup_caddy(conn: VPSConnection, email: str | None = None) -> None:
    """Setup Caddy reverse proxy with automatic HTTPS.

    Args:
        conn: VPS connection
        email: Email for Let's Encrypt notifications (optional)
    """
    console.print("[cyan]Setting up Caddy reverse proxy...[/cyan]")

    # Create docklift directory
    if not conn.dir_exists(DOCKLIFT_DIR):
        conn.sudo(f"mkdir -p {DOCKLIFT_DIR}")
        conn.sudo(f"chown {conn.config.user}:{conn.config.user} {DOCKLIFT_DIR}")
        console.print(f"[green]✓ Created {DOCKLIFT_DIR}[/green]")

    # Create initial Caddyfile
    caddyfile_content = _generate_initial_caddyfile(email)
    _upload_file_content(conn, caddyfile_content, CADDYFILE_PATH)
    console.print("[green]✓ Created Caddyfile[/green]")

    # Create Caddy docker-compose.yml
    caddy_compose = _generate_caddy_compose()
    _upload_file_content(conn, caddy_compose, CADDY_COMPOSE_FILE)
    console.print("[green]✓ Created Caddy compose file[/green]")

    # Start Caddy
    conn.run(f"cd {DOCKLIFT_DIR} && docker compose -f {CADDY_COMPOSE_FILE} up -d")
    console.print("[green]✓ Caddy started successfully[/green]")


def _generate_initial_caddyfile(email: str | None = None) -> str:
    """Generate initial Caddyfile content.

    Args:
        email: Email for Let's Encrypt notifications (optional)

    Returns:
        Caddyfile content as string
    """
    email_line = f"    email {email}" if email else "    # email not configured"

    return f"""{{
    # Global options
    admin off
{email_line}
}}

# Placeholder for application routes
# This file will be updated by docklift deploy
"""


def _generate_caddy_compose() -> str:
    """Generate Caddy docker-compose.yml content.

    Returns:
        Docker compose YAML as string
    """
    return f"""version: '3.8'

services:
  caddy:
    image: caddy:2-alpine
    container_name: docklift-caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"  # HTTP/3
    volumes:
      - {CADDYFILE_PATH}:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - {SHARED_NETWORK}

volumes:
  caddy_data:
  caddy_config:

networks:
  {SHARED_NETWORK}:
    external: true
"""


def _upload_file_content(conn: VPSConnection, content: str, remote_path: str) -> None:
    """Upload file content to VPS using temporary file.

    Args:
        conn: VPS connection
        content: File content as string
        remote_path: Destination path on VPS
    """
    with NamedTemporaryFile(mode="w", suffix=".tmp", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        conn.put(tmp_path, remote_path)
    finally:
        Path(tmp_path).unlink()


def update_caddyfile(conn: VPSConnection, domain: str, app_name: str, port: int) -> None:
    """Update Caddyfile to add a new application route.

    Args:
        conn: VPS connection
        domain: Application domain name
        app_name: Application container name
        port: Application internal port
    """
    console.print(f"[cyan]Updating Caddyfile for {domain}...[/cyan]")

    # Download current Caddyfile
    with NamedTemporaryFile(mode="w+", suffix=".tmp", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        conn.connection.get(CADDYFILE_PATH, tmp_path)

        with open(tmp_path) as f:
            content = f.read()

        # Check if domain already exists
        if domain in content:
            console.print(f"[yellow]Domain {domain} already configured[/yellow]")
            return

        # Add new route
        new_route = f"""
{domain} {{
    reverse_proxy {app_name}:{port}
}}
"""

        content += new_route

        with open(tmp_path, "w") as f:
            f.write(content)

        conn.put(tmp_path, CADDYFILE_PATH)
        console.print(f"[green]✓ Added {domain} to Caddyfile[/green]")

        # Reload Caddy
        conn.run(
            f"docker exec docklift-caddy caddy reload --config /etc/caddy/Caddyfile"
        )
        console.print("[green]✓ Caddy reloaded[/green]")

    finally:
        Path(tmp_path).unlink()

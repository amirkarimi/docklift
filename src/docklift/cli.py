"""CLI interface for docklift."""

from pathlib import Path
from typing import Required

import click
from rich.console import Console
from rich.panel import Panel
from rich.traceback import install

from .bootstrap import bootstrap
from .config import DockLiftConfig
from .connection import VPSConnection
from .deploy import deploy

# Install rich traceback for better error messages
install(show_locals=True)

console = Console()


@click.group()
@click.version_option(version="0.1.0", prog_name="docklift")
def cli() -> None:
    """DockLift - Deploy web applications to VPS with Docker Compose and automatic SSL."""
    pass


@cli.command()
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default="docklift.yml",
    help="Path to configuration file",
)
def bootstrap_cmd(config: Path) -> None:
    """Bootstrap VPS with Docker, Caddy, and shared infrastructure.

    This command is idempotent and can be run multiple times safely.
    It will:
    - Install Docker and Docker Compose if not present
    - Create a shared network for all applications
    - Set up Caddy reverse proxy with automatic HTTPS
    """
    console.print(
        Panel.fit(
            "[bold cyan]DockLift Bootstrap[/bold cyan]\n"
            "Preparing your VPS for application deployments",
            border_style="cyan",
        )
    )

    try:
        # Load configuration
        cfg = DockLiftConfig.from_yaml(config)

        # Connect to VPS
        with VPSConnection(cfg.vps) as conn:
            bootstrap(conn, email=cfg.vps.email)

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        raise click.Abort()


@cli.command()
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default="docklift.yml",
    help="Path to configuration file",
)
@click.option(
    "--skip-bootstrap",
    is_flag=True,
    help="Skip bootstrap check (assume VPS is already bootstrapped)",
)
def deploy_cmd(config: Path, skip_bootstrap: bool) -> None:
    """Deploy application to VPS.

    This command is idempotent and can be run multiple times safely.
    It will:
    - Upload application code and dependencies
    - Generate docker-compose.yml for the application
    - Build the application image on the VPS
    - Start or update the application
    - Configure Caddy to route traffic to the application
    - Test that the application is reachable
    """
    console.print(
        Panel.fit(
            "[bold cyan]DockLift Deploy[/bold cyan]\n"
            "Deploying your application to VPS",
            border_style="cyan",
        )
    )

    try:
        # Load configuration
        cfg = DockLiftConfig.from_yaml(config)

        # Connect to VPS
        with VPSConnection(cfg.vps) as conn:
            # Check if VPS is bootstrapped
            if not skip_bootstrap:
                if not conn.command_exists("docker"):
                    console.print(
                        "\n[yellow]VPS is not bootstrapped. Running bootstrap first...[/yellow]\n"
                    )
                    bootstrap(conn, email=cfg.vps.email)

            # Deploy application
            deploy(conn, cfg.application)

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        raise click.Abort()


@cli.command()
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default="docklift.yml",
    help="Path to configuration file",
)
def status(config: Path) -> None:
    """Check status of deployed application."""
    try:
        # Load configuration
        cfg = DockLiftConfig.from_yaml(config)

        # Connect to VPS
        with VPSConnection(cfg.vps) as conn:
            console.print(
                f"\n[bold cyan]Status for {cfg.application.name}[/bold cyan]\n"
            )

            # Check if app exists
            result = conn.run(
                f"docker ps -a --filter name={cfg.application.name}-app --format '{{{{.Status}}}}'",
                hide=True,
                warn=True,
            )

            if not result.stdout.strip():
                console.print("[yellow]Application not deployed[/yellow]\n")
                return

            status_str = result.stdout.strip()
            if "Up" in status_str:
                console.print(f"[green]✓ Running: {status_str}[/green]")
            else:
                console.print(f"[red]✗ Not running: {status_str}[/red]")

            # Show logs
            console.print("\n[cyan]Recent logs:[/cyan]")
            conn.run(
                f"docker logs --tail 20 {cfg.application.name}-app", warn=True
            )

            console.print(
                f"\n[cyan]Domain: https://{cfg.application.domain}[/cyan]\n"
            )

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        raise click.Abort()


@cli.command()
@click.option(
    "-c",
    "--config",
    type=click.Path(exists=True, path_type=Path),
    default="docklift.yml",
    help="Path to configuration file",
)
@click.option(
    "--remove-volumes",
    is_flag=True,
    help="Remove volumes (WARNING: will delete data)",
)
@click.confirmation_option(
    prompt="Are you sure you want to remove this application?"
)
def remove(config: Path, remove_volumes: bool) -> None:
    """Remove deployed application from VPS.

    WARNING: This will stop and remove the application containers.
    Use --remove-volumes to also delete data volumes.
    """
    try:
        # Load configuration
        cfg = DockLiftConfig.from_yaml(config)

        # Connect to VPS
        with VPSConnection(cfg.vps) as conn:
            console.print(
                f"\n[bold yellow]Removing {cfg.application.name}[/bold yellow]\n"
            )

            app_dir = f"/opt/docklift/apps/{cfg.application.name}"

            if conn.dir_exists(app_dir):
                # Stop and remove containers
                volume_flag = "-v" if remove_volumes else ""
                conn.run(
                    f"cd {app_dir} && docker compose down {volume_flag}", warn=True
                )
                console.print("[green]✓ Containers removed[/green]")

                # Remove application directory
                conn.run(f"rm -rf {app_dir}")
                console.print("[green]✓ Application files removed[/green]")

                console.print(
                    "\n[yellow]Note: Caddy configuration not automatically updated.[/yellow]"
                )
                console.print(
                    "[yellow]The domain entry will remain in Caddyfile but won't serve traffic.[/yellow]\n"
                )
            else:
                console.print("[yellow]Application not found[/yellow]\n")

    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}\n")
        raise click.Abort()


@cli.command("init")
@click.argument("app-name")
@click.option(
    "--domain", prompt="Domain name", help="Domain name for the application"
)
@click.option("--host", prompt="VPS IP/hostname", help="VPS IP address or hostname")
@click.option("--user", prompt="SSH user", default="root", help="SSH user")
@click.option(
    "--ssh-key",
    prompt="SSH key path",
    default="~/.ssh/id_rsa",
    help="Path to SSH private key",
)
@click.option(
    "--email",
    prompt="Email for SSL notifications (optional, press Enter to skip)",
    default="",
    help="Email for Let's Encrypt SSL certificate notifications",
)
@click.option(
    "--port",
    prompt="Application port (optional, press Enter to auto-assign)",
    default=0,
    type=int,
    help="Port the application listens on",
)
def init(
    app_name: str, domain: str, host: str, user: str, ssh_key: str, email: str, port: int
) -> None:
    """Initialize a new docklift configuration file."""
    config_path = Path("docklift.yml")

    if config_path.exists():
        if not click.confirm("docklift.yml already exists. Overwrite?"):
            console.print("[yellow]Aborted[/yellow]")
            return

    # Generate configuration lines
    email_line = f"  email: {email}" if email.strip() else "  # email: admin@example.com  # Optional: for Let's Encrypt notifications"
    port_line = f"  port: {port}" if port != 0 else "  # port: 3000  # Optional: auto-assigned if not specified"

    config_template = f"""vps:
  host: {host}
  user: {user}
  ssh_key_path: {ssh_key}
  port: 22
{email_line}

application:
  name: {app_name}
  domain: {domain}
  dockerfile: ./Dockerfile
  context: .
{port_line}
  environment:
    # Add non-sensitive environment variables here
    # NODE_ENV: production
  # env_file: .env  # Optional: load secrets from .env file
  dependencies:
    # Add dependency services here (databases, caches, etc.)
    # Example:
    # postgres:
    #   image: postgres:16-alpine
    #   environment:
    #     POSTGRES_DB: myapp
    #     POSTGRES_USER: myapp
    #     POSTGRES_PASSWORD: changeme
    #   volumes:
    #     - postgres_data:/var/lib/postgresql/data
"""

    with open(config_path, "w") as f:
        f.write(config_template)

    console.print(f"\n[green]✓ Created {config_path}[/green]")
    console.print("\n[cyan]Next steps:[/cyan]")
    console.print("1. Review and edit docklift.yml")
    console.print("2. Run: [bold]docklift bootstrap[/bold]")
    console.print("3. Run: [bold]docklift deploy[/bold]\n")


def main() -> None:
    """Main entry point."""
    cli()

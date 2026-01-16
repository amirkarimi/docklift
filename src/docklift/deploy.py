"""Deploy application to VPS."""

import tarfile
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import Any

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .bootstrap import DOCKLIFT_DIR, SHARED_NETWORK, update_caddyfile
from .config import ApplicationConfig, ServiceConfig
from .connection import VPSConnection

console = Console()


def deploy(conn: VPSConnection, app_config: ApplicationConfig) -> None:
    """Deploy application to VPS.

    This is idempotent and can be run multiple times safely.

    Args:
        conn: VPS connection
        app_config: Application configuration
    """
    console.print(f"\n[bold cyan]Deploying {app_config.name}[/bold cyan]\n")

    # Auto-assign port if not specified
    if app_config.port is None:
        app_config.port = _auto_assign_port(conn, app_config.name)
        console.print(f"[cyan]Auto-assigned port: {app_config.port}[/cyan]")

    # Show environment info
    if app_config.env_file:
        env_path = Path(app_config.env_file).expanduser()
        if env_path.exists():
            console.print(f"[cyan]Loading environment from: {app_config.env_file}[/cyan]")
        else:
            console.print(f"[yellow]Warning: env_file specified but not found: {app_config.env_file}[/yellow]")

    app_dir = f"{DOCKLIFT_DIR}/apps/{app_config.name}"

    # Create application directory
    _create_app_directory(conn, app_dir)

    # Upload application context
    _upload_app_context(conn, app_config, app_dir)

    # Generate and upload docker-compose.yml
    _create_app_compose_file(conn, app_config, app_dir)

    # Build and start application
    _build_and_start_app(conn, app_dir)

    # Update Caddy configuration
    update_caddyfile(
        conn, app_config.domain, f"{app_config.name}-app", app_config.port
    )

    # Test deployment
    _test_deployment(conn, app_config)

    console.print(
        f"\n[bold green]✓ {app_config.name} deployed successfully![/bold green]"
    )
    console.print(f"[green]Application available at: https://{app_config.domain}[/green]\n")


def _auto_assign_port(conn: VPSConnection, current_app_name: str) -> int:
    """Auto-assign port by finding the highest used port and incrementing.

    Args:
        conn: VPS connection
        current_app_name: Name of the current app being deployed

    Returns:
        Assigned port number (starts at 3000)
    """
    apps_dir = f"{DOCKLIFT_DIR}/apps"

    # Check if apps directory exists
    if not conn.dir_exists(apps_dir):
        return 3000

    # Get list of all app directories
    result = conn.run(f"ls -1 {apps_dir} 2>/dev/null || true", hide=True)
    app_names = [name.strip() for name in result.stdout.strip().split("\n") if name.strip()]

    if not app_names:
        return 3000

    max_port = 2999  # Start before 3000

    # Read each app's docker-compose.yml to find their ports
    for app_name in app_names:
        compose_file = f"{apps_dir}/{app_name}/docker-compose.yml"
        if not conn.file_exists(compose_file):
            continue

        # Download and parse compose file
        with NamedTemporaryFile(mode="w+", suffix=".yml", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            conn.connection.get(compose_file, tmp_path)

            with open(tmp_path) as f:
                compose_data = yaml.safe_load(f)

            # Look for 'expose' in the app service
            if compose_data and "services" in compose_data:
                app_service = compose_data["services"].get("app", {})
                expose_list = app_service.get("expose", [])

                for port_spec in expose_list:
                    try:
                        port = int(str(port_spec).split("/")[0])  # Handle "3000/tcp"

                        # Return the same port if it's the current app
                        if app_name == current_app_name:
                            return port

                        max_port = max(max_port, port)
                    except (ValueError, AttributeError):
                        pass

        except Exception:
            # If we can't read the file, skip it
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    return max_port + 1


def _create_app_directory(conn: VPSConnection, app_dir: str) -> None:
    """Create application directory on VPS.

    Args:
        conn: VPS connection
        app_dir: Application directory path
    """
    console.print("[cyan]Creating application directory...[/cyan]")

    if not conn.dir_exists(app_dir):
        conn.run(f"mkdir -p {app_dir}")
        console.print(f"[green]✓ Created {app_dir}[/green]")
    else:
        console.print("[green]✓ Directory exists[/green]")


def _upload_app_context(
    conn: VPSConnection, app_config: ApplicationConfig, app_dir: str
) -> None:
    """Upload application build context to VPS.

    Args:
        conn: VPS connection
        app_config: Application configuration
        app_dir: Remote application directory
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Uploading application context...[/cyan]"),
        console=console,
    ) as progress:
        progress.add_task("upload", total=None)

        context_path = Path(app_config.context).resolve()
        if not context_path.exists():
            raise FileNotFoundError(f"Context path not found: {context_path}")

        # Create tarball of context
        with TemporaryDirectory() as tmpdir:
            tarball_path = Path(tmpdir) / "context.tar.gz"

            with tarfile.open(tarball_path, "w:gz") as tar:
                tar.add(context_path, arcname=".")

            # Upload tarball
            remote_tarball = f"{app_dir}/context.tar.gz"
            conn.put(str(tarball_path), remote_tarball)

            # Extract on VPS
            conn.run(f"cd {app_dir} && tar -xzf context.tar.gz && rm context.tar.gz")

    console.print("[green]✓ Application context uploaded[/green]")


def _create_app_compose_file(
    conn: VPSConnection, app_config: ApplicationConfig, app_dir: str
) -> None:
    """Generate and upload docker-compose.yml for application.

    Args:
        conn: VPS connection
        app_config: Application configuration
        app_dir: Remote application directory
    """
    console.print("[cyan]Creating docker-compose.yml...[/cyan]")

    compose_content = _generate_app_compose(app_config)

    # Upload compose file
    with NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as tmp:
        yaml.dump(compose_content, tmp, default_flow_style=False)
        tmp_path = tmp.name

    try:
        remote_compose = f"{app_dir}/docker-compose.yml"
        conn.put(tmp_path, remote_compose)
        console.print("[green]✓ docker-compose.yml created[/green]")
    finally:
        Path(tmp_path).unlink()


def _generate_app_compose(app_config: ApplicationConfig) -> dict[str, Any]:
    """Generate docker-compose configuration for application.

    Args:
        app_config: Application configuration

    Returns:
        Docker compose configuration as dict
    """
    services: dict[str, Any] = {}

    # Add dependency services (databases, caches, etc.)
    for dep_name, dep_config in app_config.dependencies.items():
        services[dep_name] = _service_config_to_compose(dep_config)

    # Add main application service
    app_service: dict[str, Any] = {
        "build": {
            "context": ".",
            "dockerfile": app_config.dockerfile,
        },
        "container_name": f"{app_config.name}-app",
        "restart": "unless-stopped",
        "environment": app_config.get_merged_environment(),
        "networks": [SHARED_NETWORK],
        "expose": [str(app_config.port)],
    }

    if app_config.dependencies:
        app_service["depends_on"] = list(app_config.dependencies.keys())

    services["app"] = app_service

    # Compose file structure
    compose: dict[str, Any] = {
        "services": services,
        "networks": {
            SHARED_NETWORK: {"external": True},
        },
    }

    return compose


def _service_config_to_compose(
    config: ServiceConfig
) -> dict[str, Any]:
    """Convert ServiceConfig to docker-compose service definition.

    Args:
        name: Service name
        config: Service configuration

    Returns:
        Docker compose service definition
    """
    service: dict[str, Any] = {}

    if config.image:
        service["image"] = config.image

    if config.environment:
        service["environment"] = config.environment

    if config.volumes:
        service["volumes"] = config.volumes

    if config.ports:
        service["ports"] = config.ports

    if config.depends_on:
        service["depends_on"] = config.depends_on

    # Add restart policy by default
    service["restart"] = "unless-stopped"

    # Add to shared network
    service["networks"] = [SHARED_NETWORK]

    # Merge any extra configuration
    service.update(config.extra)

    return service


def _build_and_start_app(
    conn: VPSConnection, app_dir: str
) -> None:
    """Build and start application using docker compose.

    Args:
        conn: VPS connection
        app_config: Application configuration
        app_dir: Remote application directory
    """
    console.print("[cyan]Building and starting application...[/cyan]")

    # Pull dependency images
    console.print("[cyan]Pulling dependency images...[/cyan]")
    conn.run(f"cd {app_dir} && docker compose pull", warn=True)

    # Build application image
    console.print("[cyan]Building application image...[/cyan]")
    result = conn.run(f"cd {app_dir} && docker compose build app")

    if not result.ok:
        raise RuntimeError("Failed to build application image")

    console.print("[green]✓ Application image built[/green]")

    # Start services with force-recreate
    console.print("[cyan]Starting services...[/cyan]")
    result = conn.run(f"cd {app_dir} && docker compose up -d --force-recreate")

    if not result.ok:
        raise RuntimeError("Failed to start services")

    console.print("[green]✓ Services started[/green]")


def _test_deployment(conn: VPSConnection, app_config: ApplicationConfig) -> None:
    """Test that application is reachable via its domain.

    Args:
        conn: VPS connection
        app_config: Application configuration
    """
    console.print(f"[cyan]Testing deployment at {app_config.domain}...[/cyan]")

    # Wait a bit for services to start
    import time

    time.sleep(2)

    # Check if app container is running
    result = conn.run(
        f"docker ps --filter name={app_config.name}-app --format '{{{{.Status}}}}'",
        hide=True,
    )

    if "Up" not in result.stdout:
        console.print("[red]✗ Application container is not running[/red]")
        # Show logs for debugging
        conn.run(f"docker logs {app_config.name}-app")
        raise RuntimeError("Application failed to start")

    console.print("[green]✓ Application container is running[/green]")

    # Test HTTP connectivity from VPS
    result = conn.run(
        f"curl -f -s -o /dev/null -w '%{{http_code}}' http://localhost:80 -H 'Host: {app_config.domain}' || echo 'failed'",
        warn=True,
        hide=True,
    )

    if "failed" in result.stdout or result.stdout.strip() not in ["200", "301", "302", "308"]:
        console.print(
            f"[yellow]⚠ Could not verify HTTP connectivity (got: {result.stdout.strip()})[/yellow]"
        )
        console.print(
            "[yellow]This may be normal if the application requires HTTPS or returns different status codes[/yellow]"
        )
    else:
        console.print(f"[green]✓ Application responding with HTTP {result.stdout.strip()}[/green]")

    console.print(
        "[cyan]Note: SSL certificates may take a few minutes to provision on first deployment[/cyan]"
    )

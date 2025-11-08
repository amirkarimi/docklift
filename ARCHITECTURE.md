# DockLift Architecture

## Project Structure

```
docklift/
├── src/docklift/
│   ├── __init__.py           # Package entry point
│   ├── cli.py                # CLI interface (Click commands)
│   ├── config.py             # Configuration schema (Pydantic models)
│   ├── connection.py         # SSH connection management (Fabric)
│   ├── bootstrap.py          # VPS bootstrap operations
│   └── deploy.py             # Application deployment operations
├── examples/
│   ├── docklift.example.yml  # Example configuration
│   ├── Dockerfile.node       # Example Node.js Dockerfile
│   └── Dockerfile.python     # Example Python Dockerfile
├── pyproject.toml            # Project metadata and dependencies
├── uv.lock                   # Locked dependencies
└── README.md                 # User documentation
```

## Core Components

### 1. Configuration (`config.py`)

Uses Pydantic for type-safe configuration validation:

- **VPSConfig**: SSH connection details (host, user, key, port)
- **ServiceConfig**: Docker service configuration (image, env, volumes, ports)
- **ApplicationConfig**: Application deployment settings
- **DockLiftConfig**: Root configuration with `from_yaml()` loader

### 2. SSH Connection (`connection.py`)

Wraps Fabric Connection with convenience methods:

- Context manager for automatic connection/cleanup
- Helper methods: `run()`, `sudo()`, `put()`, `file_exists()`, `dir_exists()`, `command_exists()`
- Rich console output for user feedback

### 3. Bootstrap (`bootstrap.py`)

Sets up VPS infrastructure (idempotent):

**Operations:**
1. Install Docker and Docker Compose (if not present)
2. Create shared network `docklift-network`
3. Setup Caddy reverse proxy with automatic HTTPS
4. Create `/opt/docklift/` directory structure

**Key Functions:**
- `bootstrap()`: Main entry point
- `_install_docker()`: Docker installation
- `_create_shared_network()`: Network setup
- `_setup_caddy()`: Caddy configuration
- `update_caddyfile()`: Add application routes

### 4. Deploy (`deploy.py`)

Deploys applications to VPS (idempotent):

**Operations:**
1. Create application directory
2. Upload application context (as tarball)
3. Generate docker-compose.yml
4. Build Docker image on VPS
5. Start services with `--force-recreate`
6. Update Caddy configuration
7. Test deployment

**Key Functions:**
- `deploy()`: Main entry point
- `_upload_app_context()`: Compress and upload code
- `_generate_app_compose()`: Create docker-compose configuration
- `_build_and_start_app()`: Build and start containers
- `_test_deployment()`: Verify application health

### 5. CLI (`cli.py`)

Click-based command-line interface:

**Commands:**
- `init`: Initialize configuration file (interactive)
- `bootstrap`: Bootstrap VPS infrastructure
- `deploy`: Deploy application
- `status`: Check application status
- `remove`: Remove application

Each command includes:
- Rich formatted output
- Error handling with click.Abort()
- Configuration loading
- VPS connection context management

## Workflow

### First-Time Setup

```
User → docklift init
     → docklift bootstrap
     → docklift deploy
```

1. **Init**: Creates `docklift.yml` configuration
2. **Bootstrap** (once per VPS):
   - Installs Docker
   - Creates shared network
   - Starts Caddy reverse proxy
3. **Deploy** (per application):
   - Uploads code
   - Builds Docker image
   - Starts containers
   - Configures routing

### Subsequent Deployments

```
User → docklift deploy
```

- Uploads new code
- Rebuilds image
- Recreates containers
- Updates Caddy if domain changed

## Network Architecture

```
Internet (80/443)
    ↓
Caddy (docklift-caddy)
    ↓
docklift-network (Docker bridge network)
    ↓
    ├─→ app1-app:3000 (app1.example.com)
    ├─→ app2-app:8000 (app2.example.com)
    └─→ app3-app:4000 (app3.example.com)
```

### Key Features:

- **Single Entry Point**: Caddy handles all HTTP/HTTPS traffic
- **Automatic SSL**: Caddy obtains and renews Let's Encrypt certificates
- **Isolation**: Each app in separate compose project
- **Discovery**: Apps communicate via container names on shared network
- **No Port Conflicts**: Apps only expose ports internally

## VPS Directory Structure

```
/opt/docklift/
├── caddy-compose.yml           # Caddy reverse proxy service
├── Caddyfile                   # Caddy configuration (auto-updated)
└── apps/
    ├── app1/
    │   ├── docker-compose.yml  # App1 services
    │   ├── Dockerfile          # Uploaded from context
    │   └── [app files]         # Application code
    └── app2/
        ├── docker-compose.yml  # App2 services
        ├── Dockerfile
        └── [app files]
```

## Docker Compose Generation

### Caddy Compose File

```yaml
version: '3.8'
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"  # HTTP/3
    volumes:
      - /opt/docklift/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - docklift-network
networks:
  docklift-network:
    external: true
```

### Application Compose File

```yaml
version: '3.8'
services:
  # Dependency services (databases, caches, etc.)
  postgres:
    image: postgres:16-alpine
    environment: {...}
    volumes: [...]
    networks: [docklift-network]

  # Main application
  app:
    build:
      context: .
      dockerfile: ./Dockerfile
    container_name: myapp-app
    restart: unless-stopped
    environment: {...}
    networks: [docklift-network]
    expose: [3000]
    depends_on: [postgres]

networks:
  docklift-network:
    external: true
```

## Idempotency

All operations are designed to be idempotent:

### Bootstrap
- Docker installation: Checks if `docker` command exists
- Network creation: Checks if network already exists
- Caddy setup: Overwrites files, recreates container

### Deploy
- Directory creation: Creates if missing, reuses if exists
- Code upload: Always uploads fresh code
- Docker build: Always rebuilds image
- Container start: Uses `--force-recreate` flag
- Caddy config: Only adds domain if not present

## Error Handling

- **Configuration Errors**: Pydantic validation with clear messages
- **Connection Errors**: Fabric exceptions caught in CLI commands
- **Command Failures**: `warn=True` for non-critical operations
- **Rich Tracebacks**: Detailed error output with `rich.traceback`

## Security Considerations

### Current Implementation
- SSH key-based authentication (no passwords)
- Automatic HTTPS via Let's Encrypt
- No hardcoded credentials
- Environment variables for secrets

### Areas for Improvement
- Secrets management (consider vault integration)
- SSH key permissions validation
- Network security groups
- Container security scanning
- Rate limiting on Caddy

## Dependencies

### Runtime
- `fabric>=3.2.2`: SSH operations
- `pyyaml>=6.0.1`: YAML parsing
- `rich>=13.7.0`: Terminal output
- `pydantic>=2.5.0`: Configuration validation
- `click>=8.1.7`: CLI framework

### System Requirements
- Python 3.12+
- SSH access to VPS
- VPS: Linux with systemd (Ubuntu/Debian recommended)
- VPS: Internet access for Docker installation

## Testing Considerations

### Manual Testing Checklist
- [ ] Init creates valid configuration
- [ ] Bootstrap on fresh VPS
- [ ] Bootstrap on already-bootstrapped VPS (idempotency)
- [ ] Deploy first application
- [ ] Deploy second application to same VPS
- [ ] Redeploy existing application (idempotency)
- [ ] Status command shows correct info
- [ ] Remove application
- [ ] SSL certificate generation (may take few minutes)

### Future Automated Testing
- Unit tests for configuration parsing
- Mock SSH connections for integration tests
- Docker-in-Docker for E2E testing
- Test fixtures with sample applications

## Future Enhancements

### Planned Features
- [ ] Environment variables from `.env` files
- [ ] Database migration support
- [ ] Backup and restore commands
- [ ] Log streaming (`docklift logs`)
- [ ] Scaling support (multiple container instances)
- [ ] CI/CD integration examples
- [ ] Rollback functionality
- [ ] Health check configuration
- [ ] Custom domain SSL (not just Let's Encrypt)
- [ ] Monitoring and alerting integration

### Performance Optimizations
- [ ] Incremental context uploads (rsync)
- [ ] Docker layer caching
- [ ] Parallel deployments
- [ ] Build caching strategies

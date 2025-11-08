# Quick Start Guide

This guide will help you deploy your first application with DockLift in under 10 minutes.

## Prerequisites

- A VPS running Ubuntu 20.04+ or Debian 11+ (fresh install is fine)
- SSH access to the VPS with key-based authentication
- A domain name with DNS pointing to your VPS IP address
- Python 3.12+ installed locally
- Your application in a directory with a Dockerfile

## Step 1: Install DockLift (On your local machine)

Using UV (recommended):

```bash
uv tool install docklift
```

Or using pip:

```bash
pip install docklift
```

Verify installation:

```bash
docklift --version
```

## Step 2: Prepare Your Application

Make sure your application directory has:

1. A `Dockerfile` that builds your application
2. All necessary application code

Example Node.js app structure:
```
myapp/
├── Dockerfile
├── package.json
├── package-lock.json
└── src/
    └── index.js
```

Example Dockerfile (Node.js):
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3000
CMD ["npm", "start"]
```

## Step 3: Initialize Configuration

Navigate to your application directory and run the interactive wizard:

```bash
cd myapp
docklift init
```

The wizard will prompt you for:
- **App name**: e.g., `myapp` (lowercase, no spaces)
- **Domain name**: e.g., `myapp.example.com`
- **Application port**: The port your app listens on, or press Enter to auto-assign
- **VPS IP/hostname**: e.g., `192.168.1.100`
- **SSH user**: e.g., `root` or `ubuntu`
- **SSH key path**: e.g., `~/.ssh/id_rsa`
- **Email**: For SSL certificate notifications (optional, press Enter to skip)

**Note**: If you skip the port, DockLift will automatically assign ports starting at 3000 and incrementing for each new application.

Alternatively, provide all values as arguments to skip prompts:

```bash
docklift init myapp --domain myapp.example.com --host 192.168.1.100 --port 3000
```

This creates a `docklift.yml` file.

## Step 4: Review Configuration

Edit `docklift.yml` to add environment variables or dependencies:

```yaml
vps:
  host: 192.168.1.100
  user: root
  ssh_key_path: ~/.ssh/id_rsa
  port: 22

application:
  name: myapp
  domain: myapp.example.com
  dockerfile: ./Dockerfile
  context: .
  port: 3000

  environment:
    NODE_ENV: production
    DATABASE_URL: postgres://myapp:password@postgres:5432/myapp

  dependencies:
    postgres:
      image: postgres:16-alpine
      environment:
        POSTGRES_DB: myapp
        POSTGRES_USER: myapp
        POSTGRES_PASSWORD: your_secure_password
      volumes:
        - postgres_data:/var/lib/postgresql/data
```

## Step 5: Bootstrap VPS

This is a one-time setup per VPS:

```bash
docklift bootstrap
```

This will:
- Install Docker and Docker Compose
- Set up Caddy reverse proxy
- Create shared network infrastructure

**Note**: This may take 2-3 minutes on a fresh VPS.

## Step 6: Deploy Application

```bash
docklift deploy
```

This will:
- Upload your application code
- Build the Docker image on the VPS
- Start your application and dependencies
- Configure Caddy for automatic HTTPS

**Note**: SSL certificates may take a few minutes to provision on first deployment.

## Step 7: Verify Deployment

Check application status:

```bash
docklift status
```

Visit your domain:

```bash
https://myapp.example.com
```

## Common Next Steps

### Update Your Application

After making code changes, simply run:

```bash
docklift deploy
```

This will rebuild and restart your application.

### Add Environment Variables

Edit `docklift.yml` and add to the `environment` section:

```yaml
environment:
  API_KEY: your-api-key
  DEBUG: "false"
```

Then redeploy:

```bash
docklift deploy
```

### Add a Database

Edit `docklift.yml` and add to `dependencies`:

```yaml
dependencies:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: mydb
      POSTGRES_USER: myuser
      POSTGRES_PASSWORD: secure_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
```

Update your app's `DATABASE_URL` in the environment section:

```yaml
environment:
  DATABASE_URL: postgres://myuser:secure_password@postgres:5432/mydb
```

Redeploy:

```bash
docklift deploy
```

### Deploy Multiple Apps

Each app needs its own configuration file. Use subdirectories:

```
projects/
├── app1/
│   ├── docklift.yml  (domain: app1.example.com)
│   └── [app files]
└── app2/
    ├── docklift.yml  (domain: app2.example.com)
    └── [app files]
```

Bootstrap the VPS once, then deploy each app:

```bash
# From app1/
docklift bootstrap
docklift deploy

# From app2/
docklift deploy --skip-bootstrap
```

### View Logs

SSH into your VPS and use docker commands:

```bash
ssh user@your-vps
docker logs myapp-app
docker logs -f myapp-app  # Follow logs
```

Or use DockLift status:

```bash
docklift status
```

### Remove Application

To completely remove an application:

```bash
docklift remove
```

To also remove data volumes:

```bash
docklift remove --remove-volumes
```

## Troubleshooting

### Connection Failed

If you get SSH connection errors:

1. Verify SSH key path: `ls -la ~/.ssh/`
2. Test manual SSH: `ssh -i ~/.ssh/id_rsa user@host`
3. Check VPS firewall allows SSH (port 22)

### Domain Not Resolving

1. Verify DNS is configured: `dig myapp.example.com`
2. Wait for DNS propagation (can take up to 24 hours)
3. Check domain points to correct IP address

### SSL Certificate Not Working

1. Verify domain DNS is correct and propagated
2. Wait a few minutes for Let's Encrypt provisioning
3. Check Caddy logs: `ssh user@vps 'docker logs docklift-caddy'`
4. Ensure ports 80 and 443 are open in firewall

### Application Not Starting

Check application logs:

```bash
docklift status  # Shows recent logs
```

Or SSH and check:

```bash
ssh user@vps
docker logs myapp-app
docker ps -a  # Check container status
```

Common issues:
- Wrong port in configuration
- Missing environment variables
- Database connection issues
- Application code errors

### Port Already in Use

If you get port conflicts:
- Each application should have a unique name
- Applications only expose ports internally (no conflicts)
- If Caddy won't start, check if another service uses 80/443

## Next Steps

- Read the full [README.md](README.md) for all features
- Check [examples/](examples/) for more configuration examples
- Review [ARCHITECTURE.md](ARCHITECTURE.md) to understand how it works

## Getting Help

- Check existing issues: https://github.com/yourusername/docklift/issues
- Open a new issue with:
  - Your `docklift.yml` (remove sensitive data)
  - Error messages
  - VPS operating system
  - Steps to reproduce

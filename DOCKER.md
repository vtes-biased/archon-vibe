# Docker Setup Guide

## Overview

The Archon project uses Docker to containerize the entire stack:
- **Frontend**: Svelte + TypeScript PWA with Rust WASM engine
- **Backend**: FastAPI + Python with Rust Python bindings
- **Database**: PostgreSQL 17

## Quick Start

```bash
# Build engine artifacts + Docker images, then start all services
just docker-build
just docker-up

# View logs
just docker-logs

# Access services
# Frontend: http://localhost:3000
# Backend: http://localhost:8000
# Database: localhost:5432
```

**Note**: `just docker-build` automatically builds the Rust engine artifacts first (Python wheel + WASM).

## Architecture

### Build Strategy

The Rust engine is **built locally first**, then the artifacts are copied into Docker images. This approach:
- Speeds up Docker builds (no Rust toolchain needed in containers)
- Improves build caching
- Allows testing engine builds independently

### Frontend Dockerfile (`frontend/Dockerfile`)

Two-stage build:
1. **Stage 1**: Build Svelte app with pre-built WASM package
2. **Stage 2**: Serve with nginx

**Prerequisites**: `engine/pkg/` must exist (built with `wasm-pack`)

### Backend Dockerfile (`backend/Dockerfile`)

Single-stage build:
- Install Python dependencies
- Copy and install pre-built Python wheel
- Run FastAPI with uvicorn

**Prerequisites**: `engine/target/wheels/*.whl` must exist (built with `maturin`)

### Build Artifacts

The following artifacts must be built locally before Docker builds:

| Artifact | Command | Used By |
|----------|---------|---------|
| `engine/target/wheels/*.whl` | `maturin build --release` | Backend |
| `engine/pkg/` | `wasm-pack build --target web --release` | Frontend |

These artifacts are:
- Excluded from `.gitignore` (regenerated locally)
- Included in Docker context (via `.dockerignore` allowlist)
- Built automatically by `just docker-build` commands

### Docker Compose (`docker-compose.yml`)

Services:
- **db**: PostgreSQL 17 with persistent volume
- **backend**: FastAPI server (depends on db)
- **frontend**: nginx serving the PWA (depends on backend)

## Available Commands

All Docker commands are available through `just`:

```bash
# Build engine artifacts (local builds, not in Docker)
just build-engine              # Build both Python wheel + WASM
just build-engine-python       # Build Python wheel only
just build-engine-wasm         # Build WASM only

# Build Docker images (engine artifacts built automatically as prerequisite)
just docker-build              # Build all images (+ engine)
just docker-build-backend      # Build backend only (+ Python wheel)
just docker-build-frontend     # Build frontend only (+ WASM)

# Run
just docker-up                 # Start in background
just docker-up-logs            # Start with logs visible

# Stop
just docker-down               # Stop services
just docker-down-volumes       # Stop and remove volumes

# Monitor
just docker-logs               # All logs
just docker-logs-backend       # Backend logs only
just docker-logs-frontend      # Frontend logs only
just docker-logs-db            # Database logs only
just docker-ps                 # Service status

# Access
just docker-shell-backend      # Backend shell
just docker-shell-db           # Database shell

# Maintenance
just docker-restart            # Restart all services
just docker-clean              # Remove all Docker resources
just docker-rebuild            # Full rebuild
```

## Environment Variables

### Backend

- `DATABASE_URL`: PostgreSQL connection string
- `ENVIRONMENT`: `development` or `production`

### Frontend

- `VITE_API_URL`: Backend API URL (for build-time configuration)

## Volumes

- `postgres_data`: Persistent PostgreSQL data

## Ports

- `3000`: Frontend web interface
- `8000`: Backend API
- `5432`: PostgreSQL database

## Health Checks

All services include health checks:
- **Database**: `pg_isready`
- **Backend**: HTTP GET `/`
- **Frontend**: nginx status

## Development vs Production

Current setup is development-oriented:
- Backend runs with uvicorn in reload mode (change for production)
- Logs are verbose
- Default passwords (change for production)

For production:
1. Use secrets/env files for sensitive data
2. Configure nginx SSL/TLS
3. Use production-grade uvicorn workers
4. Enable database backups
5. Configure proper log aggregation

## Troubleshooting

### Build fails with "no matches for pattern"

This means the engine artifacts are missing. Build them first:

```bash
# Build engine artifacts
just build-engine

# Or build them separately
just build-engine-python   # For backend
just build-engine-wasm     # For frontend

# Then build Docker images
just docker-build
```

### General build failures

```bash
# Clean and rebuild
just docker-clean
just docker-build
```

### Service won't start

```bash
# Check logs
just docker-logs

# Check service status
just docker-ps
```

### Database connection issues

```bash
# Check database is ready
just docker-logs-db

# Access database directly
just docker-shell-db
```

### Port conflicts

If ports 3000, 8000, or 5432 are already in use, modify `docker-compose.yml`:

```yaml
ports:
  - "3001:80"  # Change 3000 to 3001
```


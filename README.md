# Archon

Web application for managing the VEKN community and tournaments.

## About

**VEKN** (Vampire: Elder Kindred Network) is the international players association for **V:TES** (Vampire: The Eternal Struggle), a multiplayer collectible card game set in the World of Darkness. 

Archon provides tournament organization, player management, and community administration tools for the global V:TES community.

**Game Rules**: https://www.vekn.net/rulebook  
**Tournament Rules**: https://www.vekn.net/tournament-rules

## Features

### Member Management
- Unique numeric VEKN ID for each member
- Sponsorship system (new members sponsored by Princes, NCs, or ICs)
- Privacy controls (member names/ratings visible only to VEKN members)
- Personal data management with role-based permissions

### Organizational Hierarchy
- **Inner Circle (IC)**: Permanent administrators with full system access
- **National Coordinators (NC)**: Appointed by ICs, manage country-level operations
- **Princes**: Appointed by ICs or NCs, organize tournaments
- **Rulemongers**: Rules experts appointed by ICs
- **Judges**: Appointed by Rulemongers, enforce tournament rules
- **Playtest Coordinators (PTC)**: Appointed by ICs, manage card playtesting
- **Playtesters (PT)**: Designated by PTCs, test new cards and mechanics
- **Ethics Committee**: Handle player conduct issues, appointed by ICs

### Tournament Management
- Tournament creation by Princes, NCs, or ICs
- Collaborative organization with any VEKN member
- Player registration and check-in
- Preliminary rounds (tables of 4-5 players)
- Player drop/rejoin between rounds
- Finals table (top 5 players)
- Scoring: Game Wins (GW), Victory Points (VP), Tournament Points (TP)

### Sanctions System

**In-Tournament** (issued by organizers/judges):
- **Caution**: Informative only, tournament-local
- **Warning**: Visible across tournaments for 18 months
- **Disqualification**: Excludes from tournament, visible for 18 months

**Out-of-Tournament** (issued by Ethics Committee or ICs):
- **Suspension**: Up to 18 months
- **Permanent Ban**: Indefinite exclusion

## Technical Architecture

### Offline-First PWA
Archon is designed to work seamlessly online or offline, crucial for tournament venues with poor connectivity.

### Stack
- **Frontend**: Svelte + TypeScript + Vite + Tailwind CSS
- **Backend**: FastAPI + Python + PostgreSQL
- **Shared Core**: Rust (compiled to WASM for frontend, PyO3 for backend)
- **Offline Storage**: IndexedDB
- **Real-time Sync**: Server-Sent Events (SSE)

### Data Model
- All objects stored as JSONB in PostgreSQL
- UUID v7 identifiers (time-ordered)
- Event-driven architecture with business logic in Rust
- Automatic conflict resolution during offline reconciliation

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed technical documentation.

## Development

### Prerequisites

Install these tools before setting up the project:

| Tool | Install | Purpose |
|------|---------|---------|
| **Rust** | [rustup.rs](https://rustup.rs/) | Shared engine (business logic) |
| **Node.js** 18+ | [nvm](https://github.com/nvm-sh/nvm) or [nodejs.org](https://nodejs.org/) | Frontend tooling |
| **uv** | [docs.astral.sh/uv](https://docs.astral.sh/uv/) | Python package manager (auto-installs Python) |
| **just** | [github.com/casey/just](https://github.com/casey/just#installation) | Task runner |
| **Docker** | [Docker Desktop](https://www.docker.com/) or [OrbStack](https://orbstack.dev/) | Database (dev) and deployment |

### Setup

```bash
git clone https://github.com/lionel-panhaleux/archon-cursor.git
cd archon-cursor

# Install all dependencies (Python, Node, Rust, wasm-pack) and build the engine
just update
```

### Running

```bash
# Start everything (database + backend + frontend)
just dev

# Stop all services
just dev-stop
```

- **Frontend**: http://localhost:5173
- **Backend API**: http://localhost:8000
- **Database**: Docker on port 5433

### Useful Commands

```bash
just              # List all commands
just test         # Run all tests (engine + backend + frontend)
just lint         # Lint and auto-fix
just build        # Production build (Docker images)
just dev-reset    # Reset dev database
```

### Docker Deployment

Run the entire stack (frontend, backend, and database) with Docker:

```bash
# Build Docker images
just docker-build

# Start all services
just docker-up

# View logs
just docker-logs

# Stop services
just docker-down

# Full rebuild
just docker-rebuild
```

Services:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **PostgreSQL**: localhost:5432

The Dockerfiles automatically build the Rust engine:
- Python bindings (PyO3) for the backend
- WebAssembly (WASM) for the frontend

## Configuration

### Environment Variables

Copy `.env.example` to `.env` and fill in the values. Most variables are self-explanatory; the sections below cover the ones that require external setup.

### TWDA Auto-PR (Tournament Winning Deck Archive)

When a sanctioned tournament finishes and the winner's decklist is available, Archon can automatically open a Pull Request on the [GiottoVerducci/TWD](https://github.com/GiottoVerducci/TWD) repository.

This uses a **GitHub App** installed on the TWD repo. To set it up:

1. **Register a GitHub App** at https://github.com/settings/apps/new
   - **Name**: e.g. "Archon TWDA Bot"
   - **Homepage URL**: your Archon instance URL
   - **Permissions** (Repository):
     - Contents: **Read & Write** (to create branches and commit deck files)
     - Pull requests: **Read & Write** (to open PRs)
   - No webhook needed (uncheck "Active" under Webhook)
   - **Where can this app be installed?**: "Only on this account" is fine

2. **Generate a private key** on the App settings page. Download the `.pem` file.

3. **Install the App** on the `GiottoVerducci/TWD` repository (or ask the repo owner to install it). Note the **Installation ID** from the URL after installation (`https://github.com/settings/installations/{INSTALLATION_ID}`).

4. **Set the environment variables**:

```bash
# Numeric App ID (visible on the App settings page)
TWDA_GITHUB_APP_ID=123456

# PEM private key: either inline contents or a path to the .pem file
TWDA_GITHUB_PRIVATE_KEY=/path/to/private-key.pem

# Installation ID (numeric, from the installation URL)
TWDA_GITHUB_INSTALLATION_ID=78901234
```

When all three variables are set, Archon will create a branch `archon/{vekn_event_id}` and open a PR with the winner's deck in TWDA format. If the decklist is updated later, the PR is automatically updated. If the variables are not set, this feature is silently skipped.

## License

MIT

## Contributing

This is an Open-Source software, contributions are welcome.

## Contact

For VEKN inquiries, visit [vekn.net](https://www.vekn.net/)


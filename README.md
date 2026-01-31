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
- **uv** (Python package manager): https://docs.astral.sh/uv/
- **Node.js** 18+ (for frontend)
- **PostgreSQL** 15+
- **Rust** 1.70+

Note: uv will automatically install Python 3.11 when you run `uv sync`

### Setup

```bash
# Clone repository
git clone https://github.com/lionel-panhaleux/archon-cursor.git
cd archon-cursor

# Backend setup
# Install dependencies (uv will create venv and install Python 3.11 automatically)
uv sync --dev

# Frontend setup
cd frontend
npm install
cd ..

# Database setup (when schema is ready)
createdb archon
psql archon < schema.sql

# Build Rust core (when implemented)
cd core
cargo build --release
cd ..
```

### Running

```bash
# Start backend
uv run uvicorn src.main:app --app-dir backend --reload

# Start frontend
cd frontend
npm run dev
```

The backend API will be available at `http://localhost:8000`  
The PWA will be available at `http://localhost:5173`

### Development with Just

The project uses [just](https://github.com/casey/just) for task automation:

```bash
# List all available commands
just

# Install all dependencies
just install

# Build all components
just build

# Run backend (development)
just serve-backend

# Run frontend (development)
just serve-frontend

# Run tests
just test

# Lint and format
just lint
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

## License

MIT

## Contributing

This is an Open-Source software, contributions are welcome.

## Contact

For VEKN inquiries, visit [vekn.net](https://www.vekn.net/)


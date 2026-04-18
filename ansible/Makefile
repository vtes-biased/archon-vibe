# ============================================================================
# Archon ansible deploy — local build + remote provision/deploy
# ----------------------------------------------------------------------------
# Build pipeline runs on the dev laptop (macOS supported, Linux x86_64 wheel
# produced via manylinux docker). Build artifacts land in ./build/ and are
# rsynced to the target hosts by the roles.
# ============================================================================

REPO_ROOT := $(abspath $(CURDIR)/..)
BUILD_DIR := $(CURDIR)/build
MANYLINUX := quay.io/pypa/manylinux_2_28_x86_64

ANSIBLE := ansible-playbook

# ---- helpers ---------------------------------------------------------------
.PHONY: help galaxy clean build-all build-engine-wheel build-backend build-bot build-frontend
.PHONY: bootstrap-beta bootstrap-prod database-beta database-prod
.PHONY: deploy-beta deploy-prod upgrade-beta upgrade-prod migrate-postgres-prod
.PHONY: lint dry-beta dry-prod

help:
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

galaxy: ## Install Ansible collection dependencies
	ansible-galaxy collection install -r requirements.yml

clean: ## Remove local build artifacts
	rm -rf $(BUILD_DIR)
	mkdir -p $(BUILD_DIR)

# ---- build -----------------------------------------------------------------
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

build-engine-wheel: | $(BUILD_DIR) ## Build the PyO3 engine wheel for linux x86_64 (manylinux_2_28, cp313)
	cd $(REPO_ROOT) && python scripts/update_cards.py
	# Targets Python 3.13 specifically (no abi3). Both prod and beta run the
	# same uv-managed Python 3.13 (see roles/common/tasks/python.yml), so a
	# single cp313-cp313 wheel is sufficient.
	docker run --rm --platform=linux/amd64 \
	  -v $(REPO_ROOT):/io \
	  -w /io/engine \
	  $(MANYLINUX) \
	  bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh && \
	           /root/.local/bin/uv tool install maturin && \
	           /root/.local/bin/maturin build --release \
	             --compatibility manylinux_2_28 \
	             --interpreter python3.13 \
	             --out /io/ansible/build"

build-backend: | $(BUILD_DIR) ## Build the backend wheel + export pinned requirements
	cd $(REPO_ROOT) && uv build --wheel --out-dir $(BUILD_DIR)
	cd $(REPO_ROOT) && uv export --frozen --no-dev --no-hashes --no-emit-project \
	  -o $(BUILD_DIR)/backend-requirements.txt

build-bot: | $(BUILD_DIR) ## Prepare bot source tree + pinned requirements
	rm -rf $(BUILD_DIR)/bot-src
	cp -R $(REPO_ROOT)/bot/src $(BUILD_DIR)/bot-src
	cd $(REPO_ROOT)/bot && uv pip compile pyproject.toml --no-strip-markers \
	  -o $(BUILD_DIR)/bot-requirements.txt

build-frontend: | $(BUILD_DIR) ## Build the Svelte/Vite PWA (static dist)
	cd $(REPO_ROOT)/frontend && npm ci && npm run build
	rm -rf $(BUILD_DIR)/frontend-dist
	cp -R $(REPO_ROOT)/frontend/build $(BUILD_DIR)/frontend-dist

build-all: build-engine-wheel build-backend build-bot build-frontend ## Build every deployable artifact

# ---- provisioning (first-time or full re-run) ------------------------------
bootstrap-beta: galaxy ## First-time provision: beta (packages, users, firewall, db, services)
	$(ANSIBLE) -i inventories/beta playbooks/site.yml

bootstrap-prod: galaxy ## First-time provision: prod
	$(ANSIBLE) -i inventories/prod playbooks/site.yml

database-beta: ## Install/configure PostgreSQL + archon DB/user on beta
	$(ANSIBLE) -i inventories/beta playbooks/database.yml

database-prod: ## Install/configure PostgreSQL + archon DB/user on prod
	$(ANSIBLE) -i inventories/prod playbooks/database.yml

# ---- app deploy (routine updates) ------------------------------------------
deploy-beta: build-all ## Build artifacts and deploy backend/frontend/bot to beta
	$(ANSIBLE) -i inventories/beta playbooks/deploy.yml

deploy-prod: build-all ## Build artifacts and deploy backend/frontend/bot to prod
	$(ANSIBLE) -i inventories/prod playbooks/deploy.yml

# ---- system maintenance ----------------------------------------------------
# Pass FULL=1 for dist-upgrade (major kernel bumps); REBOOT=1 to actually reboot
# when /var/run/reboot-required is present.
UPGRADE_EXTRA := $(if $(FULL),-e upgrade_full=true) $(if $(REBOOT),-e upgrade_reboot=true)

upgrade-beta: ## apt upgrade + (optional) reboot on beta (FULL=1 REBOOT=1)
	$(ANSIBLE) -i inventories/beta playbooks/upgrade.yml $(UPGRADE_EXTRA)

upgrade-prod: ## apt upgrade + (optional) reboot on prod (FULL=1 REBOOT=1)
	$(ANSIBLE) -i inventories/prod playbooks/upgrade.yml $(UPGRADE_EXTRA)

migrate-postgres-prod: ## One-shot PG16 -> PG17 migration on prod (requires confirmation)
	$(ANSIBLE) -i inventories/prod playbooks/migrate_postgres.yml

# ---- dev / CI --------------------------------------------------------------
lint: galaxy ## yamllint + ansible-lint on the ansible tree
	yamllint -s .
	ansible-lint

dry-beta: galaxy ## Dry-run (check mode) of site.yml against beta
	$(ANSIBLE) -i inventories/beta playbooks/site.yml --check --diff

dry-prod: galaxy ## Dry-run (check mode) of site.yml against prod
	$(ANSIBLE) -i inventories/prod playbooks/site.yml --check --diff

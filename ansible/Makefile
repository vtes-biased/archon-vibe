# ============================================================================
# Archon ansible deploy — remote provision/deploy entrypoints
# ----------------------------------------------------------------------------
# Deployed artifacts are built by GitHub Actions (.github/workflows/
# release-artifacts.yml) and attached to the published Release. The deploy
# playbook fetches them itself (see playbooks/deploy.yml), so CI is the single
# source of deployed builds and the servers never run cargo/maturin/npm/uv.
# `make deploy-*` is just a friendly wrapper over `ansible-playbook`.
#
# The `build-*` targets remain for local development and for deploying a local
# build: `make deploy-beta SOURCE=local` builds everything here (macOS supported;
# Linux engine wheel via manylinux docker) and the playbook deploys build/.
# ============================================================================

REPO_ROOT := $(abspath $(CURDIR)/..)
BUILD_DIR := $(CURDIR)/build
MANYLINUX := quay.io/pypa/manylinux_2_28_x86_64

# Release to deploy; empty = latest published release. Override: RELEASE_TAG=vX.Y.Z
RELEASE_TAG ?=
# deploy-* var passthrough: pin a release and/or deploy a local build-all output.
DEPLOY_VARS := $(if $(RELEASE_TAG),-e release_tag=$(RELEASE_TAG),) $(if $(filter local,$(SOURCE)),-e artifact_source=local,)
LOCAL_BUILD := $(if $(filter local,$(SOURCE)),build-all,)

ANSIBLE := uv run --project $(REPO_ROOT) ansible-playbook
UV_RUN := uv run --project $(REPO_ROOT)

# ---- helpers ---------------------------------------------------------------
.PHONY: help galaxy clean build-all build-engine-wheel build-backend build-bot build-frontend
.PHONY: bootstrap-beta bootstrap-prod database-beta database-prod
.PHONY: deploy-beta deploy-prod upgrade-beta upgrade-prod migrate-postgres-prod
.PHONY: lint dry-beta dry-prod

help:
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

galaxy: ## Install Ansible collection + role dependencies
	$(UV_RUN) ansible-galaxy collection install -r requirements.yml
	$(UV_RUN) ansible-galaxy role install -r requirements.yml -p galaxy_roles

clean: ## Remove local build artifacts
	rm -rf $(BUILD_DIR)
	mkdir -p $(BUILD_DIR)

# ---- build (local development / `SOURCE=local` deploys) --------------------
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

build-engine-wheel: | $(BUILD_DIR) ## Build the PyO3 engine wheel for linux x86_64 (manylinux_2_28, cp313)
	cd $(REPO_ROOT) && python scripts/update_cards.py
	# manylinux_2_28 ships pythons at /opt/python/cp3XX-cp3XX/bin/python3.XX (not on PATH),
	# so we pass the full path. Both servers run the same uv-managed 3.13.
	docker run --rm --platform=linux/amd64 \
	  -v $(REPO_ROOT):/io \
	  -w /io/engine \
	  $(MANYLINUX) \
	  bash -c "curl -LsSf https://astral.sh/uv/install.sh | sh && \
	           /root/.local/bin/uv tool install maturin && \
	           /root/.local/bin/maturin build --release \
	             --compatibility manylinux_2_28 \
	             --interpreter /opt/python/cp313-cp313/bin/python3.13 \
	             --out /io/ansible/build"

build-backend: | $(BUILD_DIR) ## Build the backend wheel + export pinned requirements
	cd $(REPO_ROOT) && uv build --wheel --out-dir $(BUILD_DIR)
	cd $(REPO_ROOT) && uv export --frozen --no-dev --no-hashes --no-emit-project \
	  -o $(BUILD_DIR)/backend-requirements.txt

build-bot: | $(BUILD_DIR) ## Build the bot wheel + export pinned requirements
	cd $(REPO_ROOT)/bot && uv build --wheel --out-dir $(BUILD_DIR)
	cd $(REPO_ROOT)/bot && uv export --frozen --no-dev --no-hashes --no-emit-project \
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
# The playbook self-fetches the Release artifacts. RELEASE_TAG=vX.Y.Z pins a
# release (default: latest); SOURCE=local builds here and deploys that instead.
deploy-beta: $(LOCAL_BUILD) ## Deploy backend/frontend/bot to beta (RELEASE_TAG=… / SOURCE=local)
	$(ANSIBLE) -i inventories/beta playbooks/deploy.yml $(DEPLOY_VARS)

deploy-prod: $(LOCAL_BUILD) ## Deploy backend/frontend/bot to prod (RELEASE_TAG=… / SOURCE=local)
	$(ANSIBLE) -i inventories/prod playbooks/deploy.yml $(DEPLOY_VARS)

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
	$(UV_RUN) yamllint -s .
	$(UV_RUN) ansible-lint

dry-beta: galaxy ## Dry-run (check mode) of site.yml against beta
	$(ANSIBLE) -i inventories/beta playbooks/site.yml --check --diff

dry-prod: galaxy ## Dry-run (check mode) of site.yml against prod
	$(ANSIBLE) -i inventories/prod playbooks/site.yml --check --diff

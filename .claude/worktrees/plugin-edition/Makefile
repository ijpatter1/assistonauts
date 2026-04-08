# ═══════════════════════════════════════════════════════════
# PROJECT CONFIGURATION — change these for each project
# ═══════════════════════════════════════════════════════════
IMAGE_NAME      := assistonauts-sandbox
CONTAINER_NAME  := assistonauts-claude
# ═══════════════════════════════════════════════════════════

#
# Usage:
#   make build       — Build the sandbox Docker image
#   make sandbox     — Start interactive Claude Code session in sandbox
#   make attach      — Reattach to a running sandbox (after crash/disconnect)
#   make shell       — Start a bash shell in the sandbox (for debugging)
#   make prompt P=   — Run a headless prompt (e.g., make prompt P="run npm test")
#   make resume S=   — Resume a named session (e.g., make resume S="phase-1")
#   make stop        — Stop the running sandbox container
#   make clean       — Remove container and image (preserves volumes)
#   make clean-all   — Remove container, image, AND volumes (full reset)
#   make gcp-setup   — Print GCP service account setup instructions
#   make test-fw     — Test firewall rules are working
#   make dev         — Run dev server on HOST (not in Docker)
#
# DEV SERVER NOTE:
# The Docker sandbox does not forward ports. This is intentional —
# the sandbox is for Claude Code, not for serving the app. Run the dev
# server on your host machine with `make dev` and browse localhost.
# File changes from Claude Code (inside Docker) appear instantly on the
# host via the bind mount, so hot reload works normally.

PROJECT_DIR     := $(shell pwd)
HOST_UID        := $(shell id -u)
HOST_GID        := $(shell id -g)

# GCP service account key path (create with: make gcp-setup)
# Mount is conditional — if the file doesn't exist, Docker will skip it gracefully
GCP_SA_KEY     := $(PROJECT_DIR)/secrets/gcp-service-account.json
GCP_MOUNT      := $(shell test -f $(GCP_SA_KEY) && echo '-v $(GCP_SA_KEY):/home/claude/.config/gcloud/service-account.json:ro -e GOOGLE_APPLICATION_CREDENTIALS=/home/claude/.config/gcloud/service-account.json')

# Docker run base command — shared across targets
DOCKER_RUN_BASE := docker run -it --rm \
	--name $(CONTAINER_NAME) \
	--cap-add=NET_ADMIN \
	--cap-add=NET_RAW \
	-v $(PROJECT_DIR):/workspace \
	-v claude-config:/home/claude/.claude \
	-v claude-data:/home/claude/.local/share/claude \
	-e ANTHROPIC_API_KEY \
	$(GCP_MOUNT) \
	-w /workspace \
	$(IMAGE_NAME)

.PHONY: build sandbox attach shell prompt resume stop clean clean-all gcp-setup test-fw dev

## Build the sandbox Docker image
build:
	docker build \
		--build-arg HOST_UID=$(HOST_UID) \
		--build-arg HOST_GID=$(HOST_GID) \
		-t $(IMAGE_NAME) \
		-f sandbox/Dockerfile \
		sandbox/

## Start interactive Claude Code session in sandbox
sandbox: build
	$(DOCKER_RUN_BASE)

## Reattach to a running sandbox container (e.g., after a crash or terminal close)
attach:
	docker exec -it --user claude $(CONTAINER_NAME) claude --dangerously-skip-permissions

## Start a bash shell in the sandbox (for debugging / inspection)
shell: build
	docker run -it --rm \
		--name $(CONTAINER_NAME)-shell \
		--cap-add=NET_ADMIN \
		--cap-add=NET_RAW \
		-v $(PROJECT_DIR):/workspace \
		-e ANTHROPIC_API_KEY \
		-w /workspace \
		--entrypoint /bin/bash \
		$(IMAGE_NAME)

## Run a headless prompt (non-interactive)
## Usage: make prompt P="your prompt here"
prompt: build
	docker run --rm \
		--name $(CONTAINER_NAME)-headless \
		--cap-add=NET_ADMIN \
		--cap-add=NET_RAW \
		-v $(PROJECT_DIR):/workspace \
		-v claude-config:/home/claude/.claude \
		-v claude-data:/home/claude/.local/share/claude \
		-e ANTHROPIC_API_KEY \
		$(GCP_MOUNT) \
		-w /workspace \
		$(IMAGE_NAME) \
		-p "$(P)"

## Resume a named session
## Usage: make resume S="session-name"
resume: build
	docker run -it --rm \
		--name $(CONTAINER_NAME) \
		--cap-add=NET_ADMIN \
		--cap-add=NET_RAW \
		-v $(PROJECT_DIR):/workspace \
		-v claude-config:/home/claude/.claude \
		-v claude-data:/home/claude/.local/share/claude \
		-e ANTHROPIC_API_KEY \
		$(GCP_MOUNT) \
		-w /workspace \
		$(IMAGE_NAME) \
		--resume "$(S)"

## Run the dev server on the HOST machine (not in Docker).
## Override this for your project's dev command.
dev:
	@echo "Configure the 'dev' target in the Makefile for your project."
	@echo "Examples: npm run dev, python -m flask run, cargo watch"
	@exit 1

## Stop the running sandbox container
stop:
	docker stop $(CONTAINER_NAME) 2>/dev/null || true

## Remove container and image (preserves Docker volumes for session continuity)
clean: stop
	docker rm $(CONTAINER_NAME) 2>/dev/null || true
	docker rmi $(IMAGE_NAME) 2>/dev/null || true
	@echo "Container and image removed. Docker volumes preserved."
	@echo "Use 'make clean-all' for a full reset including volumes."

## Full reset — remove container, image, AND Docker volumes
## WARNING: This deletes Claude Code auth tokens, session history, and auto-memory.
## You will need to re-authenticate with /login after a clean-all.
clean-all: clean
	docker volume rm claude-config 2>/dev/null || true
	docker volume rm claude-data 2>/dev/null || true
	@echo "Full reset complete. All Claude Code state removed."

## Print instructions for setting up GCP service account
gcp-setup:
	@echo ""
	@echo "═══════════════════════════════════════════════════════════════"
	@echo "  GCP Service Account Setup for Claude Code Sandbox"
	@echo "═══════════════════════════════════════════════════════════════"
	@echo ""
	@echo "  1. Create a service account:"
	@echo "     gcloud iam service-accounts create claude-code-sandbox \\"
	@echo "       --display-name='Claude Code Sandbox' \\"
	@echo "       --project=YOUR_PROJECT_ID"
	@echo ""
	@echo "  2. Grant required roles (adjust for your project's needs):"
	@echo "     PROJECT=YOUR_PROJECT_ID"
	@echo "     SA=claude-code-sandbox@\$$PROJECT.iam.gserviceaccount.com"
	@echo ""
	@echo "     gcloud projects add-iam-policy-binding \$$PROJECT \\"
	@echo "       --member=serviceAccount:\$$SA --role=roles/bigquery.dataEditor"
	@echo "     gcloud projects add-iam-policy-binding \$$PROJECT \\"
	@echo "       --member=serviceAccount:\$$SA --role=roles/bigquery.jobUser"
	@echo "     gcloud projects add-iam-policy-binding \$$PROJECT \\"
	@echo "       --member=serviceAccount:\$$SA --role=roles/pubsub.editor"
	@echo "     gcloud projects add-iam-policy-binding \$$PROJECT \\"
	@echo "       --member=serviceAccount:\$$SA --role=roles/run.developer"
	@echo "     gcloud projects add-iam-policy-binding \$$PROJECT \\"
	@echo "       --member=serviceAccount:\$$SA --role=roles/storage.objectViewer"
	@echo ""
	@echo "  3. Download the key:"
	@echo "     mkdir -p secrets"
	@echo "     gcloud iam service-accounts keys create secrets/gcp-service-account.json \\"
	@echo "       --iam-account=\$$SA"
	@echo ""
	@echo "  4. Uncomment gcloud in sandbox/Dockerfile"
	@echo "     Uncomment GCLOUD_DOMAINS in sandbox/init-firewall.sh"
	@echo "     Then: make build"
	@echo ""
	@echo "  The Makefile auto-detects secrets/gcp-service-account.json"
	@echo "  and mounts it read-only into the container when present."
	@echo "  The secrets/ directory is gitignored."
	@echo ""
	@test -f $(GCP_SA_KEY) && echo "  ✓ Service account key found at $(GCP_SA_KEY)" || echo "  ✗ No key found at $(GCP_SA_KEY) — follow steps above"
	@echo ""

## Test that the firewall is blocking non-allowlisted traffic
test-fw: build
	@echo "Testing firewall rules..."
	@echo "--- Should SUCCEED (allowlisted) ---"
	docker run --rm \
		--cap-add=NET_ADMIN \
		--cap-add=NET_RAW \
		--entrypoint /bin/bash \
		$(IMAGE_NAME) \
		-c "/usr/local/bin/init-firewall.sh && curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://api.anthropic.com 2>/dev/null && echo ' ✓ api.anthropic.com reachable' || echo ' ✗ api.anthropic.com unreachable'"
	@echo "--- Should FAIL (not allowlisted) ---"
	docker run --rm \
		--cap-add=NET_ADMIN \
		--cap-add=NET_RAW \
		--entrypoint /bin/bash \
		$(IMAGE_NAME) \
		-c "/usr/local/bin/init-firewall.sh && curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://example.com 2>/dev/null && echo ' ✗ example.com reachable (FIREWALL LEAK)' || echo ' ✓ example.com blocked'"
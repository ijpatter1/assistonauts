# Claude Code Sandbox
# Isolated environment for running Claude Code with --dangerously-skip-permissions
#
# Build: make build
# Run:   make sandbox
#
# CONFIGURATION:
# Project settings (.claude/settings.json) load from /workspace/.claude/ via bind mount.
# Claude Code's internal state (auth, session history) persists in /home/claude/.claude/
# via a named Docker volume. These are separate paths that merge at runtime.

FROM node:20-slim

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    curl \
    git \
    jq \
    dnsutils \
    iptables \
    iproute2 \
    ca-certificates \
    gnupg \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code CLI via native installer (recommended over npm).
# The installer puts the binary at ~/.local/bin/claude (i.e., /root/.local/bin/claude
# during build). We copy it to /usr/local/bin so it's accessible after privilege drop.
RUN curl -fsSL https://claude.ai/install.sh | bash && \
    cp /root/.local/bin/claude /usr/local/bin/claude && \
    chmod +x /usr/local/bin/claude && \
    if [ -d /root/.local/share/claude ]; then \
      cp -r /root/.local/share/claude /usr/local/share/claude; \
    fi

# ─────────────────────────────────────────────
# OPTIONAL: Google Cloud CLI
# Uncomment when your project needs GCP access. Adds ~500MB to image.
# ─────────────────────────────────────────────
# RUN curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg | \
#     gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
#     echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | \
#     tee /etc/apt/sources.list.d/google-cloud-sdk.list && \
#     apt-get update && apt-get install -y --no-install-recommends google-cloud-cli && \
#     rm -rf /var/lib/apt/lists/*

# Create non-root user for Claude Code to run as.
# The entrypoint starts as root (for iptables), then drops to this user via runuser.
ARG HOST_UID=1000
ARG HOST_GID=1000
RUN groupadd -g ${HOST_GID} claude && \
    useradd -m -u ${HOST_UID} -g ${HOST_GID} -s /bin/bash claude

# Copy firewall initialization script
COPY init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod +x /usr/local/bin/init-firewall.sh

# Copy entrypoint
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Set working directory
WORKDIR /workspace

# Default to entrypoint — all arguments are forwarded to Claude Code
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

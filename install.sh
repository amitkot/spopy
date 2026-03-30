#!/usr/bin/env bash
set -euo pipefail

# spopy installer
# Downloads spopy (spopy) to ~/.local/bin and ensures uv is available.

REPO="amitkot/spopy"
BRANCH="main"
INSTALL_DIR="${SPOTIFY_INSTALL_DIR:-$HOME/.local/bin}"
BIN_NAME="spopy"
URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}/spopy"

info()  { printf '\033[0;34m%s\033[0m\n' "$*"; }
ok()    { printf '\033[0;32m%s\033[0m\n' "$*"; }
warn()  { printf '\033[0;33m%s\033[0m\n' "$*"; }
err()   { printf '\033[0;31m%s\033[0m\n' "$*" >&2; }

# Check for uv
if ! command -v uv &>/dev/null; then
    warn "uv is not installed. uv is required to run spopy."
    info "Installing uv via the official installer..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Source the env so uv is available in this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        err "Failed to install uv. Please install it manually:"
        err "  curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
    ok "uv installed successfully."
else
    info "uv found: $(uv --version)"
fi

# Create install directory
mkdir -p "$INSTALL_DIR"

# Download spopy
info "Downloading spopy to ${INSTALL_DIR}/${BIN_NAME}..."
curl -fsSL "$URL" -o "${INSTALL_DIR}/${BIN_NAME}"
chmod +x "${INSTALL_DIR}/${BIN_NAME}"
ok "Installed: ${INSTALL_DIR}/${BIN_NAME}"

# Check if install dir is in PATH
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    warn "${INSTALL_DIR} is not in your PATH."
    warn "Add this to your shell profile (~/.bashrc, ~/.zshrc):"
    warn "  export PATH=\"${INSTALL_DIR}:\$PATH\""
fi

ok ""
ok "spopy installed! Get started:"
info "  ${BIN_NAME} auth login"
info "  ${BIN_NAME} play 'bohemian rhapsody'"

#!/bin/sh
# Gumloop CLI installer: curl -fsSL https://gumloop.com/cli/install.sh | sh

set -eu

UV_VERSION="0.11.31"
PYTHON_VERSION="3.12"
INSTALLER_VERSION="1"

GUMLOOP_HOME="${GUMLOOP_INSTALL_DIR:-$HOME/.gumloop}"
VENV_DIR="$GUMLOOP_HOME/venv"
UV_BIN="$GUMLOOP_HOME/bin/uv"
SHIM_DIR="$HOME/.local/bin"
SHIM_PATH="$SHIM_DIR/gumloop"

if [ -t 1 ]; then
    BOLD="$(printf '\033[1m')"
    RED="$(printf '\033[31m')"
    GREEN="$(printf '\033[32m')"
    YELLOW="$(printf '\033[33m')"
    RESET="$(printf '\033[0m')"
else
    BOLD="" RED="" GREEN="" YELLOW="" RESET=""
fi

step() {
    printf '%s==>%s %s\n' "${BOLD}" "${RESET}" "$1"
}

warn() {
    printf '%swarning:%s %s\n' "${YELLOW}" "${RESET}" "$1" >&2
}

fail() {
    printf '%serror:%s %s\n' "${RED}" "${RESET}" "$1" >&2
    exit 1
}

# [ -r /dev/tty ] passes in CI/containers where the open still fails.
has_tty() {
    ( : < /dev/tty ) 2>/dev/null
}

# Prompts read /dev/tty, not stdin: under `curl | sh` stdin is the script.
confirm() {
    if ! has_tty; then
        return 1
    fi
    printf '%s [y/N] ' "$1"
    answer=""
    read -r answer < /dev/tty || { printf '\n'; return 1; }
    case "$answer" in
        y|Y|yes|YES|Yes) return 0 ;;
        *) return 1 ;;
    esac
}

confirm_yes() {
    if ! has_tty; then
        return 0
    fi
    printf '%s [Y/n] ' "$1"
    answer=""
    read -r answer < /dev/tty || { printf '\n'; return 0; }
    case "$answer" in
        n|N|no|NO|No) return 1 ;;
        *) return 0 ;;
    esac
}

if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    fail "do not run this installer with sudo. It installs into your home directory and needs no root access."
fi

case "$(uname -s)" in
    Darwin) os="macos" ;;
    Linux) os="linux" ;;
    *) fail "unsupported operating system: $(uname -s). The Gumloop CLI supports macOS and Linux (use WSL on Windows)." ;;
esac

case "$(uname -m)" in
    x86_64|amd64) arch="x86_64" ;;
    arm64|aarch64) arch="aarch64" ;;
    *) fail "unsupported architecture: $(uname -m)" ;;
esac

if [ "$os" = "macos" ] && [ "$arch" = "x86_64" ]; then
    if [ "$(sysctl -n sysctl.proc_translated 2>/dev/null || true)" = "1" ]; then
        arch="aarch64"
    fi
fi

if [ "$os" = "macos" ]; then
    uv_target="${arch}-apple-darwin"
    platform_label="macOS (${arch})"
else
    libc="gnu"
    if ldd /bin/ls 2>&1 | grep -q musl; then
        libc="musl"
    fi
    uv_target="${arch}-unknown-linux-${libc}"
    platform_label="Linux (${arch}, ${libc})"
fi

downloader=""
if command -v curl >/dev/null 2>&1; then
    downloader="curl"
elif command -v wget >/dev/null 2>&1; then
    downloader="wget"
else
    fail "curl or wget is required to install the Gumloop CLI."
fi

download() {
    url="$1"
    output="$2"
    if [ "$downloader" = "curl" ]; then
        curl -fsSL -o "$output" "$url"
    else
        wget -q -O "$output" "$url"
    fi
}

download_text() {
    url="$1"
    if [ "$downloader" = "curl" ]; then
        curl -fsSL "$url"
    else
        wget -q -O - "$url"
    fi
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | cut -d' ' -f1
    else
        shasum -a 256 "$1" | cut -d' ' -f1
    fi
}

if [ -x "$VENV_DIR/bin/gumloop" ]; then
    install_mode="Updating"
else
    install_mode="Installing"
fi

step "${install_mode} Gumloop CLI"
step "Detected platform: ${platform_label}"

if [ "$install_mode" = "Updating" ]; then
    installed_version="$("$VENV_DIR/bin/gumloop" --version 2>/dev/null || true)"
    if ! confirm_yes "Gumloop CLI${installed_version:+ ${installed_version}} is already installed. Reinstall?"; then
        step "Keeping the existing installation"
        exit 0
    fi
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT INT TERM

existing="$(command -v gumloop 2>/dev/null || true)"
if [ -n "$existing" ] && [ "$existing" != "$SHIM_PATH" ]; then
    case "$(readlink "$existing" 2>/dev/null || echo "$existing")" in
        "$GUMLOOP_HOME"/*) ;;
        *)
            method="pip"
            case "$existing" in
                *pipx*) method="pipx" ;;
                *"/uv/tools/"*) method="uv tool" ;;
            esac
            if confirm "Found existing gumloop at ${existing} (installed via ${method}). Remove it and switch to the managed install?"; then
                step "Removing ${method} install"
                case "$method" in
                    pipx) pipx uninstall gumloop >/dev/null 2>&1 || warn "pipx uninstall failed; remove it manually with: pipx uninstall gumloop" ;;
                    "uv tool") uv tool uninstall gumloop >/dev/null 2>&1 || warn "uv tool uninstall failed; remove it manually with: uv tool uninstall gumloop" ;;
                    pip)
                        shebang_python="$(head -n 1 "$existing" 2>/dev/null | sed 's/^#!//')"
                        if [ -x "$shebang_python" ] && "$shebang_python" -m pip uninstall -y gumloop >/dev/null 2>&1; then
                            :
                        else
                            warn "could not uninstall automatically; remove it manually with: pip uninstall gumloop"
                        fi
                        ;;
                esac
            else
                warn "keeping the existing install; it may shadow the new 'gumloop' command on your PATH."
            fi
            ;;
    esac
fi

uv_asset="uv-${uv_target}.tar.gz"
uv_url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${uv_asset}"

if [ -x "$UV_BIN" ] && [ "$("$UV_BIN" --version 2>/dev/null | cut -d' ' -f2)" = "$UV_VERSION" ]; then
    :
else
    step "Downloading uv ${UV_VERSION}"
    download "$uv_url" "$tmp_dir/$uv_asset"

    expected_sha="$(download_text "${uv_url}.sha256" | cut -d' ' -f1)"
    actual_sha="$(sha256_of "$tmp_dir/$uv_asset")"
    if [ -z "$expected_sha" ] || [ "$expected_sha" != "$actual_sha" ]; then
        fail "checksum verification failed for ${uv_asset}"
    fi

    tar -xzf "$tmp_dir/$uv_asset" -C "$tmp_dir"
    mkdir -p "$GUMLOOP_HOME/bin"
    mv "$tmp_dir/uv-${uv_target}/uv" "$UV_BIN"
    chmod 0755 "$UV_BIN"
fi

if [ -n "${GUMLOOP_VERSION:-}" ]; then
    install_spec="gumloop==${GUMLOOP_VERSION}"
else
    install_spec="gumloop"
fi

export UV_PYTHON_INSTALL_DIR="$GUMLOOP_HOME/python"
export UV_CACHE_DIR="$GUMLOOP_HOME/cache"

step "Installing Python ${PYTHON_VERSION} to ${GUMLOOP_HOME}"
rm -rf "$VENV_DIR"
# Without --managed-python uv silently reuses any system Python it finds.
"$UV_BIN" venv "$VENV_DIR" --python "$PYTHON_VERSION" --managed-python --quiet

step "Installing ${install_spec} from PyPI"
"$UV_BIN" pip install --python "$VENV_DIR/bin/python" --quiet "$install_spec"

version="$("$VENV_DIR/bin/python" -c 'from gumloop import __version__; print(__version__)')"
step "Resolved version: ${version}"

mkdir -p "$SHIM_DIR"
ln -sf "$VENV_DIR/bin/gumloop" "$SHIM_PATH"

cat > "$GUMLOOP_HOME/install.json" <<EOF
{
  "install_method": "installer",
  "installer_version": "${INSTALLER_VERSION}",
  "version": "${version}",
  "installed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}
EOF

"$SHIM_PATH" --version >/dev/null 2>&1 || fail "installed CLI failed to run; try re-running the installer."

case ":$PATH:" in
    *":$SHIM_DIR:"*)
        step "${SHIM_DIR} is already on PATH"
        ;;
    *)
        warn "${SHIM_DIR} is not on your PATH."
        printf '\nAdd it to your shell profile (e.g. ~/.zshrc or ~/.bashrc):\n'
        printf '    export PATH="%s:$PATH"\n\n' "$SHIM_DIR"
        ;;
esac

printf '\n%s✓ Gumloop CLI %s installed successfully.%s\n' "${GREEN}" "${version}" "${RESET}"
printf 'Run %sgumloop --help%s to get started, %sgumloop update%s to update.\n\n' \
    "${BOLD}" "${RESET}" "${BOLD}" "${RESET}"

login_state="$("$VENV_DIR/bin/python" - 2>/dev/null <<'EOF' || true
from gumloop.cli.credentials import is_keyring_available, load_credentials

if load_credentials().has_any:
    print("logged_in")
elif is_keyring_available():
    print("prompt")
else:
    print("no_keyring")
EOF
)"

case "$login_state" in
    logged_in) ;;
    no_keyring)
        printf 'No OS keychain was found, so `gumloop login` cannot store credentials on this machine.\n'
        printf 'Authenticate with environment variables instead (GUMLOOP_API_KEY + GUMLOOP_USER_ID),\n'
        printf 'or install a keychain (e.g. apt install gnome-keyring libsecret-1-0) and run `gumloop login`.\n\n'
        ;;
    *)
        if has_tty && confirm "Log in to Gumloop now?"; then
            "$SHIM_PATH" login < /dev/tty || true
        fi
        ;;
esac

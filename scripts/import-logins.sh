#!/bin/sh
# Bring a site's login from this machine's browser to your Gumloop agents:
#   GUMLOOP_LOGIN_URL='https://app.example.com' sh -c 'curl -fsSL https://gumloop.com/cli/import-logins.sh | sh'
#
# Installs the Gumloop CLI when it is missing (same installer as gumloop.com/cli/install.sh),
# signs you in when needed, then runs `gumloop browser import-logins`. Only cookies for the site
# you name are sent, and only counts are printed. On macOS, the system asks for Keychain access
# to your browser's cookie key; that prompt is the consent step.
#
# Optional:
#   GUMLOOP_BROWSER_PROFILE_ID=<id|name>   target login profile (default: your personal default)
#   GUMLOOP_TEAM_ID=<team_id>              when the target profile belongs to a team
#   GUMLOOP_BROWSER=chrome|brave|edge|arc|chromium|firefox
#   GUMLOOP_INSTALL_URL=<url>              alternative installer (defaults to gumloop.com/cli/install.sh)

set -eu

INSTALL_URL="${GUMLOOP_INSTALL_URL:-https://gumloop.com/cli/install.sh}"
GUMLOOP_HOME="${GUMLOOP_INSTALL_DIR:-$HOME/.gumloop}"
SHIM_PATH="$HOME/.local/bin/gumloop"

if [ -t 1 ]; then
    BOLD="$(printf '\033[1m')"
    RED="$(printf '\033[31m')"
    RESET="$(printf '\033[0m')"
else
    BOLD="" RED="" RESET=""
fi

step() { printf '%s==>%s %s\n' "${BOLD}" "${RESET}" "$1"; }
fail() { printf '%serror:%s %s\n' "${RED}" "${RESET}" "$1" >&2; exit 1; }

# Prompts read /dev/tty, not stdin: under `curl | sh` stdin is the script.
has_tty() { ( : < /dev/tty ) 2>/dev/null; }

prompt() {
    has_tty || fail "$2 is not set and there is no terminal to ask on. Set $2 and re-run."
    printf '%s ' "$1"
    answer=""
    read -r answer < /dev/tty || fail "no input"
    [ -n "$answer" ] || fail "nothing entered"
    printf '%s' "$answer"
}

case "$(uname -s)" in
    Darwin|Linux) ;;
    *) fail "the Gumloop CLI runs on macOS and Linux. On Windows, use the Gumloop Chrome extension from the Secrets page instead." ;;
esac

find_cli() {
    if [ -x "$SHIM_PATH" ]; then
        printf '%s' "$SHIM_PATH"
    elif [ -x "$GUMLOOP_HOME/venv/bin/gumloop" ]; then
        printf '%s' "$GUMLOOP_HOME/venv/bin/gumloop"
    elif command -v gumloop >/dev/null 2>&1; then
        command -v gumloop
    fi
}

CLI="$(find_cli || true)"
if [ -z "$CLI" ]; then
    step "Installing the Gumloop CLI"
    # The installer prompts on /dev/tty itself; GUMLOOP_SKIP_LOGIN keeps it from opening a browser mid-script.
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$INSTALL_URL" | GUMLOOP_SKIP_LOGIN=1 sh
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$INSTALL_URL" | GUMLOOP_SKIP_LOGIN=1 sh
    else
        fail "curl or wget is required"
    fi
    CLI="$(find_cli || true)"
    [ -n "$CLI" ] || fail "the Gumloop CLI did not install; see the messages above."
fi

if ! "$CLI" browser --help >/dev/null 2>&1; then
    step "Updating the Gumloop CLI (this version cannot import logins)"
    "$CLI" update >/dev/null 2>&1 || fail "could not update the Gumloop CLI; run '$CLI update' and retry."
fi

url="${GUMLOOP_LOGIN_URL:-}"
[ -n "$url" ] || url="$(prompt 'Which site should the agent be logged in to (e.g. https://app.example.com)?' GUMLOOP_LOGIN_URL)"

# Env credentials (GUMLOOP_API_KEY + GUMLOOP_USER_ID) work headless; otherwise sign in once.
if [ -z "${GUMLOOP_API_KEY:-}" ] && [ -z "${GUMLOOP_ACCESS_TOKEN:-}" ]; then
    if ! "$CLI" browser profiles list --json >/dev/null 2>&1; then
        step "Signing in to Gumloop"
        has_tty || fail "not signed in and no terminal to sign in on. Set GUMLOOP_API_KEY and GUMLOOP_USER_ID, or run 'gumloop login' first."
        "$CLI" login < /dev/tty
    fi
fi

set -- browser import-logins --url "$url" --yes
[ -n "${GUMLOOP_BROWSER_PROFILE_ID:-}" ] && set -- "$@" --into "$GUMLOOP_BROWSER_PROFILE_ID"
[ -n "${GUMLOOP_TEAM_ID:-}" ] && set -- "$@" --team "$GUMLOOP_TEAM_ID"
[ -n "${GUMLOOP_BROWSER:-}" ] && set -- "$@" --browser "$GUMLOOP_BROWSER"

step "Importing your login for ${url}"
if has_tty; then
    "$CLI" "$@" < /dev/tty
else
    "$CLI" "$@"
fi

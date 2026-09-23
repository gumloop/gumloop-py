#!/bin/sh
# Bring this machine's browser sign-ins into your Gumloop browser profile (every site, cookies only):
#   curl -fsSL https://gumloop.com/cli/import-logins.sh | sh
# One site only:
#   GUMLOOP_LOGIN_URL='https://app.example.com' sh -c 'curl -fsSL https://gumloop.com/cli/import-logins.sh | sh'

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
    step "Updating the Gumloop CLI (this version cannot import sites)"
    "$CLI" update >/dev/null 2>&1 || fail "could not update the Gumloop CLI; run '$CLI update' and retry."
fi

url="${GUMLOOP_LOGIN_URL:-}"

if [ -z "${GUMLOOP_API_KEY:-}" ] && [ -z "${GUMLOOP_ACCESS_TOKEN:-}" ]; then
    if ! "$CLI" browser profiles list --json >/dev/null 2>&1; then
        step "Signing in to Gumloop"
        has_tty || fail "not signed in and no terminal to sign in on. Set GUMLOOP_API_KEY and GUMLOOP_USER_ID, or run 'gumloop login' first."
        "$CLI" login < /dev/tty
    fi
fi

set -- browser import-logins
if [ -n "$url" ]; then
    set -- "$@" --url "$url" --yes
else
    # A whole profile is previewed and confirmed on the terminal; headless runs have already opted in.
    has_tty || set -- "$@" --yes
    for domain in $(printf '%s' "${GUMLOOP_INCLUDE_DOMAINS:-}" | tr ',' ' '); do set -- "$@" --include-domain "$domain"; done
    for domain in $(printf '%s' "${GUMLOOP_EXCLUDE_DOMAINS:-}" | tr ',' ' '); do set -- "$@" --exclude-domain "$domain"; done
fi
[ -n "${GUMLOOP_BROWSER_PROFILE_ID:-}" ] && set -- "$@" --into "$GUMLOOP_BROWSER_PROFILE_ID"
[ -n "${GUMLOOP_TEAM_ID:-}" ] && set -- "$@" --team "$GUMLOOP_TEAM_ID"
[ -n "${GUMLOOP_BROWSER:-}" ] && set -- "$@" --browser "$GUMLOOP_BROWSER"

if [ -n "$url" ]; then
    step "Importing your sign-in for ${url}"
else
    step "Importing your browser's sign-ins"
fi
if has_tty; then
    "$CLI" "$@" < /dev/tty
else
    "$CLI" "$@"
fi

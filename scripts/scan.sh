#!/usr/bin/env bash
# Publish gate for this repo: generic secret scan (gitleaks) + a denylist for
# the specific internal-IP ranges and host/project names this kit's content
# was extracted from. Exit non-zero on any hit -- wired into CI
# (.github/workflows/secret-scan.yml) and meant to be run locally before
# committing (see CONTRIBUTING.md for a pre-commit hook recipe).
#
# Usage: ./scripts/scan.sh            (scans the working tree)
#        ./scripts/scan.sh --staged   (scans only staged changes, for a
#                                       pre-commit hook)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

MODE="${1:-}"
FAIL=0

echo "== gitleaks =="
if command -v gitleaks >/dev/null 2>&1; then
    if [ "$MODE" = "--staged" ]; then
        gitleaks protect --staged --redact --no-banner || FAIL=1
    else
        gitleaks detect --no-git --redact --no-banner --source . || FAIL=1
    fi
elif command -v docker >/dev/null 2>&1; then
    echo "(gitleaks not on PATH, using zricethezav/gitleaks:latest via docker)"
    if [ "$MODE" = "--staged" ]; then
        docker run --rm -v "$PWD":/repo -w /repo zricethezav/gitleaks:latest \
            protect --staged --redact --no-banner || FAIL=1
    else
        docker run --rm -v "$PWD":/repo -w /repo zricethezav/gitleaks:latest \
            detect --no-git --redact --no-banner --source . || FAIL=1
    fi
else
    echo "ERROR: neither gitleaks nor docker is available -- cannot run the secret scanner." >&2
    echo "Install gitleaks (https://github.com/gitleaks/gitleaks#installing) or Docker and retry." >&2
    exit 2
fi

echo
echo "== internal-name / internal-IP denylist =="
# Narrow and literal on purpose: this list exists to catch residue from the
# private source this kit's content was extracted from, NOT to be a general
# secret detector (that's gitleaks' job above). False negatives here are
# expected for anything that isn't this specific kit's own history.
DENYLIST=(
    '10\.0\.10[0-9]\.[0-9]{1,3}'   # the source estate's /23-ish internal range
    '192\.168\.[0-9]{1,3}\.[0-9]{1,3}'
    '172\.(1[6-9]|2[0-9]|3[0-1])\.[0-9]{1,3}\.[0-9]{1,3}'
    'thelodge\.network'
    'thelodge\.cloud'
    'lodge-haos'
    'lodge-bad-boy'
    'lodge-boiler-api'
    'boiler-api\.'
    'Hannibal'
    'Vaultwarden'
    'Directus.*#[0-9]{3,4}'        # internal ticket references
)

HITS=0
for pattern in "${DENYLIST[@]}"; do
    # -I: skip binary, -n: line numbers, -r: recurse, exclude .git/ and this
    # script + the denylist definition itself (which necessarily quotes the
    # patterns it's looking for).
    if grep -rInE "$pattern" . \
        --exclude-dir=.git \
        --exclude="$(basename "${BASH_SOURCE[0]}")" \
        --exclude=.gitleaks.toml 2>/dev/null; then
        echo "  ^-- matched denylist pattern: $pattern"
        HITS=1
    fi
done

if [ "$HITS" -ne 0 ]; then
    echo
    echo "DENYLIST: found residue from the private source estate (see above). Fix before committing."
    FAIL=1
else
    echo "denylist: clean"
fi

if [ "$FAIL" -ne 0 ]; then
    echo
    echo "SCAN FAILED — see findings above."
    exit 1
fi
echo
echo "SCAN CLEAN."

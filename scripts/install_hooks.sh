#!/usr/bin/env bash
# Install the git hooks. Hooks are not tracked by git, so this must be run once
# per clone. It is idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
cat > .git/hooks/pre-commit <<'HOOK'
#!/usr/bin/env bash
# Refuse a commit that moves the frozen protocol without a recorded amendment.
if ! python3 -m study.protocol_lock --quiet; then
    echo ""
    echo "Commit refused: PROTOCOL.md changed without a recorded amendment."
    echo "Append an '### A<n>' entry under '## Amendments', then:"
    echo "    python3 -m study.protocol_lock --accept"
    exit 1
fi
HOOK
chmod +x .git/hooks/pre-commit
echo "Installed .git/hooks/pre-commit"

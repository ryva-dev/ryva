#!/usr/bin/env bash
# Ryva Forge pilot playbook — import → sync → approve → export
# Usage:
#   export RYVA_CLOUD_URL=https://your-cloud.example
#   bash scripts/pilot_playbook.sh /path/to/ryva/project

set -euo pipefail

ROOT="${1:-$(pwd)}"
cd "$ROOT"

if [[ ! -f project.yml ]]; then
  echo "error: project.yml not found in $ROOT" >&2
  exit 1
fi

echo "==> 1/6 Compile local AI system record"
python -m ryva.cli compile

echo "==> 2/6 Generate governance artifacts"
python -m ryva.cli governance report
python -m ryva.cli docs generate 2>/dev/null || true

AGENT=""
if command -v python >/dev/null; then
  AGENT="$(python -m ryva.cli list agents 2>/dev/null | awk 'NR==2 {print $1}' || true)"
fi
if [[ -n "${AGENT}" ]]; then
  python -m ryva.cli modelcard "$AGENT" 2>/dev/null || true
fi

echo "==> 3/6 Sync evidence to Ryva Cloud (authoritative control plane)"
python -m ryva.cli cloud sync

echo "==> 4/6 Request sample approval (technical step)"
if [[ -n "${AGENT}" ]]; then
  python -m ryva.cli approvals request \
    --agent "$AGENT" \
    --step technical \
    --reviewer "Pilot Reviewer" \
    --reviewer-email "reviewer@example.com" \
    --notes "Pilot playbook approval request"
  python -m ryva.cli cloud sync
else
  echo "warn: no agents found; skip approval request"
fi

echo "==> 5/6 Export local audit package (CLI fallback)"
python -m ryva.cli audit export

echo "==> 6/6 Next steps"
cat <<EOF

Pilot checklist complete for: $ROOT

Cloud-authoritative next steps:
  1. Open Ryva Forge dashboard → Systems → complete approval in UI
  2. Compliance → Download org-wide audit package
  3. Record release gate evaluation for staging/production

Docs:
  - docs/DATA_AUTHORITY.md (ryva-cloud)
  - docs/trust/SECURITY_OVERVIEW.md
  - docs/trust/BAA_TEMPLATE.md
EOF

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export PYTHONPATH="${ROOT_DIR}/.."
RYVA_CLI=(python -m ryva.cli)

echo "==> Compiling healthcare-ai-audit-demo"
"${RYVA_CLI[@]}" compile --root "$ROOT_DIR"

echo "==> Generating docs, model card, governance report, and audit package"
"${RYVA_CLI[@]}" docs generate --root "$ROOT_DIR"
"${RYVA_CLI[@]}" modelcard patient_intake_triage_agent --root "$ROOT_DIR"
"${RYVA_CLI[@]}" governance report --root "$ROOT_DIR" || true
"${RYVA_CLI[@]}" lineage verify --all --root "$ROOT_DIR"
"${RYVA_CLI[@]}" lineage search --agent patient_intake_triage_agent --root "$ROOT_DIR"
"${RYVA_CLI[@]}" audit export --root "$ROOT_DIR"

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "==> ANTHROPIC_API_KEY is not set; skipping live model runs and model-dependent tests"
  exit 0
fi

echo "==> Running live demo inputs"
"${RYVA_CLI[@]}" run --root "$ROOT_DIR" --agent patient_intake_triage_agent --input "$(cat "$ROOT_DIR/demo_inputs/routine_appointment_request.json")"
"${RYVA_CLI[@]}" run --root "$ROOT_DIR" --agent patient_intake_triage_agent --input "$(cat "$ROOT_DIR/demo_inputs/urgent_symptom_language.json")"
"${RYVA_CLI[@]}" run --root "$ROOT_DIR" --agent patient_intake_triage_agent --input "$(cat "$ROOT_DIR/demo_inputs/fake_phi_masking_case.json")"

echo "==> Running tests"
"${RYVA_CLI[@]}" test --root "$ROOT_DIR" --agent patient_intake_triage_agent
"${RYVA_CLI[@]}" test --root "$ROOT_DIR" --adversarial --agent patient_intake_triage_agent
"${RYVA_CLI[@]}" test --root "$ROOT_DIR" --hallucination --agent patient_intake_triage_agent
"${RYVA_CLI[@]}" test --root "$ROOT_DIR" --regression --agent patient_intake_triage_agent
"${RYVA_CLI[@]}" test --root "$ROOT_DIR" --fuzz --agent patient_intake_triage_agent
"${RYVA_CLI[@]}" align --root "$ROOT_DIR" --agent patient_intake_triage_agent

echo "==> Live demo completed. To remove generated local artifacts, run:"
echo "    python -m ryva.cli demo reset --root \"$ROOT_DIR\""

# Healthcare AI Governance Template

This project was initialized with Ryva's healthcare template, which includes:

- **HIPAA + EU AI Act policy bundle** — pre-configured alignment policies for healthcare compliance
- **PII masking enabled** — all outputs are scrubbed of protected health information by default
- **Human oversight required** — outputs must include `requires_human_review: true`
- **High-risk AI defaults** — approval workflow requires technical, privacy, compliance, and legal sign-off

## Required Approvals Before Production

This template enforces the full four-step approval workflow:

```bash
# Request technical review
ryva approvals request --agent <name> --step technical --reviewer "Dr. Jane Smith" --reviewer-email jane@hospital.org

# Request privacy review
ryva approvals request --agent <name> --step privacy --reviewer "Privacy Officer" --reviewer-email privacy@hospital.org

# Request compliance review
ryva approvals request --agent <name> --step compliance --reviewer "Compliance Team" --reviewer-email compliance@hospital.org

# Request legal review
ryva approvals request --agent <name> --step legal --reviewer "Legal Counsel" --reviewer-email legal@hospital.org
```

## Compliance Checklist

Before going to production, verify:

- [ ] HIPAA Security Risk Analysis completed (`target/hipaa/security_risk_analysis.md`)
- [ ] PHI data inventory documented (`target/hipaa/phi_inventory.md`)
- [ ] EU AI Act Annex IV technical documentation generated (`ryva docs generate`)
- [ ] Adversarial tests passing (`ryva test --adversarial`)
- [ ] Governance report generated (`ryva governance report`)
- [ ] All four approvals recorded and not stale

## Release Gate Enforcement

```bash
# Check if you're ready for production
ryva status --env production

# Sync to staging (requires technical approval + tests)
ryva cloud sync --env staging --require-approvals

# Sync to production (requires all four approvals, no stale reviews)
ryva cloud sync --env production
```

## Policy Exceptions

If you need to formally accept a known risk gap:

```bash
ryva exceptions create \
  --agent <name> \
  --policy <policy-name> \
  --reason "Business justification" \
  --approved-by "Legal Counsel Name" \
  --expires 2026-12-31
```

All exceptions appear in the audit package and have expiry dates.

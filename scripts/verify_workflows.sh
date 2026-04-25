#!/usr/bin/env bash
# Workflow verifier — runs each cron's primary command in dry-run mode.
# Called by .github/workflows/_workflow_verify.yml on every push.

set -euo pipefail

echo "=== Workflow verifier: lotus-lane ==="

# Daimoku Daily — both phases. --dry-run skips both Resend send AND
# Anthropic call, so safe to run on every push.
echo "--- generate_email --welcome --dry-run ---"
python -m pipeline.generate_email --welcome --dry-run

echo "--- generate_email --regular --dry-run ---"
python -m pipeline.generate_email --regular --dry-run

echo "=== Workflow verifier: all green ==="

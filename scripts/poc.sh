#!/usr/bin/env bash
# Read-only proof of concept against the sample order and payment services.
set -euo pipefail

FRAMEWORK="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$FRAMEWORK/.." && pwd)"
WORK="$FRAMEWORK/.sdd-tmp/poc"
POC_WORKSPACE="$WORK"

rm -rf "$WORK"
mkdir -p "$WORK/repos"
cp -R "$ROOT/examples/order-service" "$WORK/repos/order-service"
cp -R "$ROOT/examples/payment-service" "$WORK/repos/payment-service"

git_init() {
  local repo="$1"
  git -C "$repo" init
  git -C "$repo" add .
  git -C "$repo" -c user.email=sdd@example.com -c user.name=sdd commit -m "baseline"
}

git_init "$WORK/repos/order-service"
git_init "$WORK/repos/payment-service"

cd "$WORK"
uv run --project "$FRAMEWORK" sdd init --path "$WORK" --name poc --knowledge-root "$WORK/sdd-workspace"
uv run --project "$FRAMEWORK" sdd repo add "$WORK/repos/order-service"
uv run --project "$FRAMEWORK" sdd repo add "$WORK/repos/payment-service"
uv run --project "$FRAMEWORK" sdd discover --all
uv run --project "$FRAMEWORK" sdd system overview
uv run --project "$FRAMEWORK" sdd dependencies
uv run --project "$FRAMEWORK" sdd workflow discover "Customer order creation"
uv run --project "$FRAMEWORK" sdd impact "Introduce partial refund support"
uv run --project "$FRAMEWORK" sdd change propose "Introduce partial refund support"
uv run --project "$FRAMEWORK" sdd change validate introduce-partial-refund-support
uv run --project "$FRAMEWORK" sdd change approve introduce-partial-refund-support --artifact specification --reviewer poc
uv run --project "$FRAMEWORK" sdd change approve introduce-partial-refund-support --artifact design --reviewer poc
uv run --project "$FRAMEWORK" sdd change implement introduce-partial-refund-support
uv run --project "$FRAMEWORK" sdd freshness

echo
echo "POC workspace: $POC_WORKSPACE"
echo "Application copies were not modified by implement. Packets are under sdd-workspace/changes."

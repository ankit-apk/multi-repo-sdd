# Proof of concept: order service and payment service

The samples in `examples/order-service` (Python, FastAPI) and `examples/payment-service` (Node.js) are the brownfield baseline. Payment capture exists. Refunds reject any amount other than the original capture. Order service posts to `PAYMENT_SERVICE_URL` (default `http://payment-service:8080/payments`).

Use a scratch workspace so the samples in git stay the baseline. The script `scripts/poc.sh` performs registration, discovery, impact, proposal, approval, and packet creation without modifying the samples.

```bash
cd multi-repo-sdd
uv sync
./scripts/poc.sh
```

The script prints the workspace directory it created under `.sdd-tmp/poc`.

## What you should see

1. Both repositories register and are not modified.
2. Discovery reports Python/FastAPI for order service and JavaScript for payment service.
3. `dependencies.yaml` for order service contains a **verified** synchronous call to payment service. The evidence file is `app/main.py` and the symbol is `PAYMENT_SERVICE_URL`, which `_charge` uses to POST `/payments`.
4. Payment `business-rules.md` quotes the current full-refund-only behaviour as **inferred**, not as an approved rule.
5. `sdd workflow discover "Customer order creation"` names both repositories and does not pretend to be the dependency graph.
6. Impact analysis lists payment service as high (the refund rules and `/refunds` route) and order service as a dependency neighbor to evaluate.
7. `sdd change propose` writes one change id, a spec that quotes discovery excerpts, and repository task files. The order task depends on the payment task.
8. `sdd change implement` writes packets only. Application files stay untouched until you authorize writes.

## Continue into implementation

Open the scratch copies, not `examples/`. After reading `spec.md` and the payment task file:

1. Allow a partial refund when the amount is positive and not greater than the remaining captured amount. Keep rejecting amounts that exceed the capture.
2. Update the payment tests. The baseline test expects HTTP 409 for a partial refund; that assertion describes current behaviour and has to change with the specification.
3. Add the order-service call to the payment refund route only if the approved spec's order section requires it.
4. Check the task boxes in the change folder.
5. Run:

```bash
cd "$POC_WORKSPACE"
uv run --project /path/to/multi-repo-sdd sdd change verify introduce-partial-refund-support
uv run --project /path/to/multi-repo-sdd sdd change archive introduce-partial-refund-support
```

Verification runs each repository's tests with the current Python (`sys.executable -m pytest`) or `npm test`. It fails if tasks are still open or if git shows no edit since discovery. Install FastAPI and httpx into that interpreter before order-service tests can pass (`uv run --with fastapi --with httpx --with pydantic`).

Archive writes `sdd-workspace/specifications/introduce-partial-refund-support/` and refreshes discovery. The specification remains the approved intent. The refreshed discovery documents describe the code after the edit.

## Commands without the script

From a new directory:

```bash
uv run --project /path/to/multi-repo-sdd sdd init \
  --path . \
  --name poc \
  --knowledge-root ./sdd-workspace

uv run --project /path/to/multi-repo-sdd sdd repo add /path/to/order-service
uv run --project /path/to/multi-repo-sdd sdd repo add /path/to/payment-service
uv run --project /path/to/multi-repo-sdd sdd discover --all
uv run --project /path/to/multi-repo-sdd sdd system overview
uv run --project /path/to/multi-repo-sdd sdd dependencies
uv run --project /path/to/multi-repo-sdd sdd workflow discover "Customer order creation"
uv run --project /path/to/multi-repo-sdd sdd impact "Introduce partial refund support"
uv run --project /path/to/multi-repo-sdd sdd change propose "Introduce partial refund support"
uv run --project /path/to/multi-repo-sdd sdd change validate introduce-partial-refund-support
uv run --project /path/to/multi-repo-sdd sdd change approve introduce-partial-refund-support --artifact specification --reviewer you
uv run --project /path/to/multi-repo-sdd sdd change approve introduce-partial-refund-support --artifact design --reviewer you
uv run --project /path/to/multi-repo-sdd sdd change implement introduce-partial-refund-support
```

Commit the sample repositories before discovery if you want commit SHAs in the knowledge files. `sdd freshness` reports `unknown` when a path is not a git checkout.

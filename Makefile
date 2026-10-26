BACKEND := backend
FRONTEND := frontend

.PHONY: init sync test smoke lint audit api

# Create backend/.env from the example with a fresh session secret (keeps an existing file).
init:
	@test -f $(BACKEND)/.env && echo "backend/.env exists, leaving it alone" || \
	  (sed "s|^SESSION_SECRET=.*|SESSION_SECRET=$$(openssl rand -base64 48 | tr -d '\n/+=')|; \
	        s|^QDRANT_API_KEY=.*|QDRANT_API_KEY=$$(openssl rand -hex 24)|" $(BACKEND)/.env.example > $(BACKEND)/.env \
	   && chmod 600 $(BACKEND)/.env && echo "wrote backend/.env — add your LLM gateway settings")

sync:
	cd $(BACKEND) && uv sync --extra viz

test:
	cd $(BACKEND) && uv run pytest -q

smoke:
	cd $(BACKEND) && uv run python -m aura.core.llm smoke

lint:
	cd $(BACKEND) && uv run ruff check aura/core aura/api aura/ledger aura/models aura/plans.py aura/quotas.py tests/ledger tests/api alembic

audit:
	cd $(BACKEND) && uv run python -m aura.ledger.audit

api:
	cd $(BACKEND) && uv run uvicorn aura.api.app:app --port 8010 --reload --reload-exclude 'data/*'

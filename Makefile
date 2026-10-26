BACKEND := backend
FRONTEND := frontend
# Docker CLI targets use the same daemon as the backend (Colima: set DOCKER_HOST in backend/.env).
DOCKER_HOST ?= $(shell grep '^DOCKER_HOST=' $(BACKEND)/.env 2>/dev/null | cut -d= -f2)
export DOCKER_HOST

.PHONY: init sync test smoke lint audit api services sandbox-image

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
	cd $(BACKEND) && uv run ruff check aura/core aura/api aura/ledger aura/models aura/ingest aura/rag aura/sandbox aura/plans.py aura/quotas.py tests/ledger tests/api tests/core tests/sandbox tests/ingest tests/rag alembic

audit:
	cd $(BACKEND) && uv run python -m aura.ledger.audit

api:
	cd $(BACKEND) && uv run uvicorn aura.api.app:app --port 8010 --reload --reload-exclude 'data/*'

services:
	docker-compose --env-file $(BACKEND)/.env up -d qdrant

sandbox-image:
	docker build -t aura-sandbox:1 docker/sandbox

import uuid

# Namespace for deterministic ids (seed rows, chunk points) so reseeding keeps URLs and vector ids stable.
AURA_NS = uuid.UUID("6f1c2a52-7d0e-4c55-9b8e-3a1f4d2b9c10")


def new_id() -> str:
    return str(uuid.uuid4())


def stable_id(*parts: object) -> str:
    return str(uuid.uuid5(AURA_NS, ":".join(str(p) for p in parts)))

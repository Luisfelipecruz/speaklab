# Build context is the REPOSITORY ROOT, not this directory — see docker-compose.yml.
# That is what lets the image carry api/ and run without a bind mount, which is what
# makes it deployable and what lets CI run the suite inside the real image rather than
# against a reconstructed environment. .dockerignore at the root keeps the context to a
# few hundred kilobytes.
FROM python:3.12-slim

# curl is not a convenience: it is what the compose healthcheck runs. A slim image
# without it reports the api container unhealthy forever while the API is fine.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements before source, so editing a router does not re-run pip.
COPY infra/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# api/ becomes /app, so imports are `from config import ...` rather than
# `from api.config import ...`. api/tests/conftest.py puts the same directory on
# sys.path when the suite runs on a host, so a test that passes there passes here.
COPY api/ .

# In development docker-compose.yml bind-mounts ./api over this, which is the only
# reason --reload is worth having.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

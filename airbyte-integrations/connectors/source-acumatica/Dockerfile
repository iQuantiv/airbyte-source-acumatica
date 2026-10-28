ARG BASE_IMAGE=docker.io/airbyte/python-connector-base:4.1.1@sha256:a268b44c733ae699a60f5fbc06a324945dba98945c6e2ab7f8609f2f895b0d28
FROM ${BASE_IMAGE} AS builder

WORKDIR /airbyte/integration_code

# Install dependencies first (layer caching)
COPY pyproject.toml poetry.lock README.md ./
RUN poetry install --only main --no-root

# Copy source and install the root package
COPY source_acumatica ./source_acumatica
COPY main.py ./
RUN poetry install --only main

# Poetry and its dependencies are build tools; drop them so they do not ship in the runtime image
RUN pip uninstall -y poetry poetry-core poetry-plugin-export dulwich virtualenv msgpack filelock \
    && pip install --no-cache-dir --upgrade pip

ARG BASE_IMAGE=docker.io/airbyte/python-connector-base:4.1.1@sha256:a268b44c733ae699a60f5fbc06a324945dba98945c6e2ab7f8609f2f895b0d28
FROM ${BASE_IMAGE}

# Apply Debian security updates published after the base image was built
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /airbyte/integration_code

COPY --from=builder /usr/local /usr/local
COPY source_acumatica ./source_acumatica
COPY main.py ./

ENV AIRBYTE_ENTRYPOINT="python /airbyte/integration_code/main.py"
ENTRYPOINT ["python", "/airbyte/integration_code/main.py"]

ARG CONNECTOR_VERSION
ARG CONNECTOR_REPO
LABEL io.airbyte.version=${CONNECTOR_VERSION}
LABEL io.airbyte.name=${CONNECTOR_REPO}

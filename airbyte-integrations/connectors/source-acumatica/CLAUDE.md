# Acumatica Source Connector

An Airbyte source connector that integrates with Acumatica ERP systems. Extracts data from three API endpoint types: Contract-based REST APIs, OData v3 Inquiry endpoints, and OData v4 Direct Access Connector (DAC) endpoints. Supports both full refresh and incremental syncs with cursor-based pagination for large datasets.

## Tech Stack

| Layer | Technology | Version | Purpose |
|-------|------------|---------|---------|
| Runtime | Python | 3.9–3.11 | Source connector implementation |
| Framework | Airbyte CDK | 0.x | Connector development kit and stream abstractions |
| Package Manager | Poetry | 1.7+ | Dependency management and packaging |
| Testing | pytest + requests-mock | Latest | Unit and integration test framework |
| Authentication | OAuth 2.0 | Standard | Token-based auth to Acumatica |

## Quick Start

```bash
# Prerequisites
- Python 3.9 or 3.11
- Poetry 1.7+
- Valid Acumatica instance with OAuth credentials

# Install dependencies
poetry install --with dev

# Create config from spec
# See sample_files/sample_config.json as template
cp sample_files/sample_config.json secrets/config.json
# Edit secrets/config.json with your Acumatica credentials

# Test connection
poetry run source-acumatica check --config secrets/config.json

# Discover available streams (tables)
poetry run source-acumatica discover --config secrets/config.json

# Run full sync with sample catalog
poetry run source-acumatica read \
  --config secrets/config.json \
  --catalog sample_files/configured_catalog.json

# Run tests
poetry run pytest tests/
```

## Project Structure

```
source-acumatica/
├── source_acumatica/
│   ├── __init__.py              # Package initialization
│   ├── source.py                # Core connector logic (583 lines)
│   ├── run.py                   # CLI entry point
│   ├── spec.yaml                # Connection spec (BASEURL, auth, etc)
│   ├── schemas/                 # Pre-defined JSON schemas
│   │   ├── customers.json
│   │   ├── employees.json
│   │   ├── SalesOrder.json
│   │   └── TODO.md              # Schema development notes
│   └── jits.py                  # Empty placeholder
├── unit_tests/                  # Unit tests (mocked)
│   ├── test_source.py           # Basic connector tests
│   ├── test_streams.py          # Stream initialization tests
│   └── test_incremental_streams.py  # Cursor/state tests
├── integration_tests/           # Integration tests (real API)
│   ├── testsalesorder.py        # SalesOrder endpoint tests
│   ├── configured_catalog.json  # Sample sync catalog
│   └── acceptance.py            # Acceptance test fixtures
├── Dockerfile                 # Multi-stage Docker build (reads base image from build arg)
├── build.sh                   # Build script (reads metadata.yaml for base image/version)
├── check-base-image.sh        # Checks Docker Hub for newer base images
├── pyproject.toml              # Project metadata and deps
├── poetry.lock                 # Locked dependency versions
├── metadata.yaml               # Airbyte registry metadata (single source of truth for base image + version)
├── acceptance-test-config.yml  # Acceptance test config
└── README.md                   # User documentation
```

## Architecture Overview

The connector follows a hierarchical stream model with three endpoint types:

```
SourceAcumatica (AbstractSource)
  ├── Contract-based Streams (legacy XML/REST endpoints)
  ├── OData v3 Inquiry Streams (read-only queries)
  └── OData v4 DAC Streams (direct table access)

Each stream type inherits from AcumaticaStream or IncrementalAcumaticaStream
which handle pagination, state management, and schema flattening.
```

**Authentication Flow:**
1. `AcumaticaOauth2Authenticator` handles OAuth 2.0 ROPC flow (CLIENTID/CLIENTSECRET + USERNAME/PASSWORD)
2. Token automatically refreshed on expiration via CDK's `Oauth2Authenticator` base class
3. Session cleanup via `logoutFromAcumatica()` after each read operation

**Data Flow:**
1. `check_connection()` validates credentials by requesting an access token
2. `streams()` introspects Acumatica metadata to build stream list dynamically
3. Each stream fetches pages of data with `$skip/$top` pagination
4. Incremental streams use cursor field (LastModified/LastModifiedDateTime) for state
5. Nested objects are flattened to top-level properties via `flatten_json_array()`

### Key Modules

| Module | Location | Purpose |
|--------|----------|---------|
| SourceAcumatica | source.py | Main source class; instantiates streams |
| AcumaticaStream | source.py | Base stream for full-refresh syncs; handles pagination, retry, and HTTP |
| IncrementalAcumaticaStream | source.py | Extends AcumaticaStream with cursor-based incremental state |
| AcumaticaOauth2Authenticator | source.py | OAuth 2.0 ROPC authenticator with auto token refresh |
| Metadata Resolution | source.py | `getmetatdata()`, `getodata3metadata()`, `getodata4metadata()`: Schema introspection |
| Schema Processing | source.py:224 | `process_schema()`: Flattens allOf references and nested arrays |
| Flattening | source.py | `flatten_json_array()`: Recursively flattens nested objects |

## Development Guidelines

### Code Style

**File Naming:**
- Modules: `snake_case` (e.g., `source_acumatica`, `run.py`)
- Directories: `snake_case` (e.g., `source_acumatica/`, `unit_tests/`)

**Code Naming:**
- Classes: `PascalCase` (e.g., `SourceAcumatica`, `AcumaticaStream`)
- Functions/methods: `snake_case` (e.g., `get_access_token()`, `read_records()`)
- Variables: `snake_case` (e.g., `stream_state`, `access_token`)
- Constants: `SCREAMING_SNAKE_CASE` (e.g., `BASEURL` in config)
- Private methods: prefix with `_` (e.g., `self._schema`, `self._cursor_field`)

**Stream Naming Convention:**
Streams are named as `{ENDPOINTTYPE}__{ENTITY}`:
- `contract__SalesOrder` (Contract-based endpoint)
- `Inquiry__Employees` (OData v3 Inquiry)
- `DAC__Customers` (OData v4 Direct Access)

### Import Order

1. Standard library (abc, collections, datetime, etc.)
2. External packages (requests, dateutil, yaml, airbyte_cdk, etc.)
3. Local imports (relative imports from current package)
4. Logging setup

Current code does not strictly follow this, but new code should.

### Type Hints

- Stream method signatures use `Mapping[str, Any]` for config/state dictionaries
- Return types explicitly annotated (e.g., `Tuple[bool, any]`, `List[HttpStream]`)
- Abstract base classes used for inheritance (`AcumaticaStream` extends `Stream`)

### Testing Patterns

**Unit Tests** (`unit_tests/`):
- Use `pytest` with `unittest.mock.MagicMock`
- Mock HTTP responses with `requests-mock`
- Test stream instantiation, connection checks, basic flow
- File pattern: `test_*.py`

**Integration Tests** (`integration_tests/`):
- Hit real Acumatica instance (requires live credentials)
- Validate endpoint behavior and schema discovery
- Run via `acceptance-test-config.yml` for CI/CD

### Key Design Patterns

**1. Dynamic Stream Discovery:**
- Metadata endpoints queried at runtime to discover available entities
- Schemas loaded from Acumatica's OData metadata rather than pre-defined
- Supports new Acumatica fields without code changes

**2. Incremental State Management:**
- `get_updated_state()` compares cursor values (dates) to track progress
- State persisted between syncs to resume from last position
- Supports multiple cursor fields per entity

**3. Pagination Strategy:**
- `request_params()` builds `$skip` and `$top` query parameters
- `next_page_token` incremented after each page fetch
- Loop terminates when response contains fewer records than page size

**4. Schema Flattening:**
- OData `$expand` and nested navigation properties flattened to flat JSON
- `process_schema()` merges allOf constructs for schema compatibility
- Nested objects converted to top-level prefixed fields (e.g., `Address.City` → `Address_City`)

## Available Commands

| Command | Description |
|---------|-------------|
| `poetry install --with dev` | Install all dependencies including dev tools |
| `poetry run source-acumatica spec` | Print connection specification (JSON schema) |
| `poetry run source-acumatica check --config` | Validate credentials and test connection |
| `poetry run source-acumatica discover --config` | Introspect Acumatica and list available streams |
| `poetry run source-acumatica read --config --catalog` | Execute a sync with specified streams/columns |
| `poetry run pytest unit_tests/` | Run unit tests (mocked) |
| `poetry run pytest integration_tests/` | Run integration tests (live API) |
| `./build.sh` | Build Docker image (reads base image and version from metadata.yaml) |
| `./build.sh 0.1.28` | Build with version override |
| `./check-base-image.sh` | Check Docker Hub for newer base images |

## Environment & Configuration

### Required Configuration (spec.yaml)

| Variable | Type | Required | Description | Example |
|----------|------|----------|-------------|---------|
| `BASEURL` | string | Yes | Base URL of Acumatica instance | `https://mycompany.acumatica.com` |
| `CLIENTID` | string | Yes | OAuth client ID from Acumatica | `C0625E9C-...@MDB-UserTesting` |
| `CLIENTSECRET` | string | Yes | OAuth client secret (secret) | `HY5XGtaPxGUwKiUhqiJMLw` |
| `USERNAME` | string | Yes | Acumatica username | `MDBANALYTICS` |
| `PASSWORD` | string | Yes | Acumatica password (secret) | `0kX&jkex7Agn%xMW` |
| `TENANTNAME` | string | No | Tenant name (if multi-tenant) | `mycompany` |
| `PAGESIZE` | number | No | Records per page (default: 1000) | `500` |
| `STREAM_PAGESIZE_OVERRIDES` | array | No | Per-stream page size overrides. Format: `StreamName::PageSize` | `["DAC__GLTran::10000"]` |
| `STREAMSTODISABLEPAGING` | array | No | Streams to disable paging for (fetches all records in one request) | `["Inquiry__MyStream"]` |
| `MAX_EMPTY_RETRIES` | integer | No | Max retries for empty 200 responses (default: 10) | `10` |
| `EMPTY_RETRY_BACKOFF_BASE` | integer | No | Backoff base in seconds for empty response retries (default: 5, capped at 300s) | `5` |
| `APIVERSION` | string | No | Acumatica API version (default: 24.200.001) | `"24.200.001"` |

### Required Environment Variables

No environment variables required. All config passed via `--config` JSON file.

### Development Config

Create `secrets/config.json`:
```json
{
  "BASEURL": "https://your-instance.acumatica.com",
  "CLIENTID": "your-client-id",
  "CLIENTSECRET": "your-client-secret",
  "USERNAME": "your-username",
  "PASSWORD": "your-password",
  "PAGESIZE": 1000,
  "STREAM_PAGESIZE_OVERRIDES": ["DAC__GLTran::10000"],
  "MAX_EMPTY_RETRIES": 10,
  "EMPTY_RETRY_BACKOFF_BASE": 5
}
```

This file is gitignored for security.

## Testing Strategy

### Unit Tests
- Located in `unit_tests/`
- Mock all HTTP requests and external calls
- Test connection validation, stream discovery, incremental state
- Run via `poetry run pytest unit_tests/`

### Integration Tests
- Located in `integration_tests/`
- Hit real Acumatica instance (requires live credentials in `secrets/config.json`)
- Test actual endpoint response parsing and schema compliance
- `acceptance.py` provides fixtures for setup/teardown

### Acceptance Tests
- Defined in `acceptance-test-config.yml`
- Run by Airbyte CI/CD pipeline
- Validates against Airbyte connector contract

**Coverage Target:** Aim for >80% line coverage in unit tests.

## Common Workflows

### Adding a New Stream

1. **Schema Definition:** Create JSON schema file in `source_acumatica/schemas/`
2. **Stream Class:** Define in `source.py` inheriting from `AcumaticaStream` or `IncrementalAcumaticaStream`
3. **Registration:** Add instantiation in `SourceAcumatica.streams()`
4. **Tests:** Add test case in `unit_tests/test_streams.py`
5. **Validation:** Run `poetry run source-acumatica discover --config secrets/config.json` to verify

### Debugging a Sync

1. Enable logging: Check `logger.info()` calls in `source.py` for request/response details
2. Inspect state: Review `stream_state` passed to `get_updated_state()`
3. Validate schema: Ensure JSON schema in `spec` matches actual API response structure
4. Check pagination: Verify `$skip` and `$top` params in request logs

### Updating Dependencies

1. Add new package: `poetry add package-name`
2. Update existing: `poetry update package-name`
3. Lock versions: Commit changes to `pyproject.toml` and `poetry.lock`
4. Test: `poetry run pytest` to verify no breaking changes

## Recent Changes

- **Latest:** Per-stream page size overrides, configurable empty response retry with capped backoff
- **Recent:** Dockerfile and build.sh replacing airbyte-ci, base image update checker
- **Recent:** AcumaticaOauth2Authenticator replacing manual get_access_token()
- **Recent:** Added paging support for large result sets ($skip/$top)
- **Earlier:** Inquiry endpoints (OData v3) and DAC endpoints (OData v4) support
- **Earlier:** Schema conversion fixes for allOf and nested parent properties

See git log for full commit history.

## Deployment

### Local Development
```bash
poetry install --with dev
poetry run source-acumatica check --config secrets/config.json
```

### Docker Image
```bash
# Build image (reads base image and version from metadata.yaml)
./build.sh

# Run in Docker
docker run --rm \
  -v $(pwd)/secrets:/secrets \
  -v $(pwd)/sample_files:/sample_files \
  airbyte/source-acumatica:dev \
  read --config /secrets/config.json --catalog /sample_files/configured_catalog.json
```

### Push to Azure Container Registry
```bash
docker tag airbyte/source-acumatica:<version> acriquantiv.azurecr.io/source-acumatica:<version>
az acr login --name acriquantiv
docker push acriquantiv.azurecr.io/source-acumatica:<version>
```

### Release stage
- Current version: see `dockerImageTag` in metadata.yaml
- Release stage: Beta (community-supported)

## Additional Resources

- **Acumatica API Docs:** https://www.acumatica.com/api-reference (OData/REST)
- **Airbyte CDK Docs:** https://docs.airbyte.com/connector-development
- **Project README:** @README.md (user-facing documentation)
- **Acceptance Tests:** @acceptance-test-config.yml
- **GitHub Issues:** Filter by `source-acumatica` label in main Airbyte repo

## Known Limitations & TODOs

- Cursor field detection relies on hardcoded field names (LastModified, LastModifiedDateTime)
- Contract-based endpoints require manual schema definition; OData metadata-driven
- Schema flattening may lose data for deeply nested objects
- Rate limiting not configurable per Acumatica instance
- See `source_acumatica/schemas/TODO.md` for schema development notes


## Skill Usage Guide

When working on tasks involving these technologies, invoke the corresponding skill:

| Skill | Invoke When |
|-------|-------------|
| poetry | Manages project dependencies, lockfiles, and virtual environments |
| airbyte-cdk | Develops connector streams and handles incremental sync with cursors |
| docker | Builds and deploys containerized connector images |
| oauth | Manages OAuth 2.0 authentication and token lifecycle |
| requests-mock | Mocks HTTP responses for testing without live endpoints |

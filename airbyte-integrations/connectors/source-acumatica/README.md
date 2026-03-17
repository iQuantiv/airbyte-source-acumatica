# Acumatica Source

This is the repository for the Acumatica source connector, written in Python.
For information about how to use this connector within Airbyte, see [the documentation](https://docs.airbyte.com/integrations/sources/acumatica).

## Local development

### Prerequisites

* Python (`^3.9`)
* Poetry (`^1.7`) - installation instructions [here](https://python-poetry.org/docs/#installation)



### Installing the connector

From this connector directory, run:
```bash
poetry install --with dev
```


### Create credentials

**If you are a community contributor**, follow the instructions in the [documentation](https://docs.airbyte.com/integrations/sources/acumatica)
to generate the necessary credentials. Then create a file `secrets/config.json` conforming to the `src/source_acumatica/spec.yaml` file.
Note that any directory named `secrets` is gitignored across the entire Airbyte repo, so there is no danger of accidentally checking in sensitive information.
See `sample_files/sample_config.json` for a sample config file.


### Locally running the connector

```
poetry run source-acumatica spec
poetry run source-acumatica check --config secrets/config.json
poetry run source-acumatica discover --config secrets/config.json
poetry run source-acumatica read --config secrets/config.json --catalog sample_files/configured_catalog.json
```

### Running tests

To run tests locally, from the connector directory run:

```
poetry run pytest tests
```

### Building the docker image

From this connector directory, run:
```bash
./build.sh
```

This reads the base image, version, and repository from `metadata.yaml` and builds a multi-stage Docker image. Two tags are created:
- `airbyte/source-acumatica:<version>` (e.g., `airbyte/source-acumatica:0.1.23`)
- `airbyte/source-acumatica:dev`

You can override the version tag: `./build.sh 0.1.24`

### Running as a docker container

```bash
docker run --rm airbyte/source-acumatica:dev spec
docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-acumatica:dev check --config /secrets/config.json
docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-acumatica:dev discover --config /secrets/config.json
docker run --rm -v $(pwd)/secrets:/secrets -v $(pwd)/integration_tests:/integration_tests airbyte/source-acumatica:dev read --config /secrets/config.json --catalog /integration_tests/configured_catalog.json
```

### Pushing to a container registry

```bash
# Tag for your registry
docker tag airbyte/source-acumatica:0.1.23 <your-registry>/airbyte/source-acumatica:0.1.23

# Push
docker push <your-registry>/airbyte/source-acumatica:0.1.23
```

### Checking for base image updates

A pre-commit hook automatically checks for newer versions of the base image when committing connector changes. You can also run the check manually:
```bash
./check-base-image.sh
```

### Customizing acceptance Tests

Customize `acceptance-test-config.yml` file to configure acceptance tests. See [Connector Acceptance Tests](https://docs.airbyte.com/connector-development/testing-connectors/connector-acceptance-tests-reference) for more information.
If your connector requires to create or destroy resources for use during acceptance tests create fixtures for it and place them inside integration_tests/acceptance.py.

### Dependency Management

All of your dependencies should be managed via Poetry. 
To add a new dependency, run:

```bash
poetry add <package-name>
```

Please commit the changes to `pyproject.toml` and `poetry.lock` files.

## Publishing a new version of the connector

1. Run tests: `poetry run pytest unit_tests/`
2. Bump the `dockerImageTag` in `metadata.yaml`
3. Build the image: `./build.sh`
4. Test in Docker: `docker run --rm -v $(pwd)/secrets:/secrets airbyte/source-acumatica:dev check --config /secrets/config.json`
5. Tag and push to your container registry
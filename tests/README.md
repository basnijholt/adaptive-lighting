# Developer notes for the tests directory

To run the tests, check out the [CI configuration](../.github/workflows/pytest.yml) to see how they are executed in the CI pipeline.
Alternatively, you can use the provided Docker image to run the tests locally or run them with VS Code directly in the dev container.

## Prerequisites

Before running tests with Docker, you need a local Home Assistant core checkout with symlinks:

```bash
# Clone HA core (one-time setup)
git clone --depth 1 https://github.com/home-assistant/core.git core

# Setup symlinks (one-time setup)
./scripts/setup-symlinks
```

## Running tests with Docker

Navigate to the `adaptive-lighting` repo folder and execute the following command.

**Important:** Mount the entire repo (`-v $(pwd):/app`), not individual directories, or the symlinks will break.

Linux / MacOS / Windows PowerShell:
```bash
docker run -v ${PWD}:/app basnijholt/adaptive-lighting:latest
```

- In windows command prompt, the command is:
  ```bash
  docker run -v %cd%:/app basnijholt/adaptive-lighting:latest
  ```

This command will download the Docker image from [the adaptive-lighting Docker Hub repo](https://hub.docker.com/r/basnijholt/adaptive-lighting) and run the tests.

If you prefer to build the image yourself, use the following command:

```bash
docker build -t basnijholt/adaptive-lighting:latest --no-cache --progress=plain .
```

This might be necessary if the image on Docker Hub is outdated or if the [`test_dependencies.py`](../test_dependencies.py) file is updated.

## Passing arguments to pytest

You can pass arguments to pytest by appending them to the command:

For example, to run the tests with a custom log format, use the following command (this also gets rid of the captured stderr output):

```bash
docker run -v $(pwd):/app basnijholt/adaptive-lighting:latest --show-capture=log --log-format="%(asctime)s %(levelname)-8s %(name)s:%(filename)s:%(lineno)s %(message)s" --log-date-format="%H:%M:%S" tests/components/adaptive_lighting/
```

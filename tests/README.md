# Developer notes for the tests directory

To run the tests, check out the [CI configuration](../.github/workflows/pytest.yaml) to see how they are executed in the CI pipeline.
Alternatively, you can use the provided Docker image to run the tests locally or run them with VS Code directly in the dev container.

## Coverage reports

Open a `pytest` workflow run in GitHub Actions to see line and branch coverage in each job's summary. Download its `coverage-<Home Assistant version>-py<Python version>` artifact for the XML and JSON reports and the browsable HTML report. After extracting it, open `htmlcov/index.html` to inspect missing lines and branches.

Coverage measures executed code, not whether assertions would catch a bug. Add tests for observable behavior: emitted light commands, final states, manual-control events, and timer expiry. The integration suite runs inside Home Assistant with simulated lights; it does not establish physical-device behavior. It also does not execute every documentation generator included in the package's coverage total.

The tests in `test_automation_examples.py` load YAML directly from `README.md` and execute it through Home Assistant's automation and script engines. Edit the README source when changing those examples, then run `./scripts/update-generated-content` to update the documentation pages.

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

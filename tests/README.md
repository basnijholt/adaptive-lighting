# Developer notes for the tests directory

To run the tests, check out the [CI configuration](../.github/workflows/pytest.yml) to see how they are executed in the CI pipeline.
Alternatively, you can use the provided Docker image to run the tests locally.

To run the tests using the Docker image, navigate to the `adaptive-lighting` repo folder and execute the following command:

```bash
docker run -v $(pwd):/app basnijholt/adaptive-lighting:latest
```

and to show the logs with colors use:

```bash
docker run -v $(pwd):/app -e 'PYTEST_ADDOPTS="--color=yes"' basnijholt/adaptive-lighting:latest
```

This command will download the Docker image from [the adaptive-lighting Docker Hub repo](https://hub.docker.com/r/basnijholt/adaptive-lighting) and run the tests.

If you prefer to build the image yourself, use the following command:

```bash
docker build -t basnijholt/adaptive-lighting:latest --no-cache .
```

This might be necessary if the image on Docker Hub is outdated or if the [`test_dependencies.py`](../test_dependencies.py) file is updated.

# Developer notes for the tests directory

See how the tests are run in the [CI configuration](../.github/workflows/pytest.yml).
We also provide a Docker image for running the tests locally.

Run the following command in the `adaptive-lighting` repo folder to run the tests:
```bash
docker run -v $(pwd):/app basnijholt/adaptive-lighting:latest
```
This should [download the image from Docker Hub](https://hub.docker.com/r/basnijholt/adaptive-lighting) and run the tests.

Optionally build the image yourself with:
```bash
docker build -t basnijholt/adaptive-lighting:latest --no-cache .
```
You might want to do this if the image on Docker Hub is outdated (the `home-assistant/core` code is updated more frequently than this repo and baked in to the image) or if [`test_dependencies.py`](../test_dependencies.py) is updated.

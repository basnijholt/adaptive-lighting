# See tests/README.md for instructions on how to run the tests.

# tl;dr:
# Run the following command in the adaptive-lighting repo folder to run the tests:
# docker run -v $(pwd):/app basnijholt/adaptive-lighting:latest

# Optionally build the image yourself with:
# docker build -t basnijholt/adaptive-lighting:latest .

FROM python:3.12-bookworm

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    build-essential libssl-dev libffi-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone home-assistant/core
RUN git clone --depth 1 --branch dev https://github.com/home-assistant/core.git /core

# Copy the Adaptive Lighting repository
COPY . /app/

# Setup symlinks in core
RUN ln -s /core /app/core && /app/scripts/setup-symlinks

# Install home-assistant/core dependencies
RUN /app/scripts/setup-dependencies

WORKDIR /core

# Make 'custom_components/adaptive_lighting' imports available to tests
ENV PYTHONPATH="${PYTHONPATH}:/app"

ENTRYPOINT ["python3", \
    # Enable Python development mode
    "-X", "dev", \
    # Run pytest
    "-m", "pytest", \
    # Verbose output
    "-vvv", \
    # Set a timeout of 9 seconds per test
    "--timeout=9", \
    # Print the 10 slowest tests
    "--durations=10", \
    # Measure code coverage for the 'homeassistant' package
    "--cov='homeassistant'", \
    # Generate an XML report of the code coverage
    "--cov-report=xml", \
    # Generate an HTML report of the code coverage
    "--cov-report=html", \
    # Print a summary of the code coverage in the console
    "--cov-report=term", \
    # Print logs in color
    "--color=yes", \
    # Print a count of test results in the console
    "-o", "console_output_style=count"]

# Run tests in the 'tests/components/adaptive_lighting' directory
CMD ["tests/components/adaptive_lighting"]

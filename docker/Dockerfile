FROM python:3.10-slim

# Set working directory
WORKDIR /workspace

# Install git and other necessary tools
RUN apt-get update && \
    apt-get install -y git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Install additional packages for the harness
RUN pip install tiktoken pytest-json-report

# Copy the harness code
COPY harness/ /harness/

# Set the entrypoint
ENTRYPOINT ["python", "/harness/entrypoint.py"] 
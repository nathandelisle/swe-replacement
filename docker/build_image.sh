#!/bin/bash
# Build script for the SWE replacement test Docker image

# Build the Docker image
docker build -t swe-replacement:latest .

echo "Docker image 'swe-replacement:latest' built successfully!" 
#!/usr/bin/env bash
set -o errexit

# Only install poppler for PDF to image conversion
apt-get update
apt-get install -y poppler-utils

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
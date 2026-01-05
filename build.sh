#!/usr/bin/env bash
set -o errexit

# No system dependencies needed anymore!

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt
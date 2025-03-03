#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Create uploads directory
mkdir -p static/uploads
chmod -R 777 static/uploads

#!/usr/bin/env bash
# exit on error
set -o errexit

pip install -r requirements.txt

# Create uploads and logs directories
mkdir -p static/uploads logs
chmod -R 777 static/uploads logs

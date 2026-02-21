#!/bin/bash

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

python -m pypandoc.download_pandoc

ollama pull phi3

echo "✅ Setup complete"

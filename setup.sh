#!/bin/bash

echo
echo "Installing dependencies (apt)"
sudo apt install -y potrace openscad

echo
echo "Creating python environment"
python3.10 -m venv env
. env/bin/activate

echo
echo "Installing dependencies (pip)"
python -m pip install -U wheel setuptools pip
python -m pip install -r requirements.txt
python -m pip install -U ruff pyupgrade # Code quality
python -m pip freeze > requirements-freeze.txt

echo
echo "To activate environment (every time you start work) run:"
echo ". env/bin/activate"

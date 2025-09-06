#!/bin/bash


# Assumes there is a parent directory with virtual ENV with dependancies installed

cd "$(dirname "$0")"

# Absolute path to your virtual environment
VENV_PATH="../v_env"

# Absolute path to your python file
PY_SCRIPT="ZenSamaya.spec"

# Activate the virtual environment
source "$VENV_PATH/bin/activate"

# Run your Python script
#python "$PY_SCRIPT"
pyinstaller "$PY_SCRIPT"

# (Optional) Deactivate the virtual environment
deactivate
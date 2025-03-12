#!/usr/bin/env bash
set -e

# ------------------------------------------------------------------------------
# 1. Download micromamba (linux-64) if not present
# ------------------------------------------------------------------------------
if [ ! -f micromamba ]; then
    echo "Downloading micromamba (linux-64)..."
    curl -L -o micromamba \
        "https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-linux-64"
    chmod +x micromamba
fi

# ------------------------------------------------------------------------------
# 2. Create environment if not existing, specifying conda-forge for Python 3.12
# ------------------------------------------------------------------------------
if [ ! -d env ]; then
    echo "Creating local environment with Python 3.12 from conda-forge..."
    ./micromamba create -y -p "$PWD/env" -c conda-forge python=3.12
else
    echo "Environment already exists. Skipping creation."
fi

# ------------------------------------------------------------------------------
# 3. Install/Update requirements from pip
# ------------------------------------------------------------------------------
echo "Installing/Updating pip requirements..."
./micromamba run -p "$PWD/env" python -m pip install --upgrade pip
./micromamba run -p "$PWD/env" python -m pip install -r requirements.txt

# ------------------------------------------------------------------------------
# 4. Run the application
# ------------------------------------------------------------------------------
echo "Launching the application..."
./micromamba run -p "$PWD/env" python main.py

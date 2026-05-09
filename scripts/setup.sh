#!/bin/bash
# UMI Exchange — Interactive Setup Script
set -euo pipefail
echo "=== UMI Exchange Setup ==="
echo ""

# Check Python
python3 --version >/dev/null 2>&1 || { echo "ERROR: Python 3 required."; exit 1; }

# Create virtualenv if not exists
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt

# Create .env if not exists
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    # Generate secret key
    SECRET=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
    sed -i "s/change-me-to-a-random-50-char-string/$SECRET/" .env
    # Generate encryption key
    ENC_KEY=$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    sed -i "s|generate-with-python.*|$ENC_KEY|" .env
    echo "  .env created with generated keys."
    echo "  IMPORTANT: Edit .env to set DATABASE_URL and REDIS_URL."
fi

# Run migrations
echo "Running migrations..."
python3 manage.py migrate

echo ""
echo "=== Setup complete ==="
echo "Start the dev server: python manage.py runserver"
echo "Create a superuser:   python manage.py createsuperuser"

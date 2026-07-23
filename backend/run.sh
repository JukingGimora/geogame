#!/bin/sh
cd "$(dirname "$0")"
eval "$(conda shell.bash hook)"
if ! conda env list | grep -q "^geogame "; then
  conda create -n geogame python=3.11 -y
fi
conda activate geogame
pip install -r requirements.txt
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
uvicorn app.main:app --host 0.0.0.0 --port 8020 --reload

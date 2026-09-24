#!/bin/sh
set -e
cd /app/graph
python seed.py || echo "WARN: Neo4j seed failed; API will use in-memory network"
cd /app/backend
if [ "${TRAIN_MODEL:-0}" = "1" ] || [ ! -s "$MODEL_DIR/delay_xgb.json" ] || [ ! -s "$MODEL_DIR/feature_names.json" ]; then
  python scripts/train.py
else
  echo "Using existing model at $MODEL_DIR (set TRAIN_MODEL=1 to retrain)"
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

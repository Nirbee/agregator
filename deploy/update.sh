#!/usr/bin/env bash
# Обновление до свежей версии из git и перезапуск.
#   sudo bash deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ -d .git ]; then
  echo ">>> git pull..."
  git pull --ff-only || echo "(!) git pull пропущен"
fi

[ -f .env ] || { cp .env.example .env; echo ">>> создан .env — отредактируйте и запустите снова"; exit 0; }

echo ">>> Пересборка и перезапуск..."
docker compose up -d --build
docker compose ps
echo ">>> Обновлено. Логи: docker compose logs -f"

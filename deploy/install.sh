#!/usr/bin/env bash
# ============================================================
#  Установка агрегатора на чистый сервер (Ubuntu 22.04/24.04).
#  Запуск:
#    git clone https://github.com/Nirbee/agregator.git
#    cd agregator
#    sudo bash deploy/install.sh
# ============================================================
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR="$(pwd)"
echo ">>> Каталог проекта: $PROJECT_DIR"

# 1. Docker + compose
if ! command -v docker >/dev/null 2>&1; then
  echo ">>> Устанавливаю Docker..."
  curl -fsSL https://get.docker.com | sh
else
  echo ">>> Docker уже установлен."
fi

# 2. Файл настроек
if [ ! -f .env ]; then
  cp .env.example .env
  echo ">>> Создан .env из шаблона."
  echo "!!! ВАЖНО: откройте .env и задайте PORTAL_PASSWORD (и токены при необходимости):"
  echo "    nano $PROJECT_DIR/.env"
  echo "    затем снова запустите: sudo bash deploy/update.sh"
  exit 0
fi

# 3. Сборка и запуск
echo ">>> Сборка образа (первый раз долго — качается Chromium)..."
docker compose up -d --build

echo ""
echo ">>> Готово. Контейнеры:"
docker compose ps
IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo ""
echo ">>> Портал доступен: http://${IP:-СЕРВЕР}:8000"
echo ">>> Логин/пароль — из .env (PORTAL_USER / PORTAL_PASSWORD)."
echo ">>> Логи сбора:   docker compose logs -f scheduler"

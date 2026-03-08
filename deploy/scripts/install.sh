#!/usr/bin/env bash
set -euo pipefail

# Interactive installer for Ubuntu 22.04+
# Usage:
#   bash deploy/scripts/install.sh

export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"

if [[ "${BASH_VERSINFO[0]}" -lt 4 ]]; then
  echo "Требуется Bash >= 4"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

if [[ ! -f "${REPO_DIR}/pyproject.toml" ]]; then
  echo "Не найден pyproject.toml. Запустите скрипт из репозитория проекта."
  exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "Скрипт рассчитан на Ubuntu/Linux."
  exit 1
fi

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  if [[ "${ID:-}" != "ubuntu" ]]; then
    echo "Предупреждение: обнаружена ОС ${ID:-unknown}. Ожидалась Ubuntu."
  fi
fi

SUDO_CMD=""
if [[ "${EUID}" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO_CMD="sudo"
  else
    echo "Нужен root-доступ или sudo."
    exit 1
  fi
fi

run_root() {
  if [[ -n "${SUDO_CMD}" ]]; then
    sudo "$@"
  else
    "$@"
  fi
}

run_as_user() {
  local user="$1"
  shift
  if [[ "${EUID}" -eq 0 ]]; then
    runuser -u "${user}" -- "$@"
  else
    sudo -u "${user}" "$@"
  fi
}

prompt() {
  local var_name="$1"
  local label="$2"
  local default_value="${3:-}"
  local value
  if [[ -n "${default_value}" ]]; then
    read -r -p "${label} [${default_value}]: " value
    value="${value:-${default_value}}"
  else
    read -r -p "${label}: " value
  fi
  printf -v "${var_name}" "%s" "${value}"
}

prompt_secret() {
  local var_name="$1"
  local label="$2"
  local value
  read -r -s -p "${label}: " value
  echo
  printf -v "${var_name}" "%s" "${value}"
}

prompt_yes_no() {
  local var_name="$1"
  local label="$2"
  local default_value="${3:-y}"
  local value
  local normalized_default
  normalized_default="$(echo "${default_value}" | tr '[:upper:]' '[:lower:]')"
  while true; do
    read -r -p "${label} [y/n, default=${normalized_default}]: " value
    value="${value:-${normalized_default}}"
    value="$(echo "${value}" | tr '[:upper:]' '[:lower:]')"
    case "${value}" in
      y|yes|д|да)
        printf -v "${var_name}" "true"
        return
        ;;
      n|no|н|нет)
        printf -v "${var_name}" "false"
        return
        ;;
      *)
        echo "Введите y или n."
        ;;
    esac
  done
}

require_non_empty() {
  local var_name="$1"
  local label="$2"
  local value="${!var_name:-}"
  while [[ -z "${value}" ]]; do
    echo "${label} не может быть пустым."
    read -r -p "${label}: " value
  done
  printf -v "${var_name}" "%s" "${value}"
}

normalize_admin_ids() {
  local raw="${1:-}"
  local stripped
  local part
  local ids=()

  stripped="${raw//[[:space:]]/}"
  if [[ -z "${stripped}" ]]; then
    echo "[]"
    return
  fi

  if [[ "${stripped}" =~ ^\[(.*)\]$ ]]; then
    stripped="${BASH_REMATCH[1]}"
  fi

  IFS=',' read -r -a parts <<<"${stripped}"
  for part in "${parts[@]}"; do
    [[ -z "${part}" ]] && continue
    if [[ ! "${part}" =~ ^[0-9]+$ ]]; then
      echo "Ошибка: BOT_ADMIN_IDS должен содержать только числа через запятую." >&2
      exit 1
    fi
    ids+=("${part}")
  done

  if [[ "${#ids[@]}" -eq 0 ]]; then
    echo "[]"
  else
    local joined
    joined="$(IFS=,; echo "${ids[*]}")"
    echo "[${joined}]"
  fi
}

normalize_single_line() {
  local var_name="$1"
  local value="${!var_name:-}"
  value="${value//$'\r'/}"
  value="${value//$'\n'/}"
  printf -v "${var_name}" "%s" "${value}"
}

assert_ascii() {
  local var_name="$1"
  local value="${!var_name:-}"
  if [[ -z "${value}" ]]; then
    return
  fi
  if LC_ALL=C grep -q '[^ -~]' <<<"${value}"; then
    echo "Ошибка: ${var_name} содержит не-ASCII символы."
    echo "Используйте только латиницу/цифры/символы (без кириллицы)."
    exit 1
  fi
}

env_quote() {
  local value="${1-}"
  value="${value//\\/\\\\}"
  value="${value//\$/\\\$}"
  value="${value//\"/\\\"}"
  printf '"%s"' "${value}"
}

gen_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    date +%s%N | sha256sum | awk '{print $1}'
  fi
}

echo "=========================================="
echo " RemnaShop: интерактивная автоустановка"
echo "=========================================="
echo

prompt "APP_DIR" "Папка установки" "/opt/remnashop"
prompt "SERVICE_USER" "Системный пользователь сервисов" "remnashop"
prompt "SERVICE_GROUP" "Системная группа сервисов" "${SERVICE_USER}"
prompt "WEB_DOMAIN" "Домен админ-панели (например panel.example.com)" "panel.example.com"
prompt "WEB_PORT" "Внутренний порт веб-приложения" "8080"
prompt "TIMEZONE" "Таймзона" "Europe/Moscow"
prompt "ENVIRONMENT" "Окружение (dev/prod)" "production"

echo
echo "Telegram"
prompt_secret "BOT_TOKEN" "BOT_TOKEN"
require_non_empty "BOT_TOKEN" "BOT_TOKEN"
prompt "BOT_ADMIN_IDS" "BOT_ADMIN_IDS (через запятую)" ""
prompt "SUPPORT_USERNAME" "Username поддержки (без @)" "support"

echo
echo "Админ-панель"
prompt "ADMIN_USERNAME" "ADMIN_USERNAME" "admin"
prompt_secret "ADMIN_PASSWORD" "ADMIN_PASSWORD"
if [[ -z "${ADMIN_PASSWORD}" ]]; then
  ADMIN_PASSWORD="$(gen_secret | head -c 20)"
  echo "ADMIN_PASSWORD сгенерирован автоматически: ${ADMIN_PASSWORD}"
fi

echo
echo "Remnawave API"
prompt "REMNAWAVE_BASE_URL" "REMNAWAVE_BASE_URL" "https://remnawave.example.com/api/v1"
prompt_secret "REMNAWAVE_API_KEY" "REMNAWAVE_API_KEY"
require_non_empty "REMNAWAVE_API_KEY" "REMNAWAVE_API_KEY"

echo
echo "Платежи (можно оставить по умолчанию)"
prompt "PAYMENT_PROVIDER" "PAYMENT_PROVIDER" "none"
prompt_secret "PAYMENT_API_KEY" "PAYMENT_API_KEY (можно пусто)"
prompt_secret "PAYMENT_WEBHOOK_SECRET" "PAYMENT_WEBHOOK_SECRET (можно пусто)"

echo
prompt_yes_no "INSTALL_NGINX" "Установить и настроить Nginx?" "y"
SSL_ENABLED="false"
CERTBOT_EMAIL=""
if [[ "${INSTALL_NGINX}" == "true" ]]; then
  prompt_yes_no "SSL_ENABLED" "Настроить HTTPS через certbot?" "y"
  if [[ "${SSL_ENABLED}" == "true" ]]; then
    prompt "CERTBOT_EMAIL" "Email для certbot (обязательно для SSL)" ""
    require_non_empty "CERTBOT_EMAIL" "Email для certbot"
  fi
fi

prompt_yes_no "ENABLE_BACKUP_CRON" "Добавить cron на backup каждые 6 часов?" "y"

for v in BOT_TOKEN BOT_ADMIN_IDS SUPPORT_USERNAME ADMIN_USERNAME ADMIN_PASSWORD REMNAWAVE_BASE_URL REMNAWAVE_API_KEY PAYMENT_PROVIDER PAYMENT_API_KEY PAYMENT_WEBHOOK_SECRET WEB_DOMAIN TIMEZONE ENVIRONMENT CERTBOT_EMAIL; do
  normalize_single_line "${v}"
done

for v in BOT_TOKEN BOT_ADMIN_IDS SUPPORT_USERNAME ADMIN_USERNAME ADMIN_PASSWORD REMNAWAVE_BASE_URL REMNAWAVE_API_KEY PAYMENT_PROVIDER PAYMENT_API_KEY PAYMENT_WEBHOOK_SECRET WEB_DOMAIN TIMEZONE ENVIRONMENT CERTBOT_EMAIL; do
  assert_ascii "${v}"
done

BOT_ADMIN_IDS_JSON="$(normalize_admin_ids "${BOT_ADMIN_IDS}")"

SESSION_SECRET="$(gen_secret)"
DATABASE_URL="sqlite+aiosqlite:///${APP_DIR}/data/remnashop.db"
BACKUP_DIR="${APP_DIR}/backups"

echo
echo "Проверка параметров:"
echo "APP_DIR=${APP_DIR}"
echo "SERVICE_USER=${SERVICE_USER}"
echo "WEB_DOMAIN=${WEB_DOMAIN}"
echo "WEB_PORT=${WEB_PORT}"
echo "ENVIRONMENT=${ENVIRONMENT}"
echo "INSTALL_NGINX=${INSTALL_NGINX}"
echo "SSL_ENABLED=${SSL_ENABLED}"
echo
prompt_yes_no "CONFIRM" "Продолжить установку?" "y"
if [[ "${CONFIRM}" != "true" ]]; then
  echo "Установка отменена."
  exit 0
fi

echo
echo "==> Установка системных пакетов"
run_root apt-get update
run_root apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  git \
  rsync \
  curl

if [[ "${INSTALL_NGINX}" == "true" ]]; then
  run_root apt-get install -y nginx
  if [[ "${SSL_ENABLED}" == "true" ]]; then
    run_root apt-get install -y certbot python3-certbot-nginx
  fi
fi

echo "==> Подготовка пользователя и директорий"
if ! getent group "${SERVICE_GROUP}" >/dev/null 2>&1; then
  run_root groupadd --system "${SERVICE_GROUP}"
fi
if ! id -u "${SERVICE_USER}" >/dev/null 2>&1; then
  run_root useradd --system --home "${APP_DIR}" --shell /usr/sbin/nologin -g "${SERVICE_GROUP}" "${SERVICE_USER}"
fi

run_root mkdir -p "${APP_DIR}"
run_root mkdir -p "${APP_DIR}/data" "${BACKUP_DIR}" "${APP_DIR}/logs"

echo "==> Копирование проекта в ${APP_DIR}"
run_root rsync -a --delete \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "data" \
  --exclude "backups" \
  --exclude "logs" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  "${REPO_DIR}/" "${APP_DIR}/"

echo "==> Настройка прав"
run_root chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}"

echo "==> Создание виртуального окружения и установка зависимостей"
run_as_user "${SERVICE_USER}" python3 -m venv "${APP_DIR}/.venv"
run_as_user "${SERVICE_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip setuptools wheel
run_as_user "${SERVICE_USER}" "${APP_DIR}/.venv/bin/pip" install -e "${APP_DIR}"

echo "==> Генерация .env"
{
  printf 'APP_NAME=%s\n' "$(env_quote 'RemnaShop')"
  printf 'ENVIRONMENT=%s\n' "$(env_quote "${ENVIRONMENT}")"
  printf 'BASE_URL=%s\n' "$(env_quote "https://${WEB_DOMAIN}")"
  printf 'TIMEZONE=%s\n' "$(env_quote "${TIMEZONE}")"
  printf '\n'
  printf 'DATABASE_URL=%s\n' "$(env_quote "${DATABASE_URL}")"
  printf '\n'
  printf 'BOT_TOKEN=%s\n' "$(env_quote "${BOT_TOKEN}")"
  printf 'BOT_ADMIN_IDS=%s\n' "$(env_quote "${BOT_ADMIN_IDS_JSON}")"
  printf 'SUPPORT_USERNAME=%s\n' "$(env_quote "${SUPPORT_USERNAME}")"
  printf '\n'
  printf 'ADMIN_USERNAME=%s\n' "$(env_quote "${ADMIN_USERNAME}")"
  printf 'ADMIN_PASSWORD=%s\n' "$(env_quote "${ADMIN_PASSWORD}")"
  printf 'SESSION_SECRET=%s\n' "$(env_quote "${SESSION_SECRET}")"
  printf '\n'
  printf 'WEB_HOST=%s\n' "$(env_quote '127.0.0.1')"
  printf 'WEB_PORT=%s\n' "$(env_quote "${WEB_PORT}")"
  printf 'WEB_DOMAIN=%s\n' "$(env_quote "${WEB_DOMAIN}")"
  printf '\n'
  printf 'REMNAWAVE_BASE_URL=%s\n' "$(env_quote "${REMNAWAVE_BASE_URL}")"
  printf 'REMNAWAVE_API_KEY=%s\n' "$(env_quote "${REMNAWAVE_API_KEY}")"
  printf 'REMNAWAVE_TIMEOUT=%s\n' "$(env_quote '20')"
  printf 'REMNAWAVE_USERS_PATH=%s\n' "$(env_quote '/users')"
  printf 'REMNAWAVE_SUBSCRIPTIONS_PATH=%s\n' "$(env_quote '/subscriptions')"
  printf 'REMNAWAVE_SERVERS_PATH=%s\n' "$(env_quote '/servers')"
  printf 'REMNAWAVE_NODES_PATH=%s\n' "$(env_quote '/nodes')"
  printf 'REMNAWAVE_STATS_PATH=%s\n' "$(env_quote '/stats')"
  printf '\n'
  printf 'PAYMENT_PROVIDER=%s\n' "$(env_quote "${PAYMENT_PROVIDER}")"
  printf 'PAYMENT_API_KEY=%s\n' "$(env_quote "${PAYMENT_API_KEY}")"
  printf 'PAYMENT_WEBHOOK_SECRET=%s\n' "$(env_quote "${PAYMENT_WEBHOOK_SECRET}")"
  printf '\n'
  printf 'BACKUP_DIR=%s\n' "$(env_quote "${BACKUP_DIR}")"
} | run_root tee "${APP_DIR}/.env" >/dev/null

run_root chown "${SERVICE_USER}:${SERVICE_GROUP}" "${APP_DIR}/.env"
run_root chmod 600 "${APP_DIR}/.env"

echo "==> Инициализация БД"
run_as_user "${SERVICE_USER}" bash -lc "cd '${APP_DIR}' && '${APP_DIR}/.venv/bin/python' scripts/init_db.py"

echo "==> Создание systemd сервисов"
run_root tee /etc/systemd/system/remnashop-web.service >/dev/null <<EOF
[Unit]
Description=RemnaShop FastAPI admin panel
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python scripts/run_web.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

run_root tee /etc/systemd/system/remnashop-bot.service >/dev/null <<EOF
[Unit]
Description=RemnaShop Telegram bot
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
Group=${SERVICE_GROUP}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python scripts/run_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

run_root systemctl daemon-reload
run_root systemctl enable --now remnashop-web
run_root systemctl enable --now remnashop-bot

if [[ "${INSTALL_NGINX}" == "true" ]]; then
  echo "==> Настройка Nginx"
  run_root tee /etc/nginx/sites-available/remnashop-panel.conf >/dev/null <<EOF
server {
    listen 80;
    server_name ${WEB_DOMAIN};
    location / {
        proxy_pass http://127.0.0.1:${WEB_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 90s;
    }
}
EOF

  if [[ -L /etc/nginx/sites-enabled/default || -f /etc/nginx/sites-enabled/default ]]; then
    run_root rm -f /etc/nginx/sites-enabled/default
  fi
  run_root ln -sfn /etc/nginx/sites-available/remnashop-panel.conf /etc/nginx/sites-enabled/remnashop-panel.conf
  run_root nginx -t
  run_root systemctl enable --now nginx
  run_root systemctl reload nginx

  if [[ "${SSL_ENABLED}" == "true" ]]; then
    echo "==> Выпуск SSL сертификата через certbot"
    run_root certbot --nginx --non-interactive --agree-tos -m "${CERTBOT_EMAIL}" -d "${WEB_DOMAIN}" || {
      echo "Внимание: certbot завершился с ошибкой. Проверьте DNS и повторите вручную."
    }
  fi
fi

if [[ "${ENABLE_BACKUP_CRON}" == "true" ]]; then
  echo "==> Настройка cron для backup"
  run_root chmod +x "${APP_DIR}/deploy/scripts/backup.sh"
  run_root tee /etc/cron.d/remnashop-backup >/dev/null <<EOF
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 */6 * * * root BACKUP_DIR=${BACKUP_DIR} DB_FILE=${APP_DIR}/data/remnashop.db ${APP_DIR}/deploy/scripts/backup.sh >> ${APP_DIR}/logs/backup.log 2>&1
EOF
  run_root chmod 644 /etc/cron.d/remnashop-backup
fi

WEB_STATUS="$(run_root systemctl is-active remnashop-web || true)"
BOT_STATUS="$(run_root systemctl is-active remnashop-bot || true)"
NGINX_STATUS="not-installed"
if [[ "${INSTALL_NGINX}" == "true" ]]; then
  NGINX_STATUS="$(run_root systemctl is-active nginx || true)"
fi

if [[ "${SSL_ENABLED}" == "true" ]]; then
  PANEL_URL="https://${WEB_DOMAIN}/admin/login"
else
  PANEL_URL="http://${WEB_DOMAIN}/admin/login"
fi

echo
echo "=========================================="
echo " Установка завершена"
echo "=========================================="
echo "Папка проекта: ${APP_DIR}"
echo "Web URL: ${PANEL_URL}"
echo "Admin login: ${ADMIN_USERNAME}"
echo "Admin password: ${ADMIN_PASSWORD}"
echo
echo "Статус сервисов:"
echo "  remnashop-web: ${WEB_STATUS}"
echo "  remnashop-bot: ${BOT_STATUS}"
echo "  nginx: ${NGINX_STATUS}"
echo
echo "Полезные команды:"
echo "  sudo systemctl status remnashop-web remnashop-bot"
echo "  sudo journalctl -u remnashop-web -f"
echo "  sudo journalctl -u remnashop-bot -f"
echo "  sudo systemctl restart remnashop-web remnashop-bot"
echo "  sudo cat ${APP_DIR}/.env"
if [[ "${INSTALL_NGINX}" == "true" ]]; then
  echo "  sudo nginx -t && sudo systemctl reload nginx"
fi
if [[ "${ENABLE_BACKUP_CRON}" == "true" ]]; then
  echo "  sudo cat /etc/cron.d/remnashop-backup"
fi
echo
echo "Важно: сохраните admin пароль в безопасном месте."

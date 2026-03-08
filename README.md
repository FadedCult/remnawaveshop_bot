# RemnaShop

Telegram-бот на `aiogram` + веб-панель на `FastAPI` для продажи VPN-подписок через API Remnawave.

## Что реализовано

- Пользовательский Telegram-бот:
  - Главное меню: подписка, тарифы, баланс, поддержка, язык RU/EN, подключение.
  - Покупка и продление подписки.
  - Тикеты поддержки: создание, просмотр, ответы.
  - Опросы: ответы через команды `/survey_<id>`.
- Админ-функции в Telegram:
  - Статистика пользователей.
  - Тарифы (создание/удаление).
  - Тикеты (просмотр, ответ, закрытие).
  - Рассылки и опросы.
  - Синхронизация и статистика серверов Remnawave.
- Веб-панель `/admin` (дублирует и расширяет админ-часть бота):
  - Дашборд, аудит действий.
  - Пользователи: поиск, профиль, баланс, сообщения, удаление.
  - Тарифы: CRUD.
  - Поддержка: тикеты, ответы, закрытие.
  - Сообщения: рассылки, промо, сегментация, периодические отправки.
  - Опросы: создание, отправка, сбор ответов.
  - Сервера: синхронизация, статистика, снапшоты.
  - Система: интеграции и генератор `ADMIN_PASSWORD_HASH`.
- Безопасность:
  - Доступ в админку только через единый логин/пароль из `.env`.
  - Поддержка HTTPS через Nginx reverse-proxy.
  - Логи действий администраторов.
- Коммерческие задачи:
  - Логи платежей и подписок.
  - Обработка ошибок Remnawave + уведомления админам в Telegram.
  - Резервное копирование БД (скрипт + cron).
  - Подготовлено разделение процессов bot/web на разные серверы.

## Структура

```text
src/app/
  bot/                # aiogram handlers/keyboards/states
  web/                # FastAPI app + admin templates
  db/                 # models, repositories, session, bootstrap
  services/           # remnawave, subscriptions, tickets, broadcasts, surveys, scheduler
deploy/
  nginx/              # Nginx vhost
  systemd/            # systemd units
  scripts/            # backup script
scripts/
  run_bot.py
  run_web.py
  init_db.py
  hash_password.py
```

## Требования

- Python 3.11+
- Ubuntu 22.04+ (для production)
- Telegram Bot Token
- Remnawave API URL + API key

## Быстрый старт (локально)

1. Создать окружение и установить зависимости:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

2. Подготовить конфиг:

```bash
cp .env.example .env
```

3. Заполнить `.env`:

- `BOT_TOKEN`
- `BOT_ADMIN_IDS`
- `ADMIN_USERNAME`, `ADMIN_PASSWORD` (или `ADMIN_PASSWORD_HASH`)
- `REMNAWAVE_BASE_URL`, `REMNAWAVE_API_KEY`

4. Инициализировать БД:

```bash
python scripts/init_db.py
```

5. Запустить веб-панель:

```bash
python scripts/run_web.py
```

6. Запустить бота:

```bash
python scripts/run_bot.py
```

## Настройка Remnawave API

В `.env` вынесены пути API:

- `REMNAWAVE_USERS_PATH`
- `REMNAWAVE_SUBSCRIPTIONS_PATH`
- `REMNAWAVE_SERVERS_PATH`
- `REMNAWAVE_NODES_PATH`
- `REMNAWAVE_STATS_PATH`

Если в вашей версии Remnawave другие endpoint-и, замените значения без изменения кода.

## Ubuntu deployment (systemd + Nginx + HTTPS)

### Auto installer (interactive)

```bash
chmod +x deploy/scripts/install.sh
./deploy/scripts/install.sh
```

What this script does:

- Asks for required values (`BOT_TOKEN`, admin credentials, `REMNAWAVE_*`, domain, SSL, etc.).
- Installs system dependencies (`python3`, `venv`, `nginx`, `certbot` when needed).
- Copies project to target dir (default: `/opt/remnashop`), creates `.venv`, installs package.
- Generates `.env`, initializes DB, configures and starts `systemd` services.
- Configures `nginx` reverse proxy and optional HTTPS.
- Optionally configures backup cron.
- Prints final summary with URL, credentials, service statuses and useful commands.

### 1. Подготовка

```bash
sudo mkdir -p /opt/remnashop
sudo chown -R $USER:$USER /opt/remnashop
cd /opt/remnashop
git clone <your-repo> .
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
python scripts/init_db.py
```

### 2. systemd

```bash
sudo cp deploy/systemd/remnashop-web.service /etc/systemd/system/
sudo cp deploy/systemd/remnashop-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now remnashop-web
sudo systemctl enable --now remnashop-bot
```

### 3. Nginx

```bash
sudo cp deploy/nginx/remnashop-panel.conf /etc/nginx/sites-available/remnashop-panel.conf
sudo ln -s /etc/nginx/sites-available/remnashop-panel.conf /etc/nginx/sites-enabled/remnashop-panel.conf
sudo nginx -t
sudo systemctl reload nginx
```

### 4. SSL (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d panel.example.com
```

## Резервное копирование

```bash
chmod +x deploy/scripts/backup.sh
```

Пример cron (каждые 6 часов):

```bash
0 */6 * * * BACKUP_DIR=/opt/remnashop/backups DB_FILE=/opt/remnashop/data/remnashop.db /opt/remnashop/deploy/scripts/backup.sh
```

## Масштабирование

- Веб-панель и бот можно запускать на разных серверах.
- БД лучше перенести с SQLite на PostgreSQL (`DATABASE_URL=postgresql+asyncpg://...`).
- Для высоких нагрузок вынести планировщик (`AppScheduler`) в отдельный worker-процесс.

## Полезные команды

Сгенерировать bcrypt hash для админ-пароля:

```bash
python scripts/hash_password.py "StrongPassword123!"
```

Миграции:

```bash
alembic upgrade head
```

## Важные замечания

- Платежный провайдер сейчас через stub (`PaymentService`), подключите реальный SDK в `src/app/services/payment_stub.py`.
- Логика Remnawave может потребовать адаптации payload/endpoint под вашу версию API.
- Перед production обязательно проверьте rate-limits Telegram и политику ретраев для внешних API.

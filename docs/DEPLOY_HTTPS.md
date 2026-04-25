# HTTPS Deployment (Let's Encrypt)

Этот документ показывает два рабочих варианта публикации AIRouter по HTTPS:
- Nginx + certbot (Let's Encrypt)
- Caddy (автоматические сертификаты из коробки)

Перед началом:
- домен уже указывает на сервер (A/AAAA запись)
- в firewall открыты `80/tcp` и `443/tcp`
- AIRouter работает локально, например `127.0.0.1:8000`

## Вариант 1: Nginx + certbot

Самый быстрый путь через готовый скрипт:

```bash
sudo bash scripts/setup_https_nginx_certbot.sh \
  --domain api.example.com \
  --email admin@example.com \
  --upstream-host 127.0.0.1 \
  --upstream-port 8000
```

Что делает скрипт:
- устанавливает `nginx`, `certbot`, `python3-certbot-nginx`
- создает конфиг reverse proxy для AIRouter
- включает сайт, проверяет конфиг и перезапускает Nginx
- запрашивает сертификат Let's Encrypt
- включает HTTP -> HTTPS redirect

Проверка:

```bash
curl -I https://api.example.com/v1/models
sudo certbot renew --dry-run
```

## Вариант 2: Caddy (альтернатива)

Если нужен минимальный конфиг и авто-renew без ручного certbot.

1) Установите Caddy (Ubuntu):

```bash
sudo apt-get update
sudo apt-get install -y caddy
```

2) Создайте `/etc/caddy/Caddyfile`:

```caddy
api.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

3) Перезапустите:

```bash
sudo systemctl enable caddy
sudo systemctl restart caddy
```

Проверка:

```bash
curl -I https://api.example.com/v1/models
```

## Рекомендации для production

- Для AIRouter systemd-сервиса слушайте только loopback: `--host 127.0.0.1`.
- Не публикуйте `:8000` напрямую в интернет, отдавайте наружу только `:443`.
- Для больших аудио/файлов поднимите `client_max_body_size` в Nginx.
- После изменений прокси проверяйте health: `/v1/models` и `/admin/dashboard`.

## Типовые проблемы

- `Timeout during connect` в certbot:
  - DNS еще не применился или закрыт порт `80/tcp`.
- `unauthorized` от Let's Encrypt:
  - домен указывает не на тот сервер.
- WebSocket/SSE обрываются:
  - проверьте `proxy_set_header Upgrade`, `Connection`, и `proxy_read_timeout`.

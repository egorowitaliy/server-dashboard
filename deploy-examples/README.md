# Примеры системной конфигурации

Каталог содержит заготовки для установки Server Dashboard на Debian-подобную систему:

- `systemd/server-dashboard.service` — привилегированная служба;
- `php-fpm/server-dashboard.conf` — отдельный пул PHP-FPM;
- `nginx/server-dashboard.conf` — виртуальный сервер Nginx;
- `tmpfiles/server-dashboard.conf` — каталоги, журналы и очистка временных файлов;
- `logrotate/server-dashboard` — ротация журналов.

Это примеры, а не универсальный установщик. Перед копированием проверьте пути, версию PHP-FPM, адрес прослушивания, `server_name` и разрешённую сеть.

Порядок установки описан в `docs/INSTALLATION.md`.

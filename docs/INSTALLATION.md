# Установка Server Dashboard

## 1. Что понадобится

Server Dashboard рассчитан на Linux с systemd. Для базовой установки нужны:

- Python 3.11 или новее;
- пакет `markdown-it-py` 3.x;
- PHP 8.2 или новее с PHP-FPM;
- Nginx;
- systemd.

Дополнительные программы нужны только при включении соответствующих функций:

- Docker — для страницы контейнеров;
- Fail2Ban — для страницы блокировок;
- smartmontools — для SMART;
- собственные timer-юниты systemd — для раздела расписания.

Примеры ниже ориентированы на Debian-подобную систему. Имена пакетов и службы PHP-FPM в других дистрибутивах могут отличаться.

## 2. Размещение файлов

Рекомендуемая схема:

```text
/opt/server-dashboard/                 код приложения
/etc/server-dashboard/config.toml      основная конфигурация
/etc/server-dashboard/secrets.ini      пароль и параметры входа
/opt/server-dashboard-extensions/      внешние модули
/var/log/server-dashboard/             журналы
/run/server-dashboard/                 Unix-сокет и временные файлы
```

Конфигурация и секреты находятся вне каталога приложения. Благодаря этому обновление `/opt/server-dashboard` не должно затирать локальные настройки.

## 3. Системные группы и пользователь веб-части

Нужны две группы и отдельный непривилегированный пользователь PHP-FPM:

- `server-dashboard` — доступ к Unix-сокету привилегированной службы;
- `server-dashboard-web` — пользователь и группа веб-части.

Пример команд для новой системы:

```bash
groupadd --system server-dashboard
groupadd --system server-dashboard-web
useradd   --system   --no-create-home   --shell /usr/sbin/nologin   --gid server-dashboard-web   --groups server-dashboard   server-dashboard-web
```

Если такие учётные записи уже существуют, сначала проверьте их через `getent` и `id`, а не создавайте повторно.

## 4. Установка кода

Скопируйте содержимое репозитория в `/opt/server-dashboard`:

```bash
install -d -o root -g root -m 0755 /opt/server-dashboard
```

После копирования код приложения должен принадлежать `root` и не должен быть доступен на запись непривилегированным пользователям.

Для зависимостей Python можно использовать системный пакет дистрибутива или отдельное виртуальное окружение. Базовая зависимость проекта перечислена в `requirements.txt`.

## 5. Основная конфигурация

Создайте каталог и скопируйте пример:

```bash
install -d -o root -g server-dashboard-web -m 0750 /etc/server-dashboard
cp /opt/server-dashboard/config.example.toml /etc/server-dashboard/config.toml
mcedit /etc/server-dashboard/config.toml
```

Настройте имя сервера, часовой пояс и только те модули, которые нужны на этом хосте.

Проверьте файл до запуска службы:

```bash
/opt/server-dashboard/scripts/check-config.py --no-host
```

## 6. Пароль

Задайте пользователя веб-интерфейса:

```bash
/opt/server-dashboard/scripts/dashboard-set-password admin
```

Скрипт создаёт `/etc/server-dashboard/secrets.ini`, если файла ещё нет. Пароль сохраняется только в виде хеша. При повторной смене пароля уже настроенные интервалы сессии и ограничения попыток входа сохраняются.

## 7. Временные каталоги и журналы

Установите файл tmpfiles:

```bash
cp /opt/server-dashboard/deploy-examples/tmpfiles/server-dashboard.conf   /etc/tmpfiles.d/server-dashboard.conf
systemd-tmpfiles --create /etc/tmpfiles.d/server-dashboard.conf
```

Он создаёт:

- `/var/log/server-dashboard/audit.log`;
- `/var/log/server-dashboard/php-error.log`;
- `/run/server-dashboard/sessions`;
- `/run/server-dashboard/auth`.

Для старых сессий и файлов ограничения попыток входа задана возрастная очистка.

Установите правила ротации журналов:

```bash
cp /opt/server-dashboard/deploy-examples/logrotate/server-dashboard   /etc/logrotate.d/server-dashboard
```

## 8. Привилегированная служба

Установите unit:

```bash
cp /opt/server-dashboard/deploy-examples/systemd/server-dashboard.service   /etc/systemd/system/server-dashboard.service
systemctl daemon-reload
```

Служба запускается от `root`, но ограничена настройками systemd и принимает запросы только через Unix-сокет. Не ослабляйте её ограничения ради внешнего модуля; модулю с особыми требованиями лучше выделить отдельную службу.

## 9. PHP-FPM

Скопируйте пример пула, при необходимости изменив путь под свою версию PHP:

```bash
cp /opt/server-dashboard/deploy-examples/php-fpm/server-dashboard.conf   /etc/php/8.4/fpm/pool.d/server-dashboard.conf
php-fpm8.4 -t
systemctl reload php8.4-fpm.service
```

Пул работает от `server-dashboard-web` и использует отдельный Unix-сокет `/run/php/server-dashboard.sock`.

## 10. Nginx

Скопируйте пример виртуального сервера:

```bash
cp /opt/server-dashboard/deploy-examples/nginx/server-dashboard.conf   /etc/nginx/sites-available/server-dashboard.conf
mcedit /etc/nginx/sites-available/server-dashboard.conf
```

Обязательно замените:

- адрес в `listen`;
- `server_name`;
- сеть в `allow`.

Пример использует адреса TEST-NET и не предназначен для запуска без правки.

Для `/api/action` оставлен отдельный `fastcgi_read_timeout 75s`. Он нужен потому, что разрешённый перезапуск службы или контейнера может занимать заметно дольше обычного запроса чтения.

Проверьте и включите конфигурацию:

```bash
nginx -t
systemctl reload nginx.service
```

## 11. Первый запуск

Проверьте конфигурацию уже с состоянием хоста:

```bash
/opt/server-dashboard/scripts/check-config.py
```

Запустите службу:

```bash
systemctl enable --now server-dashboard.service
```

Проверьте связь с ней:

```bash
/opt/server-dashboard/scripts/dashboard-rpc health --pretty
/opt/server-dashboard/scripts/dashboard-rpc modules.list --pretty
```

После этого откройте веб-интерфейс из разрешённой внутренней сети.

## 12. Что проверить после установки

- страница входа принимает созданный пароль;
- отключённые модули отсутствуют в меню;
- на главной странице нет ложных предупреждений о выключенных модулях;
- разрешённые административные действия доступны только для объектов из списков разрешений;
- `audit.log` получает запись после входа;
- `php-error.log` существует и принадлежит `server-dashboard-web`;
- `systemctl --failed` не показывает ошибок, связанных с Dashboard.

Дальнейшая настройка описана в [CONFIGURATION.md](CONFIGURATION.md).

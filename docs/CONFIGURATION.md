# Настройка Server Dashboard

Основной файл — `/etc/server-dashboard/config.toml`. На Linux его удобно редактировать через `mcedit`.

После каждого изменения выполняйте:

```bash
/opt/server-dashboard/scripts/check-config.py
```

Большинство параметров перечитываются при запросе, поэтому перезапуск службы обычно не требуется. Если менялись systemd, PHP-FPM или Nginx, примените изменения соответствующей службой.

## Общие параметры

```toml
schema = 1

[dashboard]
server_name = "My Server"
timezone = "Europe/Moscow"
```

`server_name` — имя сервера в шапке, на странице входа и в заголовке браузера. Слово `Dashboard` приложение добавляет само.

`timezone` — часовой пояс в формате IANA, например `UTC`, `Europe/Moscow`, `Europe/Berlin`.

## Встроенные страницы

```toml
[modules]
overview = true
services = true
docker = false
fail2ban = false
system = true
docs = false
audit = true
```

Значение `false` означает не только скрытие ссылки в меню. Операции выключенного модуля также становятся недоступны, а главная страница перестаёт опрашивать его источники данных.

## Страница «Система»

```toml
[system]
storage = true
smart = false
schedule = true
```

Каждый компонент можно выключить отдельно. Выключенный компонент не опрашивается и не оставляет пустой блок в интерфейсе.

## Главная страница

```toml
[host]
cpu_temperature_type = "x86_pkg_temp"
live_refresh_seconds = 5
```

`cpu_temperature_type` — значение файла `type` нужной зоны из `/sys/class/thermal/thermal_zone*/`.

`live_refresh_seconds` — период обновления текущей загрузки процессора, температуры и памяти. Допустимый диапазон — от 2 до 60 секунд. Время работы сервера между запросами увеличивается в браузере без отдельного обращения к серверу.

## Хранилища

Используются при `system.storage = true`:

```toml
[[storage]]
id = "system"
name = "Системный диск"
path = "/"
warn_percent = 80
error_percent = 90
```

- `id` — уникальный идентификатор;
- `name` — подпись в интерфейсе;
- `path` — существующий абсолютный путь внутри нужной файловой системы;
- `warn_percent` — порог предупреждения;
- `error_percent` — порог ошибки.

Порог предупреждения должен быть меньше порога ошибки.

## Службы systemd

Используются при `modules.services = true`:

```toml
[[services]]
id = "nginx"
name = "Nginx"
unit = "nginx.service"
mode = "daemon"
restart = true
```

`mode` принимает два значения:

- `daemon` — обычная постоянно работающая служба;
- `oneshot` — одноразовая служба, для которой нормальным состоянием может быть завершённый запуск.

`restart = true` разрешает перезапуск из интерфейса. Если указано `false`, служба только отображается.

## Docker

Используется при `modules.docker = true`:

```toml
[docker]
restart_allow = ["jellyfin", "nextcloud"]

[docker.names]
jellyfin = "Jellyfin"
nextcloud = "Nextcloud"
```

Dashboard показывает контейнеры, которые видит Docker. Перезапустить из интерфейса можно только контейнеры из `restart_allow`.

Таблица `docker.names` задаёт понятные подписи. Если имени нет, используется техническое имя контейнера.

## Fail2Ban

Используется при `modules.fail2ban = true`:

```toml
[fail2ban]
unban_allow = ["sshd"]

[fail2ban.names]
sshd = "SSH"
```

Снять блокировку через интерфейс можно только в jail из `unban_allow`. Остальные jail остаются доступными только для просмотра.

## SMART

Используется при `modules.system = true` и `system.smart = true`:

```toml
[smart]

[[smart.disks]]
id = "system-ssd"
name = "Системный SSD"
path = "/dev/nvme0"
type = "nvme"

[[smart.disks]]
id = "data-hdd"
name = "Диск данных"
path = "/dev/sda"
type = "ata"
```

Поддерживаются типы `ata` и `nvme`. Устройства перечисляются явно; Dashboard не пытается автоматически управлять всеми дисками системы.

## Расписание systemd

Используется при `system.schedule = true`:

```toml
[[schedule]]
id = "backup"
name = "Резервное копирование"
timer = "backup.timer"
```

Dashboard только показывает время последнего и следующего запуска, а также текущее выполнение связанной службы. Запуск timer-юнитов из веб-интерфейса не предусмотрен.

## Документация

Используется при `modules.docs = true`:

```toml
[docs]
path = "/srv/docs"
recursive = true
extension = ".md"
```

Раздел работает только на чтение. Путь к документу проверяется относительно заданного каталога; выход наружу через `..` или символическую ссылку запрещён. Скрытые файлы и скрытые каталоги также не выдаются.

## Журнал действий

Для `modules.audit = true` дополнительных параметров не требуется. Журнал хранится в `/var/log/server-dashboard/audit.log`, создаётся через tmpfiles и ротируется правилами из `deploy-examples/logrotate/`.

## Внешние модули

```toml
[extensions]
root = "/opt/server-dashboard-extensions"
enabled = ["my-module"]
```

`root` должен быть абсолютным путём. Включённые модули перечисляются явно. Идентификаторы встроенных страниц зарезервированы и не могут использоваться внешним модулем.

Код серверной части внешнего модуля выполняется внутри привилегированной службы, поэтому устанавливать следует только доверенные модули. Требования к владельцам, правам и структуре описаны в [MODULE-DEVELOPMENT.md](MODULE-DEVELOPMENT.md).

## Секреты и параметры входа

Файл `/etc/server-dashboard/secrets.ini` создаёт `dashboard-set-password`.

Пример структуры:

```ini
[auth]
username = "admin"
password_hash = "..."

session_idle_seconds = 28800
max_failures = 3
failure_window_seconds = 600
lock_seconds = 900
```

Не переносите `password_hash` в основной `config.toml` и не публикуйте `secrets.ini` в репозитории.

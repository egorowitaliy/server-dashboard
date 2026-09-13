# Эксплуатация и обновление

## Проверка состояния

Основные команды диагностики:

```bash
/opt/server-dashboard/scripts/check-config.py
/opt/server-dashboard/scripts/dashboard-rpc health --pretty
/opt/server-dashboard/scripts/dashboard-rpc modules.list --pretty
systemctl status server-dashboard.service --no-pager
```

`check-config.py` проверяет структуру TOML и, если не указан `--no-host`, доступность настроенных служб, дисков, Docker, Fail2Ban, документации и внешних модулей.

## Журналы

```text
/var/log/server-dashboard/audit.log       входы и административные действия
/var/log/server-dashboard/php-error.log   ошибки PHP
/var/log/server-dashboard/access.log      запросы Nginx
/var/log/server-dashboard/nginx-error.log ошибки Nginx
```

Не используйте `audit.log` как общий отладочный журнал: его назначение — фиксировать входы и действия администратора.

## Смена пароля

```bash
/opt/server-dashboard/scripts/dashboard-set-password admin
```

При смене пароля существующие параметры времени сессии и ограничения попыток входа сохраняются.

## Отключение функции без удаления кода

Страницы отключаются в `[modules]`, части страницы «Система» — в `[system]`, внешние модули — удалением идентификатора из `[extensions].enabled`.

После изменения проверьте:

```bash
/opt/server-dashboard/scripts/check-config.py
```

## Обновление ядра

Конфигурация, секреты и внешние модули находятся вне `/opt/server-dashboard`. Безопасная последовательность обновления:

1. сохранить резервную копию текущего `/opt/server-dashboard`;
2. распаковать новую версию в отдельный каталог;
3. сравнить `config.example.toml` и `deploy-examples/` с установленной конфигурацией;
4. выполнить `check-config.py --no-host` из новой версии;
5. заменить каталог приложения;
6. при изменении системных примеров обновить соответствующие файлы в `/etc`;
7. выполнить `systemctl daemon-reload`, `systemd-tmpfiles --create`, проверку PHP-FPM и `nginx -t`;
8. перезапустить `server-dashboard.service` и перезагрузить PHP-FPM/Nginx;
9. выполнить `dashboard-rpc health --pretty` и проверить веб-интерфейс.

Не удаляйте предыдущий каталог приложения до завершения проверки новой версии.

## Обновление внешнего модуля

Внешний модуль обновляется отдельно от ядра. Перед заменой проверьте его `README`, версию API в `manifest.toml` и изменения локального `config.toml`.

## Если веб-интерфейс недоступен

Проверяйте цепочку сверху вниз:

1. `nginx -t` и состояние Nginx;
2. состояние пула PHP-FPM и наличие `/run/php/server-dashboard.sock`;
3. `systemctl status server-dashboard.service`;
4. наличие `/run/server-dashboard/dashboard.sock`;
5. `dashboard-rpc health --pretty`;
6. `check-config.py`.

Так проще отделить ошибку веб-сервера от ошибки конфигурации или привилегированной службы.

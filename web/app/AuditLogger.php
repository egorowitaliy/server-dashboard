<?php

declare(strict_types=1);

final class AuditLogger
{
    private const PATH =
        '/var/log/server-dashboard/audit.log';

    public static function write(
        string $action,
        string $result,
        string $user,
        string $ip,
        array $extra = []
    ): void {
        $parts = [
            self::localTimestamp(),
            'user=' . self::clean($user),
            'ip=' . self::clean($ip),
            'action=' . self::clean($action),
        ];

        foreach ($extra as $key => $value) {
            if (
                !is_string($key)
                || !is_scalar($value)
            ) {
                continue;
            }

            $parts[] =
                self::clean($key)
                . '='
                . self::clean((string) $value);
        }

        $parts[] =
            'result=' . self::clean($result);

        $line = implode(' ', $parts) . PHP_EOL;

        $handle = @fopen(
            self::PATH,
            'ab'
        );

        if (!is_resource($handle)) {
            error_log(
                'server_dashboard_audit_open_failed'
            );
            return;
        }

        try {
            if (@flock($handle, LOCK_EX)) {
                fwrite($handle, $line);
                fflush($handle);
                flock($handle, LOCK_UN);
            }
        } finally {
            fclose($handle);
        }
    }

    private static function localTimestamp(): string
    {
        $timezone = null;

        $timezoneFile = '/etc/timezone';

        if (is_readable($timezoneFile)) {
            $value = trim(
                (string) file_get_contents(
                    $timezoneFile
                )
            );

            if ($value !== '') {
                $timezone = $value;
            }
        }

        if ($timezone === null) {
            $link = @readlink(
                '/etc/localtime'
            );

            if (
                is_string($link)
                && str_contains(
                    $link,
                    '/zoneinfo/'
                )
            ) {
                $timezone = substr(
                    $link,
                    strpos(
                        $link,
                        '/zoneinfo/'
                    ) + 10
                );
            }
        }

        try {
            $zone = new DateTimeZone(
                $timezone ?? 'UTC'
            );
        } catch (Throwable) {
            $zone = new DateTimeZone('UTC');
        }

        return (
            new DateTimeImmutable(
                'now',
                $zone
            )
        )->format(DATE_ATOM);
    }

    private static function clean(
        string $value
    ): string {
        $value = preg_replace(
            '/[\x00-\x20\x7f]+/u',
            '_',
            $value
        ) ?? '_';

        return substr($value, 0, 256);
    }
}

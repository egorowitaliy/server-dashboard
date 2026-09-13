<?php

declare(strict_types=1);

final class Secrets
{
    private const PRIMARY_PATH =
        '/etc/server-dashboard/secrets.ini';

    private const LEGACY_PATH =
        '/opt/server-dashboard/secrets.ini';

    private static function path(): string
    {
        return is_file(self::PRIMARY_PATH)
            ? self::PRIMARY_PATH
            : self::LEGACY_PATH;
    }

    public static function auth(): array
    {
        $config = @parse_ini_file(
            self::path(),
            true,
            INI_SCANNER_TYPED
        );

        if (
            !is_array($config)
            || !isset($config['auth'])
            || !is_array($config['auth'])
        ) {
            throw new RuntimeException(
                'Auth configuration is unavailable'
            );
        }

        $auth = $config['auth'];

        $username = $auth['username'] ?? null;
        $passwordHash = $auth['password_hash'] ?? null;

        if (
            !is_string($username)
            || $username === ''
            || !is_string($passwordHash)
        ) {
            throw new RuntimeException(
                'Invalid auth configuration'
            );
        }

        return [
            'username' => $username,
            'password_hash' => $passwordHash,

            'session_idle_seconds' =>
                self::positiveInt(
                    $auth['session_idle_seconds'] ?? null,
                    28800
                ),

            'max_failures' =>
                self::positiveInt(
                    $auth['max_failures'] ?? null,
                    3
                ),

            'failure_window_seconds' =>
                self::positiveInt(
                    $auth['failure_window_seconds'] ?? null,
                    600
                ),

            'lock_seconds' =>
                self::positiveInt(
                    $auth['lock_seconds'] ?? null,
                    900
                ),
        ];
    }

    private static function positiveInt(
        mixed $value,
        int $default
    ): int {
        if (
            !is_int($value)
            || $value <= 0
        ) {
            return $default;
        }

        return $value;
    }
}

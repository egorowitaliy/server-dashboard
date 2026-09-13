<?php

declare(strict_types=1);

final class Auth
{
    private const SESSION_DIRECTORY =
        '/run/server-dashboard/sessions';

    private const SESSION_NAME =
        'SERVER_DASHBOARD';

    public static function bootstrap(
        array $authConfig
    ): void {
        if (session_status() === PHP_SESSION_ACTIVE) {
            return;
        }

        session_name(
            self::SESSION_NAME
        );

        session_save_path(
            self::SESSION_DIRECTORY
        );

        $secure =
            isset($_SERVER['HTTPS'])
            && $_SERVER['HTTPS'] !== ''
            && $_SERVER['HTTPS'] !== 'off';

        session_set_cookie_params(
            [
                'lifetime' => 0,
                'path' => '/',
                'domain' => '',
                'secure' => $secure,
                'httponly' => true,
                'samesite' => 'Strict',
            ]
        );

        if (!session_start()) {
            throw new RuntimeException(
                'Unable to start session'
            );
        }

        self::expireIdleSession(
            (int) $authConfig[
                'session_idle_seconds'
            ]
        );
    }

    public static function isAuthenticated(): bool
    {
        return (
            ($_SESSION['authenticated'] ?? false)
            === true
            && is_string(
                $_SESSION['user'] ?? null
            )
        );
    }

    public static function user(): ?string
    {
        return self::isAuthenticated()
            ? $_SESSION['user']
            : null;
    }

    public static function login(
        string $username
    ): void {
        session_regenerate_id(true);

        $_SESSION = [
            'authenticated' => true,
            'user' => $username,
            'last_activity' => time(),
        ];

        Csrf::rotate();
    }

    public static function touch(): void
    {
        if (self::isAuthenticated()) {
            $_SESSION['last_activity'] =
                time();
        }
    }

    public static function logout(): void
    {
        $_SESSION = [];

        if (ini_get('session.use_cookies')) {
            $params =
                session_get_cookie_params();

            setcookie(
                session_name(),
                '',
                [
                    'expires' => time() - 42000,
                    'path' => $params['path'],
                    'domain' => $params['domain'],
                    'secure' => $params['secure'],
                    'httponly' => $params['httponly'],
                    'samesite' =>
                        $params['samesite'] ?? 'Strict',
                ]
            );
        }

        session_destroy();
    }

    private static function expireIdleSession(
        int $idleSeconds
    ): void {
        if (!self::isAuthenticated()) {
            return;
        }

        $last =
            $_SESSION['last_activity'] ?? 0;

        if (
            !is_int($last)
            || $last <= 0
            || (time() - $last) > $idleSeconds
        ) {
            self::logout();

            session_start();

            return;
        }

        $_SESSION['last_activity'] =
            time();
    }
}

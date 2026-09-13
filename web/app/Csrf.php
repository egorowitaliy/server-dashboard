<?php

declare(strict_types=1);

final class Csrf
{
    public static function token(): string
    {
        $token = $_SESSION['csrf_token'] ?? null;

        if (
            !is_string($token)
            || strlen($token) !== 64
        ) {
            $token = bin2hex(
                random_bytes(32)
            );

            $_SESSION['csrf_token'] = $token;
        }

        return $token;
    }

    public static function verify(
        mixed $token
    ): bool {
        $expected =
            $_SESSION['csrf_token'] ?? null;

        return (
            is_string($token)
            && is_string($expected)
            && hash_equals($expected, $token)
        );
    }

    public static function rotate(): void
    {
        $_SESSION['csrf_token'] =
            bin2hex(random_bytes(32));
    }
}

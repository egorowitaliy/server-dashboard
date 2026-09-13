<?php

declare(strict_types=1);

final class DashboardIdentity
{
    private const FALLBACK_SERVER_NAME =
        'Server';

    private const PRODUCT_NAME =
        'Dashboard';

    public static function load(): array
    {
        $serverName =
            self::FALLBACK_SERVER_NAME;

        try {
            $data =
                (new DaemonClient())
                ->request(
                    'modules.list'
                );

            $value =
                $data['server_name']
                ?? null;

            if (
                is_string($value)
                && trim($value) !== ''
            ) {
                $serverName =
                    trim($value);
            }

        } catch (Throwable) {
            /*
             * Login должен оставаться доступным,
             * даже если privileged daemon временно
             * не отвечает.
             */
        }

        return [
            'server_name' =>
                $serverName,

            'product_name' =>
                self::PRODUCT_NAME,

            'title' =>
                $serverName
                . ' '
                . self::PRODUCT_NAME,
        ];
    }
}

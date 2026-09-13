<?php

declare(strict_types=1);

final class DaemonClientException extends RuntimeException
{
    public function __construct(
        private readonly string $daemonCode,
        string $message
    ) {
        parent::__construct($message);
    }

    public function daemonCode(): string
    {
        return $this->daemonCode;
    }
}


final class DaemonClient
{
    private const SOCKET =
        'unix:///run/server-dashboard/dashboard.sock';

    private const PROTOCOL_VERSION = 1;
    private const CONNECT_TIMEOUT = 2.0;
    private const READ_TIMEOUT = 12;
    private const ACTION_TIMEOUT = 70;
    private const MAX_RESPONSE_BYTES = 2 * 1024 * 1024;

    public function request(
        string $operation,
        array $params = [],
        bool $action = false
    ): array {
        if (
            preg_match(
                '/\A[a-z][a-z0-9_.-]{0,127}\z/D',
                $operation
            ) !== 1
        ) {
            throw new RuntimeException(
                'Invalid daemon operation'
            );
        }

        if (count($params) > 32) {
            throw new RuntimeException(
                'Too many daemon parameters'
            );
        }

        $requestId = bin2hex(random_bytes(16));

        $request = [
            'version' => self::PROTOCOL_VERSION,
            'id' => $requestId,
            'op' => $operation,
            'params' => $params !== []
                ? $params
                : new stdClass(),
        ];

        $payload = json_encode(
            $request,
            JSON_THROW_ON_ERROR
            | JSON_UNESCAPED_UNICODE
            | JSON_UNESCAPED_SLASHES
        ) . "\n";

        $errno = 0;
        $errstr = '';

        $stream = @stream_socket_client(
            self::SOCKET,
            $errno,
            $errstr,
            self::CONNECT_TIMEOUT,
            STREAM_CLIENT_CONNECT
        );

        if (!is_resource($stream)) {
            throw new RuntimeException(
                'Dashboard daemon is unavailable'
            );
        }

        try {
            stream_set_timeout(
                $stream,
                $action
                    ? self::ACTION_TIMEOUT
                    : self::READ_TIMEOUT
            );

            $length = strlen($payload);
            $offset = 0;

            while ($offset < $length) {
                $written = fwrite(
                    $stream,
                    substr($payload, $offset)
                );

                if ($written === false || $written === 0) {
                    throw new RuntimeException(
                        'Incomplete daemon request'
                    );
                }

                $offset += $written;
            }

            $response = '';
            $terminated = false;

            while (!feof($stream)) {
                $chunk = fgets($stream, 65536);

                if ($chunk === false) {
                    $meta = stream_get_meta_data($stream);

                    if (!empty($meta['timed_out'])) {
                        throw new RuntimeException(
                            'Dashboard daemon timeout'
                        );
                    }

                    break;
                }

                $response .= $chunk;

                if (strlen($response) > self::MAX_RESPONSE_BYTES) {
                    throw new RuntimeException(
                        'Dashboard daemon response too large'
                    );
                }

                if (str_ends_with($response, "\n")) {
                    $terminated = true;
                    break;
                }
            }

            if (!$terminated) {
                throw new RuntimeException(
                    'Incomplete daemon response'
                );
            }

            $decoded = json_decode(
                trim($response),
                true,
                64,
                JSON_THROW_ON_ERROR
            );

            if (!is_array($decoded)) {
                throw new RuntimeException(
                    'Invalid daemon response'
                );
            }

            if (($decoded['version'] ?? null) !== self::PROTOCOL_VERSION) {
                throw new RuntimeException(
                    'Daemon protocol version mismatch'
                );
            }

            if (($decoded['id'] ?? null) !== $requestId) {
                throw new RuntimeException(
                    'Daemon response id mismatch'
                );
            }

            if (($decoded['ok'] ?? null) !== true) {
                $error = $decoded['error'] ?? [];

                $code = (
                    is_array($error)
                    && is_string($error['code'] ?? null)
                )
                    ? $error['code']
                    : 'daemon_error';

                $message = (
                    is_array($error)
                    && is_string($error['message'] ?? null)
                )
                    ? $error['message']
                    : 'Daemon operation failed';

                throw new DaemonClientException(
                    $code,
                    $message
                );
            }

            $data = $decoded['data'] ?? null;

            return is_array($data)
                ? $data
                : ['value' => $data];

        } finally {
            fclose($stream);
        }
    }
}

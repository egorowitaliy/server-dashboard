<?php

declare(strict_types=1);

final class RateLimiter
{
    private const DIRECTORY =
        '/run/server-dashboard/auth';

    private int $maxFailures;
    private int $windowSeconds;
    private int $lockSeconds;

    public function __construct(
        array $authConfig
    ) {
        $this->maxFailures =
            (int) $authConfig['max_failures'];

        $this->windowSeconds =
            (int) $authConfig[
                'failure_window_seconds'
            ];

        $this->lockSeconds =
            (int) $authConfig['lock_seconds'];
    }

    public function status(
        string $ip
    ): array {
        $filename = $this->filename($ip);

        if (!is_file($filename)) {
            return [
                'locked' => false,
                'remaining_seconds' => 0,
                'failures' => 0,
            ];
        }

        return $this->readStatus(
            $filename
        );
    }

    public function recordFailure(
        string $ip
    ): array {
        return $this->update(
            $ip,
            function (
                array $state,
                int $now
            ): array {
                $state = $this->normalize(
                    $state,
                    $now
                );

                if ($state['locked_until'] > $now) {
                    return [
                        $state,
                        [
                            'locked' => true,
                            'remaining_seconds' =>
                                $state['locked_until'] - $now,
                        ],
                    ];
                }

                $state['failures'][] = $now;

                if (
                    count($state['failures'])
                    >= $this->maxFailures
                ) {
                    $state['locked_until'] =
                        $now + $this->lockSeconds;

                    $state['failures'] = [];
                }

                return [
                    $state,
                    [
                        'locked' =>
                            $state['locked_until'] > $now,

                        'remaining_seconds' =>
                            max(
                                0,
                                $state['locked_until'] - $now
                            ),
                    ],
                ];
            }
        );
    }

    public function clear(
        string $ip
    ): void {
        $filename = $this->filename($ip);

        if (!is_file($filename)) {
            return;
        }

        $handle = @fopen(
            $filename,
            'r+'
        );

        if (!is_resource($handle)) {
            return;
        }

        try {
            if (flock($handle, LOCK_EX)) {
                @unlink($filename);
                flock($handle, LOCK_UN);
            }
        } finally {
            fclose($handle);
        }
    }

    private function filename(
        string $ip
    ): string {
        return self::DIRECTORY
            . '/'
            . hash('sha256', $ip)
            . '.json';
    }

    private function readStatus(
        string $filename
    ): array {
        $handle = @fopen(
            $filename,
            'r+'
        );

        if (!is_resource($handle)) {
            return [
                'locked' => false,
                'remaining_seconds' => 0,
                'failures' => 0,
            ];
        }

        try {
            if (!flock($handle, LOCK_EX)) {
                throw new RuntimeException(
                    'Unable to lock auth state'
                );
            }

            $raw = stream_get_contents($handle);
            $state = [];

            if (
                is_string($raw)
                && trim($raw) !== ''
            ) {
                try {
                    $decoded = json_decode(
                        $raw,
                        true,
                        32,
                        JSON_THROW_ON_ERROR
                    );

                    if (is_array($decoded)) {
                        $state = $decoded;
                    }
                } catch (JsonException) {
                    $state = [];
                }
            }

            $now = time();

            $state = $this->normalize(
                $state,
                $now
            );

            $empty = (
                $state['locked_until'] === 0
                && $state['failures'] === []
            );

            if ($empty) {
                @unlink($filename);
            } else {
                rewind($handle);
                ftruncate($handle, 0);

                fwrite(
                    $handle,
                    json_encode(
                        $state,
                        JSON_THROW_ON_ERROR
                        | JSON_UNESCAPED_SLASHES
                    )
                );

                fflush($handle);
            }

            flock($handle, LOCK_UN);

            return [
                'locked' =>
                    $state['locked_until'] > $now,

                'remaining_seconds' =>
                    max(
                        0,
                        $state['locked_until'] - $now
                    ),

                'failures' =>
                    count($state['failures']),
            ];

        } finally {
            fclose($handle);
        }
    }

    private function normalize(
        array $state,
        int $now
    ): array {
        $failures =
            $state['failures'] ?? [];

        if (!is_array($failures)) {
            $failures = [];
        }

        $minimum =
            $now - $this->windowSeconds;

        $failures = array_values(
            array_filter(
                $failures,
                static fn (mixed $value): bool =>
                    is_int($value)
                    && $value >= $minimum
                    && $value <= $now
            )
        );

        $lockedUntil =
            $state['locked_until'] ?? 0;

        if (!is_int($lockedUntil)) {
            $lockedUntil = 0;
        }

        if ($lockedUntil <= $now) {
            $lockedUntil = 0;
        }

        return [
            'failures' => $failures,
            'locked_until' => $lockedUntil,
        ];
    }

    private function update(
        string $ip,
        callable $callback
    ): mixed {
        $filename =
            $this->filename($ip);

        $handle = @fopen(
            $filename,
            'c+'
        );

        if (!is_resource($handle)) {
            throw new RuntimeException(
                'Auth rate-limit state is unavailable'
            );
        }

        try {
            if (!flock($handle, LOCK_EX)) {
                throw new RuntimeException(
                    'Unable to lock auth state'
                );
            }

            rewind($handle);
            $raw = stream_get_contents($handle);

            $state = [];

            if (
                is_string($raw)
                && trim($raw) !== ''
            ) {
                try {
                    $decoded = json_decode(
                        $raw,
                        true,
                        32,
                        JSON_THROW_ON_ERROR
                    );

                    if (is_array($decoded)) {
                        $state = $decoded;
                    }
                } catch (JsonException) {
                    $state = [];
                }
            }

            [$newState, $result] =
                $callback(
                    $state,
                    time()
                );

            $encoded = json_encode(
                $newState,
                JSON_THROW_ON_ERROR
                | JSON_UNESCAPED_SLASHES
            );

            rewind($handle);
            ftruncate($handle, 0);
            fwrite($handle, $encoded);
            fflush($handle);

            flock($handle, LOCK_UN);

            return $result;

        } finally {
            fclose($handle);
        }
    }
}

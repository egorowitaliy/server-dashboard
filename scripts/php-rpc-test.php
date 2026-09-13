<?php

declare(strict_types=1);

require '/opt/server-dashboard/web/app/DaemonClient.php';

$client = new DaemonClient();

try {
    $data = $client->request('health');

    echo json_encode(
        $data,
        JSON_PRETTY_PRINT
        | JSON_UNESCAPED_UNICODE
        | JSON_UNESCAPED_SLASHES
    ), PHP_EOL;

    exit(0);

} catch (Throwable $e) {
    fwrite(
        STDERR,
        '[ERROR] ' . $e->getMessage() . PHP_EOL
    );

    exit(1);
}

<?php

declare(strict_types=1);

require '/opt/server-dashboard/web/app/bootstrap.php';

if (
    ($_SERVER['REQUEST_METHOD'] ?? '')
    !== 'POST'
) {
    http_response_code(405);
    header('Allow: POST');
    exit;
}

if (!Auth::isAuthenticated()) {
    header('Location: /login', true, 303);
    exit;
}

if (!Csrf::verify(
    $_POST['csrf'] ?? null
)) {
    http_response_code(400);
    echo 'Некорректный CSRF token';
    exit;
}

$user = Auth::user() ?? '-';

$ip = (string) (
    $_SERVER['REMOTE_ADDR']
    ?? 'unknown'
);

AuditLogger::write(
    'auth.logout',
    'ok',
    $user,
    $ip
);

Auth::logout();

header(
    'Location: /login',
    true,
    303
);

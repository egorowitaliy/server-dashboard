<?php

declare(strict_types=1);

require_once __DIR__ . '/Secrets.php';
require_once __DIR__ . '/AuditLogger.php';
require_once __DIR__ . '/Csrf.php';
require_once __DIR__ . '/RateLimiter.php';
require_once __DIR__ . '/Auth.php';
require_once __DIR__ . '/DaemonClient.php';
require_once __DIR__ . '/DashboardIdentity.php';

$authConfig = Secrets::auth();

Auth::bootstrap(
    $authConfig
);

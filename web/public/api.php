<?php

declare(strict_types=1);

require '/opt/server-dashboard/web/app/bootstrap.php';


function respond(
    array $payload,
    int $status
): never {
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store, max-age=0');

    echo json_encode(
        $payload,
        JSON_THROW_ON_ERROR
        | JSON_UNESCAPED_UNICODE
        | JSON_UNESCAPED_SLASHES
    );

    exit;
}


function errorResponse(
    string $code,
    string $message,
    int $status
): never {
    respond(
        [
            'ok' => false,
            'error' => [
                'code' => $code,
                'message' => $message,
            ],
        ],
        $status
    );
}


function requireAuth(): void
{
    if (!Auth::isAuthenticated()) {
        errorResponse(
            'unauthorized',
            'Требуется авторизация',
            401
        );
    }
}


function daemonStatus(string $code): int
{
    return match ($code) {
        'module_disabled',
        'component_disabled',
        'unknown_operation',
        'asset_not_found',
        'document_not_found' => 404,

        'target_not_allowed' => 403,

        'invalid_target',
        'invalid_params',
        'invalid_ip',
        'invalid_document',
        'invalid_operation' => 400,

        'document_too_large' => 413,
        'action_timeout' => 504,

        default => 502,
    };
}


function daemonError(DaemonClientException $e): never
{
    errorResponse(
        $e->daemonCode(),
        $e->getMessage(),
        daemonStatus($e->daemonCode())
    );
}


function requestBody(): array
{
    $contentType = strtolower(
        trim((string) ($_SERVER['CONTENT_TYPE'] ?? ''))
    );

    if (!str_starts_with($contentType, 'application/json')) {
        errorResponse(
            'unsupported_media_type',
            'Ожидается application/json',
            415
        );
    }

    $raw = file_get_contents(
        'php://input',
        false,
        null,
        0,
        8193
    );

    if (!is_string($raw) || strlen($raw) > 8192) {
        errorResponse(
            'invalid_request',
            'Некорректный запрос',
            400
        );
    }

    try {
        $body = json_decode(
            $raw,
            true,
            16,
            JSON_THROW_ON_ERROR
        );
    } catch (JsonException) {
        errorResponse(
            'invalid_json',
            'Некорректный JSON',
            400
        );
    }

    if (!is_array($body) || array_is_list($body)) {
        errorResponse(
            'invalid_request',
            'Ожидается JSON-объект',
            400
        );
    }

    return $body;
}


function operationFromBody(array $body): array
{
    $operation = $body['operation'] ?? null;
    $params = $body['params'] ?? [];

    if (
        !is_string($operation)
        || preg_match(
            '/\A[a-z][a-z0-9_.-]{0,127}\z/D',
            $operation
        ) !== 1
    ) {
        errorResponse(
            'invalid_operation',
            'Некорректная операция',
            400
        );
    }

    if (
        !is_array($params)
        || ($params !== [] && array_is_list($params))
    ) {
        errorResponse(
            'invalid_params',
            'params должен быть JSON-объектом',
            400
        );
    }

    if (count($params) > 32) {
        errorResponse(
            'invalid_params',
            'Слишком много параметров',
            400
        );
    }

    return [$operation, $params];
}


function auditMeta(array $params): array
{
    $result = [];

    foreach ($params as $key => $value) {
        if (
            is_string($key)
            && preg_match('/\A[A-Za-z0-9_.-]{1,64}\z/D', $key) === 1
            && is_scalar($value)
        ) {
            $result[$key] = (string) $value;
        }
    }

    return $result;
}


function requireCsrf(): void
{
    $csrf = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? null;

    if (!Csrf::verify($csrf)) {
        AuditLogger::write(
            'api.action',
            'csrf_failed',
            Auth::user() ?? '-',
            (string) ($_SERVER['REMOTE_ADDR'] ?? 'unknown')
        );

        errorResponse(
            'csrf_failed',
            'Некорректный CSRF token',
            403
        );
    }
}


$method = $_SERVER['REQUEST_METHOD'] ?? '';
$path = parse_url(
    (string) ($_SERVER['REQUEST_URI'] ?? ''),
    PHP_URL_PATH
);

if (!is_string($path)) {
    errorResponse('not_found', 'Ресурс не найден', 404);
}


/* Extension assets are served only for enabled, registered extensions. */
if (
    preg_match(
        '#\A/api/extensions/([a-z0-9][a-z0-9_-]{0,63})/asset/([A-Za-z0-9_.-]{1,128}\.(?:js|css|svg))\z#D',
        $path,
        $assetMatch
    ) === 1
) {
    if ($method !== 'GET') {
        header('Allow: GET');
        errorResponse('method_not_allowed', 'Метод не поддерживается', 405);
    }

    requireAuth();
    Auth::touch();
    session_write_close();

    try {
        $client = new DaemonClient();
        $asset = $client->request(
            'extension.asset.describe',
            [
                'module' => $assetMatch[1],
                'asset' => $assetMatch[2],
            ]
        );
    } catch (DaemonClientException $e) {
        daemonError($e);
    } catch (Throwable $e) {
        error_log('dashboard_extension_asset_error ' . $e->getMessage());
        errorResponse('backend_unavailable', 'Asset временно недоступен', 503);
    }

    $file = $asset['path'] ?? null;
    $mime = $asset['mime'] ?? 'application/octet-stream';

    if (!is_string($file) || !is_file($file) || !is_readable($file)) {
        errorResponse('asset_not_found', 'Asset не найден', 404);
    }

    header('Content-Type: ' . (is_string($mime) ? $mime : 'application/octet-stream'));
    header('Cache-Control: private, max-age=300');
    header('X-Content-Type-Options: nosniff');
    readfile($file);
    exit;
}


/* Generic read-only RPC for extension frontends. */
if ($path === '/api/rpc') {
    if ($method !== 'POST') {
        header('Allow: POST');
        errorResponse('method_not_allowed', 'Метод не поддерживается', 405);
    }

    requireAuth();
    [$operation, $params] = operationFromBody(requestBody());

    $user = Auth::user() ?? '-';
    Auth::touch();
    session_write_close();

    try {
        $client = new DaemonClient();
        $description = $client->request(
            'operation.describe',
            ['operation' => $operation]
        );

        if (($description['kind'] ?? null) !== 'read') {
            errorResponse(
                'operation_not_read_only',
                'Из этого endpoint разрешены только операции чтения',
                403
            );
        }

        $data = $client->request($operation, $params);
        respond(['ok' => true, 'data' => $data], 200);

    } catch (DaemonClientException $e) {
        daemonError($e);
    } catch (Throwable $e) {
        error_log(sprintf(
            'dashboard_rpc_error operation=%s message=%s',
            $operation,
            $e->getMessage()
        ));
        errorResponse('backend_unavailable', 'Backend временно недоступен', 503);
    }
}


/* Generic mutating endpoint. Every action is described by the daemon first. */
if ($path === '/api/action') {
    if ($method !== 'POST') {
        header('Allow: POST');
        errorResponse('method_not_allowed', 'Метод не поддерживается', 405);
    }

    requireAuth();
    requireCsrf();
    [$operation, $params] = operationFromBody(requestBody());

    $user = Auth::user() ?? '-';
    $clientIp = (string) ($_SERVER['REMOTE_ADDR'] ?? 'unknown');
    $meta = auditMeta($params);

    Auth::touch();
    session_write_close();

    try {
        $client = new DaemonClient();
        $description = $client->request(
            'operation.describe',
            ['operation' => $operation]
        );

        if (($description['kind'] ?? null) !== 'action') {
            errorResponse(
                'operation_not_action',
                'Из этого endpoint разрешены только изменяющие операции',
                403
            );
        }

        if (
            $operation === 'system.reboot'
            || $operation === 'system.poweroff'
        ) {
            AuditLogger::write(
                $operation,
                'requested',
                $user,
                $clientIp,
                $meta
            );
        }

        $data = $client->request(
            $operation,
            $params,
            true
        );

        AuditLogger::write(
            $operation,
            'ok',
            $user,
            $clientIp,
            $meta
        );

        respond(['ok' => true, 'data' => $data], 200);

    } catch (DaemonClientException $e) {
        AuditLogger::write(
            $operation,
            'failed',
            $user,
            $clientIp,
            [
                ...$meta,
                'code' => $e->daemonCode(),
            ]
        );
        daemonError($e);
    } catch (Throwable $e) {
        AuditLogger::write(
            $operation,
            'failed',
            $user,
            $clientIp,
            $meta
        );
        error_log(sprintf(
            'dashboard_action_error operation=%s message=%s',
            $operation,
            $e->getMessage()
        ));
        errorResponse('backend_unavailable', 'Backend временно недоступен', 503);
    }
}


/* Parameterized built-in reads kept as stable convenience routes. */
$parameterized = [
    '/api/fail2ban/banned' => [
        'operation' => 'fail2ban.banned',
        'query' => 'jail',
        'param' => 'jail',
    ],
    '/api/docs/read' => [
        'operation' => 'docs.read',
        'query' => 'document',
        'param' => 'document',
    ],
];

if (isset($parameterized[$path])) {
    if ($method !== 'GET') {
        header('Allow: GET');
        errorResponse('method_not_allowed', 'Метод не поддерживается', 405);
    }

    requireAuth();
    $spec = $parameterized[$path];
    $value = $_GET[$spec['query']] ?? null;

    if (!is_string($value) || $value === '' || strlen($value) > 512) {
        errorResponse('invalid_params', 'Некорректный параметр', 400);
    }

    Auth::touch();
    session_write_close();

    try {
        $client = new DaemonClient();
        $data = $client->request(
            $spec['operation'],
            [$spec['param'] => $value]
        );
        respond(['ok' => true, 'data' => $data], 200);
    } catch (DaemonClientException $e) {
        daemonError($e);
    } catch (Throwable $e) {
        error_log('dashboard_parameterized_read_error ' . $e->getMessage());
        errorResponse('backend_unavailable', 'Backend временно недоступен', 503);
    }
}


$routes = [
    '/api/health' => 'health',
    '/api/modules' => 'modules.list',
    '/api/overview' => 'overview',
    '/api/host' => 'host.snapshot',
    '/api/system' => 'system.snapshot',
    '/api/services' => 'services.list',
    '/api/docker' => 'docker.list',
    '/api/fail2ban' => 'fail2ban.list',
    '/api/schedule' => 'schedule.list',
    '/api/smart' => 'smart.list',
    '/api/docs' => 'docs.list',
    '/api/audit' => 'audit.list',
];

$operation = $routes[$path] ?? null;

if (!is_string($operation)) {
    errorResponse('not_found', 'Ресурс не найден', 404);
}

if ($method !== 'GET') {
    header('Allow: GET');
    errorResponse('method_not_allowed', 'Метод не поддерживается', 405);
}

if ($operation !== 'health') {
    requireAuth();
}

if (Auth::isAuthenticated()) {
    Auth::touch();
    session_write_close();
}

try {
    $client = new DaemonClient();
    $data = $client->request($operation);
    respond(['ok' => true, 'data' => $data], 200);
} catch (DaemonClientException $e) {
    daemonError($e);
} catch (Throwable $e) {
    error_log(sprintf(
        'dashboard_api_error operation=%s message=%s',
        $operation,
        $e->getMessage()
    ));
    errorResponse('backend_unavailable', 'Backend временно недоступен', 503);
}

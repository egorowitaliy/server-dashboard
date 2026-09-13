<?php

declare(strict_types=1);

require '/opt/server-dashboard/web/app/bootstrap.php';

$dashboardIdentity =
    DashboardIdentity::load();

$ip = (string) (
    $_SERVER['REMOTE_ADDR']
    ?? 'unknown'
);

$limiter = new RateLimiter(
    $authConfig
);

$status = $limiter->status($ip);

$error = null;
$locked = (bool) $status['locked'];
$remaining = (int) $status['remaining_seconds'];

if (Auth::isAuthenticated()) {
    header('Location: /', true, 303);
    exit;
}

$configured =
    $authConfig['password_hash'] !== '!';

if (
    ($_SERVER['REQUEST_METHOD'] ?? '')
    === 'POST'
) {
    $status = $limiter->status($ip);

    if ($status['locked']) {
        $locked = true;
        $remaining =
            (int) $status['remaining_seconds'];

        AuditLogger::write(
            'auth.login',
            'blocked',
            '-',
            $ip
        );

    } elseif (!Csrf::verify(
        $_POST['csrf'] ?? null
    )) {
        http_response_code(400);

        AuditLogger::write(
            'auth.login',
            'csrf_failed',
            '-',
            $ip
        );

        $error =
            'Сеанс формы устарел. Обновите страницу.';

    } elseif (!$configured) {
        http_response_code(503);

        $error =
            'Пароль администратора ещё не настроен.';

    } else {
        $username =
            trim(
                (string) (
                    $_POST['username']
                    ?? ''
                )
            );

        $password =
            (string) (
                $_POST['password']
                ?? ''
            );

        $userValid = hash_equals(
            $authConfig['username'],
            $username
        );

        $passwordValid =
            password_verify(
                $password,
                $authConfig['password_hash']
            );

        if ($userValid && $passwordValid) {
            $limiter->clear($ip);

            Auth::login(
                $authConfig['username']
            );

            AuditLogger::write(
                'auth.login',
                'ok',
                $authConfig['username'],
                $ip
            );

            header(
                'Location: /',
                true,
                303
            );

            exit;
        }

        $after =
            $limiter->recordFailure($ip);

        AuditLogger::write(
            'auth.login',
            'failed',
            $username !== ''
                ? $username
                : '-',
            $ip
        );

        if ($after['locked']) {
            $locked = true;
            $remaining =
                (int) $after[
                    'remaining_seconds'
                ];

            $error = null;
        } else {
            $error =
                'Неверное имя пользователя или пароль.';
        }
    }
}

function h(string $value): string
{
    return htmlspecialchars(
        $value,
        ENT_QUOTES | ENT_SUBSTITUTE,
        'UTF-8'
    );
}

?><!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title><?= h($dashboardIdentity['title']) ?> — вход</title>
<style>
*{box-sizing:border-box}

:root{
    --page:#f3f4f5;
    --panel:#fff;
    --line:#cfd5d9;
    --text:#27333b;
    --muted:#77828a;
    --accent:#168ec1;
}

body,
button,
input{
    font-family:"Roboto","Segoe UI",Arial,sans-serif;
}

body{
    margin:0;
    min-height:100vh;
    display:grid;
    place-items:center;
    background:var(--page);
    color:var(--text);
    font-size:14px;
}

.card{
    width:min(380px,calc(100vw - 32px));
    background:var(--panel);
    border:1px solid #dce0e3;
    border-radius:4px;
    padding:28px 30px 30px;
}

h1{
    margin:0 0 5px;
    font-size:23px;
    line-height:1.2;
    font-weight:700;
    letter-spacing:-.2px;
}

.login-brand .brand-part{
    font:inherit;
}

.login-brand .brand-server{
    color:var(--accent);
}

.login-brand .brand-product{
    color:#111820;
}

.sub{
    color:var(--muted);
    margin-bottom:25px;
}

label{
    display:block;
    margin:15px 0 6px;
    font-size:13px;
    font-weight:500;
}

input{
    width:100%;
    height:39px;
    padding:0 10px;
    border:1px solid var(--line);
    border-radius:3px;
    background:#fff;
    color:var(--text);
    font-size:14px;
}

input:focus{
    outline:none;
    border-color:var(--accent);
}

button{
    width:100%;
    min-height:39px;
    margin-top:21px;
    border:1px solid #117da9;
    border-radius:3px;
    background:var(--accent);
    color:#fff;
    font-weight:500;
    cursor:pointer;
}

button:hover{
    background:#117eaa;
}

.message,
.locked{
    padding:11px 12px;
    border-radius:3px;
    line-height:1.45;
}

.message{
    border:1px solid #e6c2bf;
    background:#fffafa;
    color:#9c3d37;
}

.locked{
    border:1px solid #e4d1ac;
    background:#fffdf8;
    color:#80601d;
}
</style>
</head>
<body>
<div class="card">
    <h1 class="login-brand"><span class="brand-part brand-server"><?= h($dashboardIdentity['server_name']) ?></span> <span class="brand-part brand-product"><?= h($dashboardIdentity['product_name']) ?></span></h1>
    <div class="sub">Операционный дашборд</div>

<?php if (!$configured): ?>

    <div class="message">
        Пароль администратора ещё не настроен.
    </div>

<?php elseif ($locked): ?>

    <div class="locked">
        Вход временно заблокирован после нескольких
        неудачных попыток.<br><br>
        Осталось примерно:
        <?= (int) ceil($remaining / 60) ?> мин.
    </div>

<?php else: ?>

    <?php if ($error !== null): ?>
        <div class="message">
            <?= h($error) ?>
        </div>
    <?php endif; ?>

    <form method="post" action="/login" autocomplete="on">
        <input
            type="hidden"
            name="csrf"
            value="<?= h(Csrf::token()) ?>"
        >

        <label for="username">
            Пользователь
        </label>

        <input
            id="username"
            name="username"
            type="text"
            autocomplete="username"
            required
        >

        <label for="password">
            Пароль
        </label>

        <input
            id="password"
            name="password"
            type="password"
            autocomplete="current-password"
            required
        >

        <button type="submit">
            Войти
        </button>
    </form>

<?php endif; ?>

</div>
</body>
</html>

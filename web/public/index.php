<?php

declare(strict_types=1);

require '/opt/server-dashboard/web/app/bootstrap.php';

if (!Auth::isAuthenticated()) {
    header('Location: /login', true, 303);
    exit;
}

Auth::touch();
$user = Auth::user() ?? '-';

$dashboardIdentity =
    DashboardIdentity::load();

function h(string $value): string
{
    return htmlspecialchars(
        $value,
        ENT_QUOTES | ENT_SUBSTITUTE,
        'UTF-8'
    );
}

$cssPath = __DIR__ . '/assets/css/app.css';
$jsPath = __DIR__ . '/assets/js/app.js';
$cssVersion = is_file($cssPath) ? (string) filemtime($cssPath) : '1';
$jsVersion = is_file($jsPath) ? (string) filemtime($jsPath) : '1';
?><!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title><?= h($dashboardIdentity['title']) ?></title>
<meta name="csrf-token" content="<?= h(Csrf::token()) ?>">
<link rel="stylesheet" href="/assets/css/app.css?v=<?= h($cssVersion) ?>">
</head>
<body>
<div class="app">
<header class="topbar">
    <div class="brand-wrap">
        <button id="mobile-menu" type="button" class="top-action mobile-menu" aria-label="Меню">
            <span class="icon i-chart"></span>
        </button>
        <div id="dashboard-brand" class="brand">
            <span id="dashboard-server-name" class="brand-part brand-server"><?= h($dashboardIdentity['server_name']) ?></span>
            <span id="dashboard-product-name" class="brand-part brand-product"><?= h($dashboardIdentity['product_name']) ?></span>
        </div>
    </div>

    <div class="top-actions">
        <button id="refresh" type="button" class="top-action">
            <span class="icon i-refresh"></span>
            <span>Обновить</span>
        </button>

        <button id="reboot" type="button" class="top-action" hidden>
            <span class="icon i-power"></span>
            <span>Перезагрузка</span>
        </button>

        <button id="shutdown" type="button" class="top-action shutdown" hidden>
            <span class="icon i-power"></span>
            <span>Выключить</span>
        </button>

        <div class="top-divider"></div>
        <div class="user">
            <span class="icon i-person"></span>
            <span><?= h($user) ?></span>
        </div>

        <form method="post" action="/logout">
            <input type="hidden" name="csrf" value="<?= h(Csrf::token()) ?>">
            <button type="submit" class="logout">Выйти</button>
        </form>
    </div>
</header>

<aside class="sidebar">
    <nav id="module-nav"></nav>
</aside>

<main id="main-content" class="main">
    <div class="loading">Получение данных…</div>
</main>

<footer class="app-footer">
    <span>Разработка: <a href="https://e-v-s.ru" target="_blank" rel="noopener noreferrer">Виталий Егоров</a></span>
    <span class="app-footer-separator" aria-hidden="true">·</span>
    <span>Telegram: <a href="https://t.me/egorowitaliy" target="_blank" rel="noopener noreferrer">@egorowitaliy</a></span>
</footer>
</div>

<script src="/assets/js/app.js?v=<?= h($jsVersion) ?>"></script>
</body>
</html>

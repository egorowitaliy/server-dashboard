(() => {
  "use strict";

  const main =
    document.getElementById("main-content");

  const moduleNav =
    document.getElementById("module-nav");

  let navButtons = [];

  const refreshButton =
    document.getElementById("refresh");

  const mobileMenu =
    document.getElementById("mobile-menu");


  const rebootButton =
    document.getElementById("reboot");

  const shutdownButton =
    document.getElementById("shutdown");

  let currentPage = null;

  const renderers = {};
  const liveTablePages = new Set();
  const placementHooks = {
    overview: [],
    system: []
  };
  const moduleMetadata = new Map();
  let extensionErrors = [];

  let systemScheduleEnabled = false;
  let hostPollTimer = null;
  let uptimeTimer = null;
  let pagePollTimer = null;
  let schedulePollTimer = null;

  let uptimeBaseSeconds = 0;
  let uptimeBaseTime = 0;

  let hostRefreshSeconds = 5;

  let openFail2BanJail = null;

  let openDocumentId = null;


  const csrfToken =
    document.querySelector(
      'meta[name="csrf-token"]'
    )?.content || "";


  const actionApi = async (
    operation,
    params
  ) => {
    const response = await fetch(
      "/api/action",
      {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Accept":
            "application/json",

          "Content-Type":
            "application/json",

          "X-CSRF-Token":
            csrfToken
        },

        body: JSON.stringify({
          operation,
          params
        })
      }
    );

    if (response.status === 401) {
      window.location.href =
        "/login";

      throw new Error(
        "unauthorized"
      );
    }

    const payload =
      await response.json();

    if (
      !response.ok
      || payload.ok !== true
    ) {
      throw new Error(
        payload?.error?.message
        || "Операция не выполнена"
      );
    }

    return payload.data;
  };


  const restartObject = async (
    operation,
    row,
    button
  ) => {
    const target =
      row.id;

    if (
      typeof target !== "string"
      || !target
    ) {
      window.alert(
        "Не удалось определить объект."
      );

      return;
    }

    const confirmed =
      window.confirm(
        `Перезапустить «${row.name}»?`
      );

    if (!confirmed) {
      return;
    }

    const oldText =
      button.textContent;

    button.disabled = true;

    button.classList.add(
      "action-running"
    );

    button.textContent =
      "Перезапуск…";

    try {
      await actionApi(
        operation,
        {
          target
        }
      );

      button.textContent =
        "Готово";

      const actionPage =
        currentPage;

      stopPagePolling();

      window.setTimeout(
        async () => {
          if (
            currentPage
            !== actionPage
          ) {
            return;
          }

          try {
            await renderers[
              actionPage
            ](true);

          } catch (error) {
            if (
              error?.message
              !== "unauthorized"
            ) {
              console.warn(
                "Post-action refresh failed",
                error
              );
            }
          }

          if (
            currentPage
            === actionPage
          ) {
            schedulePagePoll();
          }
        },
        700
      );

    } catch (error) {
      if (
        error?.message
        !== "unauthorized"
      ) {
        window.alert(
          error?.message
          || "Операция не выполнена"
        );

        button.disabled =
          false;

        button.textContent =
          oldText;

        button.classList.remove(
          "action-running"
        );
      }
    }
  };


  const api = async (path) => {
    const response = await fetch(
      path,
      {
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "application/json"
        }
      }
    );

    if (response.status === 401) {
      window.location.href = "/login";
      throw new Error("unauthorized");
    }

    const payload =
      await response.json();

    if (
      !response.ok
      || payload.ok !== true
    ) {
      throw new Error(
        payload?.error?.message
        || "Не удалось получить данные"
      );
    }

    return payload.data;
  };


  const rpcRead = async (
    operation,
    params = {}
  ) => {
    const response = await fetch(
      "/api/rpc",
      {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          "Accept": "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify({
          operation,
          params
        })
      }
    );

    if (response.status === 401) {
      window.location.href = "/login";
      throw new Error("unauthorized");
    }

    const payload = await response.json();

    if (
      !response.ok
      || payload.ok !== true
    ) {
      throw new Error(
        payload?.error?.message
        || "Не удалось получить данные"
      );
    }

    return payload.data;
  };


  const el = (
    tag,
    className,
    text
  ) => {
    const node =
      document.createElement(tag);

    if (className) {
      node.className = className;
    }

    if (text !== undefined) {
      node.textContent = text;
    }

    return node;
  };


  const closeSystemModal = () => {
    document.querySelector(
      ".system-modal-overlay"
    )?.remove();
  };


  const showSystemAccepted = (
    overlay,
    card,
    title,
    text
  ) => {
    card.replaceChildren();

    const header =
      el(
        "div",
        "system-modal-title",
        title
      );

    const message =
      el(
        "div",
        "system-modal-result",
        text
      );

    card.append(
      header,
      message
    );

    overlay.classList.add(
      "accepted"
    );
  };


  const openSystemModal = ({
    operation,
    title,
    description,
    confirmText,
    buttonText,
    danger = false
  }) => {
    closeSystemModal();

    const overlay =
      el(
        "div",
        "system-modal-overlay"
      );

    const card =
      el(
        "div",
        "system-modal"
      );

    card.setAttribute(
      "role",
      "dialog"
    );

    card.setAttribute(
      "aria-modal",
      "true"
    );

    card.setAttribute(
      "aria-label",
      title
    );

    const header =
      el(
        "div",
        "system-modal-title",
        title
      );

    const body =
      el(
        "div",
        "system-modal-description",
        description
      );

    const confirmRow =
      el(
        "label",
        "system-confirm"
      );

    const checkbox =
      document.createElement(
        "input"
      );

    checkbox.type =
      "checkbox";

    const confirmLabel =
      el(
        "span",
        "",
        confirmText
      );

    confirmRow.append(
      checkbox,
      confirmLabel
    );

    const actions =
      el(
        "div",
        "system-modal-actions"
      );

    const cancel =
      el(
        "button",
        "btn",
        "Отмена"
      );

    cancel.type =
      "button";

    const submit =
      el(
        "button",
        danger
          ? "btn btn-danger"
          : "btn btn-primary",
        buttonText
      );

    submit.type =
      "button";

    submit.disabled =
      true;

    checkbox.addEventListener(
      "change",
      () => {
        submit.disabled =
          !checkbox.checked;
      }
    );

    cancel.addEventListener(
      "click",
      closeSystemModal
    );

    overlay.addEventListener(
      "click",
      (event) => {
        if (
          event.target === overlay
        ) {
          closeSystemModal();
        }
      }
    );

    submit.addEventListener(
      "click",
      async () => {
        if (!checkbox.checked) {
          return;
        }

        checkbox.disabled =
          true;

        cancel.disabled =
          true;

        submit.disabled =
          true;

        submit.textContent =
          "Отправка…";

        try {
          await actionApi(
            operation,
            {}
          );

          showSystemAccepted(
            overlay,
            card,
            title,
            operation === "system.reboot"
              ? "Команда перезагрузки отправлена серверу."
              : "Команда выключения отправлена серверу."
          );

        } catch (error) {
          if (
            error?.message
            === "unauthorized"
          ) {
            return;
          }

          /*
           * После reboot/poweroff соединение может оборваться
           * раньше HTTP-ответа. Fetch в таком случае обычно
           * возвращает TypeError.
           */
          if (
            error instanceof TypeError
          ) {
            showSystemAccepted(
              overlay,
              card,
              title,
              "Соединение с сервером прервано. Команда могла быть принята."
            );

            return;
          }

          checkbox.disabled =
            false;

          cancel.disabled =
            false;

          submit.disabled =
            !checkbox.checked;

          submit.textContent =
            buttonText;

          window.alert(
            error?.message
            || "Команда не выполнена"
          );
        }
      }
    );

    actions.append(
      cancel,
      submit
    );

    card.append(
      header,
      body,
      confirmRow,
      actions
    );

    overlay.append(
      card
    );

    document.body.append(
      overlay
    );

    checkbox.focus();
  };


  rebootButton?.addEventListener(
    "click",
    () => openSystemModal({
      operation:
        "system.reboot",

      title:
        "Перезагрузка сервера",

      description:
        "Сервер будет перезагружен. Текущие соединения и работающие сеансы будут прерваны.",

      confirmText:
        "Я подтверждаю перезагрузку сервера",

      buttonText:
        "Перезагрузить"
    })
  );


  shutdownButton?.addEventListener(
    "click",
    () => openSystemModal({
      operation:
        "system.poweroff",

      title:
        "Выключение сервера",

      description:
        "После выключения сервер перестанет быть доступен до следующего включения.",

      confirmText:
        "Я подтверждаю выключение сервера",

      buttonText:
        "Выключить",

      danger:
        true
    })
  );


  const icon = (
    name,
    extra = ""
  ) => {
    return el(
      "span",
      `icon i-${name}${extra ? ` ${extra}` : ""}`
    );
  };


  const bytes = (value) => {
    if (typeof value !== "number") {
      return "—";
    }

    const units = [
      "Б",
      "КиБ",
      "МиБ",
      "ГиБ",
      "ТиБ"
    ];

    let current = value;
    let unit = 0;

    while (
      current >= 1024
      && unit < units.length - 1
    ) {
      current /= 1024;
      unit++;
    }

    return (
      current.toFixed(
        unit >= 3 ? 1 : 0
      )
      + " "
      + units[unit]
    );
  };


  const duration = (seconds) => {
    if (typeof seconds !== "number") {
      return "—";
    }

    const days =
      Math.floor(seconds / 86400);

    const hours =
      Math.floor(
        (seconds % 86400) / 3600
      );

    const minutes =
      Math.floor(
        (seconds % 3600) / 60
      );

    if (days > 0) {
      return `${days} д ${hours} ч`;
    }

    if (hours > 0) {
      return `${hours} ч ${minutes} мин`;
    }

    return `${minutes} мин`;
  };


  const dateTime = (value) => {
    if (!value) {
      return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "—";
    }

    return new Intl.DateTimeFormat(
      "ru-RU",
      {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit"
      }
    ).format(date);
  };


  const statusText = (status) => {
    return {
      ok: "Норма",
      warn: "Внимание",
      error: "Ошибка",
      missing: "Недоступно"
    }[status] || "—";
  };


  const statusClass = (status) => {
    if (status === "ok") {
      return "green";
    }

    if (status === "warn") {
      return "amber";
    }

    return "red";
  };


  const statusNode = (
    status,
    text = null
  ) => {
    const cls =
      statusClass(status);

    const node =
      el("div", `status ${cls}`);

    node.append(
      el("span", `dot ${cls}`),
      el(
        "span",
        "",
        text || statusText(status)
      )
    );

    return node;
  };


  const panel = (
    title,
    iconName = null,
    content = null
  ) => {
    const root =
      el("section", "panel");

    const head =
      el("div", "panel-head");

    const heading =
      el("div", "panel-heading");

    if (iconName) {
      heading.append(
        icon(
          iconName,
          "panel-icon"
        )
      );
    }

    heading.append(
      el(
        "div",
        "panel-title",
        title
      )
    );

    head.append(heading);

    root.append(head);

    if (content) {
      root.append(content);
    }

    return root;
  };


  const markUpdated = () => {
    const node =
      document.getElementById(
        "updated"
      );

    if (!node) {
      return;
    }

    const d = new Date();

    node.textContent =
      "Последнее обновление: "
      + String(
        d.getHours()
      ).padStart(2, "0")
      + ":"
      + String(
        d.getMinutes()
      ).padStart(2, "0");
  };


  const showLoading = () => {
    main.replaceChildren(
      el(
        "div",
        "loading",
        "Получение данных…"
      )
    );
  };


  const showError = (error) => {
    main.replaceChildren(
      el(
        "div",
        "error-box",
        error?.message
        || "Не удалось получить данные"
      )
    );
  };


  const setActive = (page) => {
    navButtons.forEach(
      (button) => {
        button.classList.toggle(
          "active",
          button.dataset.page === page
        );
      }
    );
  };


  const setText = (
    id,
    value
  ) => {
    const node =
      document.getElementById(id);

    if (node) {
      node.textContent = value;
    }
  };


  const liveTemperature = (
    value
  ) => {
    return typeof value === "number"
      ? `${value.toFixed(0)} °C`
      : "—";
  };


  const updateLiveHost = (
    host
  ) => {
    setText(
      "live-cpu",
      `${host.cpu.usage_percent.toFixed(1)}%`
    );

    setText(
      "live-temp",
      liveTemperature(
        host.cpu.temperature_c
      )
    );

    const cpuBar =
      document.getElementById(
        "live-cpu-bar"
      );

    if (cpuBar) {
      const cpuPercent =
        Math.min(
          100,
          Math.max(
            0,
            host.cpu.usage_percent
          )
        );

      cpuBar.style.width =
        `${cpuPercent}%`;

      const progress =
        cpuBar.parentElement;

      if (progress) {
        progress.classList.toggle(
          "amber",
          cpuPercent >= 70
          && cpuPercent < 90
        );

        progress.classList.toggle(
          "red",
          cpuPercent >= 90
        );
      }
    }

    setText(
      "live-memory-value",
      `${bytes(host.memory.used_bytes)} из ${bytes(host.memory.total_bytes)}`
    );

    setText(
      "live-memory-pct",
      `${host.memory.usage_percent.toFixed(1)}%`
    );

    setText(
      "live-load",
      `${host.load["1m"].toFixed(2)} · ${host.load["5m"].toFixed(2)} · ${host.load["15m"].toFixed(2)}`
    );

    const bar =
      document.getElementById(
        "live-memory-bar"
      );

    if (bar) {
      bar.style.width =
        `${Math.min(
          100,
          host.memory.usage_percent
        )}%`;
    }
  };


  const updateUptime = () => {
    if (
      currentPage !== "overview"
    ) {
      return;
    }

    const elapsed =
      Math.floor(
        (
          Date.now()
          - uptimeBaseTime
        )
        / 1000
      );

    setText(
      "live-uptime",
      duration(
        uptimeBaseSeconds
        + elapsed
      )
    );
  };


  const stopOverviewLive = () => {
    if (
      hostPollTimer !== null
    ) {
      clearTimeout(
        hostPollTimer
      );
    }

    if (
      uptimeTimer !== null
    ) {
      clearInterval(
        uptimeTimer
      );
    }

    hostPollTimer = null;
    uptimeTimer = null;
  };


  const stopSchedulePolling = () => {
    if (
      schedulePollTimer !== null
    ) {
      clearTimeout(
        schedulePollTimer
      );
    }

    schedulePollTimer = null;
  };


  const updateScheduleRows = (
    rows
  ) => {
    for (const row of rows) {
      const value =
        document.getElementById(
          `schedule-value-${row.id}`
        );

      const last =
        document.getElementById(
          `schedule-last-${row.id}`
        );

      if (value) {
        value.textContent =
          row.running
            ? "Работает"
            : dateTime(
                row.next_run_at
              );

        value.classList.toggle(
          "green",
          row.running === true
        );
      }

      if (last) {
        last.textContent =
          `Последний: ${dateTime(row.last_run_at)}`;
      }
    }

    markUpdated();
  };


  const pollSchedule = async () => {
    schedulePollTimer = null;

    if (
      currentPage !== "system"
      || !systemScheduleEnabled
      || document.hidden
    ) {
      return;
    }

    try {
      const rows =
        await api(
          "/api/schedule"
        );

      if (
        currentPage === "system"
      ) {
        updateScheduleRows(
          rows
        );
      }

    } catch (error) {
      if (
        error?.message
        !== "unauthorized"
      ) {
        console.warn(
          "Schedule refresh failed",
          error
        );
      }
    }

    if (
      currentPage === "system"
      && systemScheduleEnabled
      && !document.hidden
    ) {
      schedulePollTimer =
        window.setTimeout(
          pollSchedule,
          hostRefreshSeconds * 1000
        );
    }
  };


  const startSchedulePolling = () => {
    stopSchedulePolling();

    if (
      currentPage !== "system"
      || !systemScheduleEnabled
      || document.hidden
    ) {
      return;
    }

    schedulePollTimer =
      window.setTimeout(
        pollSchedule,
        hostRefreshSeconds * 1000
      );
  };


  const stopPagePolling = () => {
    if (
      pagePollTimer !== null
    ) {
      clearTimeout(
        pagePollTimer
      );
    }

    pagePollTimer = null;
  };


  const schedulePagePoll = () => {
    stopPagePolling();

    if (
      !liveTablePages.has(
        currentPage
      )
      || document.hidden
    ) {
      return;
    }

    pagePollTimer =
      window.setTimeout(
        async () => {
          pagePollTimer = null;

          const page =
            currentPage;

          if (
            !liveTablePages.has(page)
            || document.hidden
          ) {
            return;
          }

          try {
            await renderers[page](
              true
            );

          } catch (error) {
            if (
              error?.message
              !== "unauthorized"
            ) {
              console.warn(
                "Page live refresh failed",
                error
              );
            }
          }

          if (
            currentPage === page
          ) {
            schedulePagePoll();
          }
        },
        hostRefreshSeconds * 1000
      );
  };


  const scheduleHostPoll = () => {
    if (
      currentPage !== "overview"
      || document.hidden
    ) {
      return;
    }

    hostPollTimer =
      window.setTimeout(
        pollHost,
        hostRefreshSeconds * 1000
      );
  };


  const pollHost = async () => {
    hostPollTimer = null;

    if (
      currentPage !== "overview"
      || document.hidden
    ) {
      return;
    }

    try {
      const host =
        await api("/api/host");

      if (
        currentPage === "overview"
      ) {
        updateLiveHost(host);
        markUpdated();
      }

    } catch (error) {
      if (
        error?.message
        !== "unauthorized"
      ) {
        console.warn(
          "Host refresh failed",
          error
        );
      }
    }

    scheduleHostPoll();
  };


  const startOverviewLive = (
    host
  ) => {
    stopOverviewLive();

    uptimeBaseSeconds =
      Number(
        host.uptime_seconds
      ) || 0;

    uptimeBaseTime =
      Date.now();

    const configured =
      Number(
        host.refresh_seconds
      );

    hostRefreshSeconds = (
      Number.isFinite(
        configured
      )
      && configured >= 2
      && configured <= 60
    )
      ? configured
      : 5;

    updateUptime();

    uptimeTimer =
      window.setInterval(
        updateUptime,
        1000
      );

    scheduleHostPoll();
  };


  const buildStatePanel = (
    host
  ) => {
    const root =
      panel(
        "Состояние сервера",
        "display"
      );

    const rows = [
      [
        "cpu",
        "Процессор",
        `${host.cpu.usage_percent.toFixed(1)}%`,
        liveTemperature(
          host.cpu.temperature_c
        )
      ],
      [
        "memory",
        "Память",
        null,
        `${host.memory.usage_percent.toFixed(1)}%`
      ],
      [
        "activity",
        "Нагрузка",
        `${host.load["1m"].toFixed(2)} · ${host.load["5m"].toFixed(2)} · ${host.load["15m"].toFixed(2)}`,
        ""
      ],
      [
        "clock",
        "Время работы",
        duration(
          host.uptime_seconds
        ),
        ""
      ]
    ];

    rows.forEach(
      (
        [
          iconName,
          label,
          value,
          right
        ],
        index
      ) => {
        const row =
          el(
            "div",
            "state-row"
          );

        row.append(
          icon(iconName),
          el(
            "div",
            "label",
            label
          )
        );

        if (index === 0) {
          const wrap =
            el(
              "div",
              "progress-wrap"
            );

          const valueNode =
            el(
              "div",
              "value",
              value
            );

          valueNode.id =
            "live-cpu";

          const progress =
            el(
              "div",
              "progress"
            );

          const bar =
            el("span");

          bar.id =
            "live-cpu-bar";

          const cpuPercent =
            Math.min(
              100,
              Math.max(
                0,
                host.cpu.usage_percent
              )
            );

          bar.style.width =
            `${cpuPercent}%`;

          if (cpuPercent >= 90) {
            progress.classList.add(
              "red"
            );
          } else if (cpuPercent >= 70) {
            progress.classList.add(
              "amber"
            );
          }

          progress.append(bar);

          wrap.append(
            valueNode,
            progress
          );

          row.append(wrap);

        } else if (index === 1) {
          const wrap =
            el(
              "div",
              "progress-wrap"
            );

          const valueNode =
            el(
              "div",
              "value",
              `${bytes(host.memory.used_bytes)} из ${bytes(host.memory.total_bytes)}`
            );

          valueNode.id =
            "live-memory-value";

          const progress =
            el(
              "div",
              "progress"
            );

          const bar =
            el("span");

          bar.id =
            "live-memory-bar";

          bar.style.width =
            `${host.memory.usage_percent}%`;

          progress.append(bar);

          wrap.append(
            valueNode,
            progress
          );

          row.append(wrap);

        } else {
          const valueNode =
            el(
              "div",
              "value",
              value
            );

          if (index === 2) {
            valueNode.id =
              "live-load";
          }

          if (index === 3) {
            valueNode.id =
              "live-uptime";
          }

          row.append(
            valueNode
          );
        }

        const rightNode =
          el(
            "div",
            "value",
            right
          );

        if (index === 0) {
          rightNode.id =
            "live-temp";
        }

        if (index === 1) {
          rightNode.id =
            "live-memory-pct";
        }

        row.append(
          rightNode
        );

        root.append(row);
      }
    );

    return root;
  };


  const appendAttentionItem = (
    root,
    item
  ) => {
    root.querySelector(
      ".attention-empty"
    )?.remove();

    const row =
      el(
        "button",
        "attention-row"
      );

    row.type = "button";

    const alertIcon =
      icon(
        "alert",
        item.severity === "warn"
          ? "amber"
          : "red"
      );

    const body =
      el(
        "div",
        "attention-copy"
      );

    body.append(
      el(
        "div",
        "alert-title",
        item.title
      ),
      el(
        "div",
        "alert-sub",
        item.message
      )
    );

    row.append(
      alertIcon,
      body,
      icon(
        "chevron",
        "chevron"
      )
    );

    if (
      typeof item.target === "string"
      && renderers[item.target]
      && moduleMetadata.get(
        item.target
      )?.enabled === true
    ) {
      row.addEventListener(
        "click",
        () => openPage(
          item.target
        )
      );
    } else {
      row.disabled = true;
    }

    root.append(row);
  };


  const buildAttentionPanel = (
    items
  ) => {
    const root =
      panel(
        "Требует внимания",
        "alert"
      );

    if (!items.length) {
      const empty =
        el(
          "div",
          "attention-empty"
        );

      empty.append(
        el(
          "span",
          "dot green"
        ),
        el(
          "span",
          "",
          "Проблем не обнаружено"
        )
      );

      root.append(empty);
    } else {
      items.forEach(
        (item) => appendAttentionItem(
          root,
          item
        )
      );
    }

    return root;
  };


  const buildStoragePanel = (
    rows
  ) => {
    const root =
      panel(
        "Хранилища",
        "hdd"
      );

    rows.forEach(
      (disk) => {
        const row =
          el(
            "div",
            "storage-row"
          );

        const info =
          el("div");

        info.append(
          el(
            "div",
            "storage-name",
            disk.name
          )
        );

        info.append(
          el(
            "div",
            "sub",
            disk.total_bytes === null
              ? "Недоступно"
              : `${bytes(disk.used_bytes)} из ${bytes(disk.total_bytes)}`
          )
        );

        const progress =
          el(
            "div",
            "progress"
          );

        const bar =
          el("span");

        bar.style.width =
          `${Math.min(
            100,
            disk.usage_percent || 0
          )}%`;

        if (
          disk.status === "error"
          || disk.status === "missing"
        ) {
          progress.classList.add(
            "red"
          );
        }

        progress.append(bar);

        row.append(
          icon("hdd"),
          info,
          progress,
          el(
            "div",
            "pct",
            disk.usage_percent === null
              ? "—"
              : `${disk.usage_percent.toFixed(1)}%`
          ),
          statusNode(
            disk.status
          )
        );

        root.append(row);
      }
    );

    return root;
  };


  const summaryLabel = (
    key,
    data
  ) => {
    if (key === "services") {
      return data.issues
        ? `${data.issues} проблем`
        : "Все работают";
    }

    if (key === "docker") {
      return data.issues
        ? `${data.issues} проблем`
        : `${data.total} контейнеров`;
    }

    if (key === "fail2ban") {
      return data.active_bans
        ? `${data.active_bans} блокировок`
        : "Блокировок нет";
    }

    if (key === "smart") {
      return data.issues
        ? `${data.issues} проблем`
        : "Исправно";
    }

    if (key === "schedule") {
      return data.issues
        ? `${data.issues} проблем`
        : "Норма";
    }

    return statusText(
      data.status
    );
  };


  const appendSummaryRow = (
    root,
    {
      iconName,
      label,
      status,
      text,
      target = null
    }
  ) => {
    const button =
      el(
        "button",
        "summary-row"
      );

    button.type = "button";

    const canOpen =
      typeof target === "string"
      && renderers[target]
      && moduleMetadata.get(
        target
      )?.enabled === true;

    if (canOpen) {
      button.addEventListener(
        "click",
        () => openPage(
          target
        )
      );
    } else {
      button.disabled = true;
      button.classList.add(
        "summary-row-static"
      );
    }

    button.append(
      icon(iconName),
      el(
        "div",
        "",
        label
      ),
      statusNode(
        status,
        text
      )
    );

    if (canOpen) {
      button.append(
        icon(
          "chevron",
          "chevron"
        )
      );
    }

    root.append(button);
    return button;
  };


  const buildSummaryPanel = (
    summary
  ) => {
    const root =
      panel(
        "Сводка",
        "activity"
      );

    const rows = [
      ["gear", "Службы", "services", "services"],
      ["box", "Docker", "docker", "docker"],
      ["shield", "Fail2Ban", "fail2ban", "fail2ban"],
      ["hdd", "SMART", "smart", "system"],
      ["calendar", "Расписание", "schedule", "system"]
    ];

    rows.forEach(
      ([iconName, label, key, target]) => {
        if (!summary[key]) {
          return;
        }

        appendSummaryRow(
          root,
          {
            iconName,
            label,
            status:
              summary[key].status,
            text:
              summaryLabel(
                key,
                summary[key]
              ),
            target
          }
        );
      }
    );

    return root;
  };


  const registerPlacement = (
    moduleId,
    placement,
    handler
  ) => {
    if (
      !["overview", "system"].includes(
        placement
      )
      || typeof handler !== "function"
    ) {
      throw new Error(
        "Некорректная регистрация placement"
      );
    }

    placementHooks[placement].push({
      moduleId,
      handler
    });
  };


  const runPlacement = async (
    placement,
    context
  ) => {
    const hooks =
      placementHooks[placement]
      || [];

    for (const hook of hooks) {
      if (
        moduleMetadata.get(
          hook.moduleId
        )?.enabled !== true
      ) {
        continue;
      }

      try {
        await hook.handler(
          context
        );
      } catch (error) {
        console.warn(
          `Module placement failed: ${hook.moduleId}/${placement}`,
          error
        );

        if (
          placement === "overview"
          && context.attentionPanel
        ) {
          appendAttentionItem(
            context.attentionPanel,
            {
              severity: "warn",
              title:
                `Модуль «${moduleMetadata.get(hook.moduleId)?.name || hook.moduleId}» недоступен`,
              message:
                error?.message
                || "Не удалось получить данные расширения.",
              target: null
            }
          );
        }
      }
    }
  };


  const renderOverview = async () => {
    showLoading();

    const data =
      await api(
        "/api/overview"
      );

    main.replaceChildren();

    const columns =
      el(
        "div",
        "overview-columns"
      );

    const leftColumn =
      el(
        "div",
        "overview-column"
      );

    const rightColumn =
      el(
        "div",
        "overview-column"
      );

    const overviewAttention =
      Array.isArray(data.attention)
        ? [...data.attention]
        : [];

    for (const error of extensionErrors) {
      overviewAttention.push({
        severity: "warn",
        title: `Расширение «${error.id || "unknown"}» не загружено`,
        message: error.message || "Ошибка загрузки расширения.",
        target: null
      });
    }

    const attentionPanel =
      buildAttentionPanel(
        overviewAttention
      );

    const summaryPanel =
      buildSummaryPanel(
        data.summary
      );

    leftColumn.append(
      buildStatePanel(
        data.host
      )
    );

    if (
      Array.isArray(data.storage)
      && data.storage.length > 0
    ) {
      leftColumn.append(
        buildStoragePanel(
          data.storage
        )
      );
    }

    rightColumn.append(
      attentionPanel,
      summaryPanel
    );

    columns.append(
      leftColumn,
      rightColumn
    );

    const updated =
      el(
        "div",
        "updated",
        ""
      );

    updated.id = "updated";

    main.append(
      columns,
      updated
    );

    await runPlacement(
      "overview",
      {
        data,
        columns,
        leftColumn,
        rightColumn,
        attentionPanel,
        summaryPanel
      }
    );

    markUpdated();
    startOverviewLive(
      data.host
    );
  };


  const renderTablePage = async (
    {
      endpoint,
      title,
      iconName,
      columns,
      rowBuilder
    },
    silent = false
  ) => {
    if (!silent) {
      showLoading();
    }

    const rows =
      await api(endpoint);

    const root =
      panel(
        title,
        iconName
      );

    const wrap =
      el(
        "div",
        "table-wrap"
      );

    const table =
      el(
        "table",
        "table"
      );

    const thead =
      document.createElement(
        "thead"
      );

    const trh =
      document.createElement(
        "tr"
      );

    columns.forEach(
      (column) => {
        const classes = [];

        if (column.right) {
          classes.push("right");
        }

        if (column.className) {
          classes.push(
            column.className
          );
        }

        trh.append(
          el(
            "th",
            classes.join(" "),
            column.label
          )
        );
      }
    );

    thead.append(trh);

    const tbody =
      document.createElement(
        "tbody"
      );

    rows.forEach(
      (row) => {
        tbody.append(
          rowBuilder(row)
        );
      }
    );

    table.append(
      thead,
      tbody
    );

    wrap.append(table);

    root.append(wrap);

    main.replaceChildren(
      root
    );
  };


  const renderServices = (
    silent = false
  ) =>
    renderTablePage({
      endpoint:
        "/api/services",

      title:
        "Службы",

      iconName:
        "gear",

      columns: [
        {label:"Служба"},
        {label:"Состояние"},
        {label:"Время работы"},
        {
          label:"Действие",
          right:true,
          className:"action-col"
        }
      ],

      rowBuilder: (row) => {
        const tr =
          document.createElement(
            "tr"
          );

        tr.append(
          el(
            "td",
            "",
            row.name
          )
        );

        const tdStatus =
          document.createElement(
            "td"
          );

        tdStatus.append(
          statusNode(
            row.status
          )
        );

        tr.append(
          tdStatus,
          el(
            "td",
            "muted",
            duration(
              row.uptime_seconds
            )
          )
        );

        const action =
          document.createElement(
            "td"
          );

        action.className =
          "right action-col";

        if (
          row.restart_allowed
        ) {
          const button =
            el(
              "button",
              "btn",
              "Перезапустить"
            );

          button.addEventListener(
            "click",
            () => restartObject(
              "service.restart",
              row,
              button
            )
          );

          action.append(
            button
          );
        }

        tr.append(action);

        return tr;
      }
    }, silent);


  const dockerStatusLabel = (
    row
  ) => {
    if (row.state === "paused") {
      return "Пауза";
    }

    if (
      row.state === "restarting"
    ) {
      return "Перезапуск";
    }

    if (row.health === "starting") {
      return "Запуск";
    }

    return statusText(
      row.status
    );
  };


  const dockerHealthDisplay = (
    row
  ) => {
    if (row.state === "paused") {
      return {
        text: "Приостановлен",
        className: "amber"
      };
    }

    if (
      row.state === "restarting"
    ) {
      return {
        text: "Перезапуск",
        className: "amber"
      };
    }

    if (row.health === "healthy") {
      return {
        text: "Исправен",
        className: "green"
      };
    }

    if (row.health === "starting") {
      return {
        text: "Запуск",
        className: "amber"
      };
    }

    if (
      row.health === "unhealthy"
    ) {
      return {
        text: "Ошибка",
        className: "red"
      };
    }

    return {
      text: "—",
      className: "muted"
    };
  };


  const renderDocker = (
    silent = false
  ) =>
    renderTablePage({
      endpoint:
        "/api/docker",

      title:
        "Docker",

      iconName:
        "box",

      columns: [
        {label:"Контейнер"},
        {label:"Состояние"},
        {label:"Проверка"},
        {label:"Время работы"},
        {label:"Перезапуски"},
        {
          label:"Действие",
          right:true,
          className:"action-col"
        }
      ],

      rowBuilder: (row) => {
        const tr =
          document.createElement(
            "tr"
          );

        tr.append(
          el(
            "td",
            "",
            row.name
          )
        );

        const tdStatus =
          document.createElement(
            "td"
          );

        tdStatus.append(
          statusNode(
            row.status,
            dockerStatusLabel(
              row
            )
          )
        );

        const health =
          dockerHealthDisplay(
            row
          );

        tr.append(
          tdStatus,
          el(
            "td",
            health.className,
            health.text
          ),
          el(
            "td",
            "muted",
            duration(
              row.uptime_seconds
            )
          ),
          el(
            "td",
            "muted",
            String(
              row.restart_count
            )
          )
        );

        const action =
          document.createElement(
            "td"
          );

        action.className =
          "right action-col";

        if (
          row.restart_allowed
        ) {
          const button =
            el(
              "button",
              "btn",
              "Перезапустить"
            );

          button.addEventListener(
            "click",
            () => restartObject(
              "docker.restart",
              row,
              button
            )
          );

          action.append(
            button
          );
        }

        tr.append(action);

        return tr;
      }
    }, silent);


  const fail2BanDetailApi = async (
    jail
  ) => {
    const response = await fetch(
      `/api/fail2ban/banned?jail=${encodeURIComponent(jail)}`,
      {
        credentials: "same-origin",
        cache: "no-store",
        headers: {
          Accept: "application/json"
        }
      }
    );

    if (response.status === 401) {
      window.location.href = "/login";
      throw new Error("unauthorized");
    }

    const payload =
      await response.json();

    if (
      !response.ok
      || payload.ok !== true
    ) {
      throw new Error(
        payload?.error?.message
        || "Не удалось получить блокировки"
      );
    }

    return payload.data;
  };


  const loadFail2BanDetail = async (
    row,
    box
  ) => {
    box.replaceChildren(
      el(
        "div",
        "f2b-detail-loading",
        "Получение списка блокировок…"
      )
    );

    try {
      const data =
        await fail2BanDetailApi(
          row.id
        );

      box.replaceChildren();

      const head =
        el(
          "div",
          "f2b-detail-head"
        );

      head.append(
        el(
          "div",
          "f2b-detail-title",
          `Активные блокировки: ${data.count}`
        )
      );

      box.append(head);

      if (
        !Array.isArray(
          data.banned_ips
        )
        || data.banned_ips.length === 0
      ) {
        box.append(
          el(
            "div",
            "f2b-empty",
            "Активных блокировок нет"
          )
        );

        return;
      }

      const list =
        el(
          "div",
          "f2b-ip-list"
        );

      for (
        const address
        of data.banned_ips
      ) {
        const item =
          el(
            "div",
            "f2b-ip-row"
          );

        item.append(
          el(
            "code",
            "f2b-ip",
            address
          )
        );

        if (
          data.unban_allowed
        ) {
          const button =
            el(
              "button",
              "btn",
              "Разбанить"
            );

          button.type =
            "button";

          button.addEventListener(
            "click",
            async () => {
              const confirmed =
                window.confirm(
                  `Разблокировать ${address} в «${data.name}»?`
                );

              if (!confirmed) {
                return;
              }

              button.disabled =
                true;

              button.textContent =
                "Разблокировка…";

              try {
                await actionApi(
                  "fail2ban.unban",
                  {
                    jail: data.id,
                    ip: address
                  }
                );

                openFail2BanJail =
                  data.id;

                await renderFail2Ban(
                  true
                );

              } catch (error) {
                if (
                  error?.message
                  !== "unauthorized"
                ) {
                  window.alert(
                    error?.message
                    || "Не удалось разблокировать IP"
                  );

                  button.disabled =
                    false;

                  button.textContent =
                    "Разбанить";
                }
              }
            }
          );

          item.append(
            button
          );
        }

        list.append(
          item
        );
      }

      box.append(list);

    } catch (error) {
      if (
        error?.message
        === "unauthorized"
      ) {
        return;
      }

      box.replaceChildren(
        el(
          "div",
          "error-box",
          error?.message
          || "Не удалось получить блокировки"
        )
      );
    }
  };


  const renderFail2Ban = async (
    silent = false
  ) => {
    if (!silent) {
      showLoading();
    }

    const rows =
      await api(
        "/api/fail2ban"
      );

    const root =
      panel(
        "Fail2Ban",
        "shield"
      );

    const wrap =
      el(
        "div",
        "table-wrap"
      );

    const table =
      el(
        "table",
        "table f2b-table"
      );

    const thead =
      document.createElement(
        "thead"
      );

    const header =
      document.createElement(
        "tr"
      );

    [
      "Защита",
      "Состояние",
      "Попытки сейчас",
      "Всего попыток",
      "Заблокировано",
      "Всего блокировок",
      ""
    ].forEach(
      (label) => {
        header.append(
          el(
            "th",
            "",
            label
          )
        );
      }
    );

    thead.append(
      header
    );

    const tbody =
      document.createElement(
        "tbody"
      );

    for (const row of rows) {
      const summary =
        document.createElement(
          "tr"
        );

      summary.className =
        "f2b-main-row";

      const statusCell =
        document.createElement(
          "td"
        );

      statusCell.append(
        statusNode(
          row.status
        )
      );

      const arrowCell =
        document.createElement(
          "td"
        );

      arrowCell.className =
        "f2b-arrow-cell";

      const arrow =
        icon(
          "chevron",
          "chevron f2b-chevron"
        );

      arrowCell.append(
        arrow
      );

      summary.append(
        el(
          "td",
          "f2b-name",
          row.name
        ),
        statusCell,
        el(
          "td",
          "muted",
          String(
            row.currently_failed
            ?? 0
          )
        ),
        el(
          "td",
          "muted",
          String(
            row.total_failed
            ?? 0
          )
        ),
        el(
          "td",
          row.currently_banned > 0
            ? "amber"
            : "muted",
          String(
            row.currently_banned
            ?? 0
          )
        ),
        el(
          "td",
          "muted",
          String(
            row.total_banned
            ?? 0
          )
        ),
        arrowCell
      );

      const detail =
        document.createElement(
          "tr"
        );

      detail.className =
        "f2b-detail-row";

      detail.hidden = true;

      const detailCell =
        document.createElement(
          "td"
        );

      detailCell.colSpan = 7;

      const detailBox =
        el(
          "div",
          "f2b-detail-box"
        );

      detailCell.append(
        detailBox
      );

      detail.append(
        detailCell
      );

      const openDetail =
        async () => {
          const opening =
            detail.hidden;

          for (
            const other
            of tbody.querySelectorAll(
              ".f2b-detail-row"
            )
          ) {
            other.hidden = true;
          }

          for (
            const other
            of tbody.querySelectorAll(
              ".f2b-main-row"
            )
          ) {
            other.classList.remove(
              "open"
            );
          }

          if (!opening) {
            openFail2BanJail =
              null;

            return;
          }

          detail.hidden =
            false;

          summary.classList.add(
            "open"
          );

          openFail2BanJail =
            row.id;

          await loadFail2BanDetail(
            row,
            detailBox
          );
        };

      summary.addEventListener(
        "click",
        openDetail
      );

      tbody.append(
        summary,
        detail
      );

      if (
        openFail2BanJail
        === row.id
      ) {
        detail.hidden =
          false;

        summary.classList.add(
          "open"
        );

        await loadFail2BanDetail(
          row,
          detailBox
        );
      }
    }

    table.append(
      thead,
      tbody
    );

    wrap.append(
      table
    );

    root.append(
      wrap
    );

    main.replaceChildren(
      root
    );
  };


  const compactRow = (
    iconName,
    name,
    value,
    status = null,
    sub = null
  ) => {
    const row =
      el(
        "div",
        "compact-row"
      );

    const copy =
      el(
        "div",
        "compact-copy"
      );

    copy.append(
      el(
        "div",
        "compact-name",
        name
      )
    );

    if (sub) {
      copy.append(
        el(
          "div",
          "sub",
          sub
        )
      );
    }

    row.append(
      icon(iconName),
      copy,
      el(
        "div",
        "compact-value",
        value
      )
    );

    if (status) {
      row.append(
        statusNode(
          status
        )
      );
    }

    return row;
  };


  const renderSystem = async () => {
    showLoading();

    const data =
      await api(
        "/api/system"
      );

    systemScheduleEnabled =
      data?.enabled?.schedule === true;

    const columns =
      el(
        "div",
        "system-columns"
      );

    const leftColumn =
      el(
        "div",
        "system-column"
      );

    const rightColumn =
      el(
        "div",
        "system-column"
      );

    if (
      data?.enabled?.storage === true
    ) {
      const storage =
        panel(
          "Хранилища",
          "hdd"
        );

      data.storage.forEach(
        (row) => {
          storage.append(
            compactRow(
              "hdd",
              row.name,
              row.usage_percent === null
                ? "Недоступно"
                : `${row.usage_percent.toFixed(1)}%`,
              row.status,
              row.total_bytes === null
                ? null
                : `${bytes(row.used_bytes)} из ${bytes(row.total_bytes)}`
            )
          );
        }
      );

      leftColumn.append(
        storage
      );
    }

    if (
      data?.enabled?.smart === true
    ) {
      const smart =
        panel(
          "SMART",
          "hdd"
        );

      data.smart.forEach(
        (row) => {
          const sub = (
            row.state === "standby"
          )
            ? "Ожидание"
            : (
                row.power_on_hours
                  ? `${row.power_on_hours} ч`
                  : null
              );

          smart.append(
            compactRow(
              "hdd",
              row.name,
              row.temperature_c === null
                ? "—"
                : `${row.temperature_c.toFixed(0)} °C`,
              row.status,
              sub
            )
          );
        }
      );

      leftColumn.append(
        smart
      );
    }

    if (
      data?.enabled?.schedule === true
    ) {
      const schedule =
        panel(
          "Расписание",
          "calendar"
        );

      data.schedule.forEach(
        (row) => {
          const item =
            compactRow(
              "calendar",
              row.name,
              row.running
                ? "Работает"
                : dateTime(
                    row.next_run_at
                  ),
              row.status,
              `Последний: ${dateTime(row.last_run_at)}`
            );

          const value =
            item.querySelector(
              ".compact-value"
            );

          if (value) {
            value.id =
              `schedule-value-${row.id}`;

            if (row.running) {
              value.classList.add(
                "green"
              );
            }
          }

          const last =
            item.querySelector(
              ".sub"
            );

          if (last) {
            last.id =
              `schedule-last-${row.id}`;
          }

          schedule.append(
            item
          );
        }
      );

      rightColumn.append(
        schedule
      );
    }

    columns.append(
      leftColumn,
      rightColumn
    );

    const updated =
      el(
        "div",
        "updated",
        ""
      );

    updated.id = "updated";

    main.replaceChildren(
      columns,
      updated
    );

    await runPlacement(
      "system",
      {
        data,
        columns,
        leftColumn,
        rightColumn
      }
    );

    markUpdated();

    if (systemScheduleEnabled) {
      startSchedulePolling();
    }
  };


  const docsReadApi = async (
    documentId
  ) => {
    return api(
      `/api/docs/read?document=${encodeURIComponent(documentId)}`
    );
  };


  const resolveDocumentationLink = (
    currentId,
    href,
    documentIds
  ) => {
    try {
      const base =
        new URL(
          `https://docs.invalid/${currentId}`
        );

      const target =
        new URL(
          href,
          base
        );

      if (
        target.origin
        !== base.origin
      ) {
        return null;
      }

      const id =
        decodeURIComponent(
          target.pathname.replace(
            /^\/+/,
            ""
          )
        );

      return documentIds.has(id)
        ? id
        : null;

    } catch {
      return null;
    }
  };


  const renderDocs = async () => {
    showLoading();

    const data =
      await api(
        "/api/docs"
      );

    const documents =
      Array.isArray(
        data.documents
      )
        ? data.documents
        : [];

    if (
      documents.length === 0
    ) {
      main.replaceChildren(
        panel(
          "Документация",
          "docs",
          el(
            "div",
            "docs-empty",
            "Документы не найдены"
          )
        )
      );

      return;
    }

    const ids =
      new Set(
        documents.map(
          (row) => row.id
        )
      );

    if (
      !openDocumentId
      || !ids.has(
        openDocumentId
      )
    ) {
      openDocumentId =
        ids.has(
          "00-README.md"
        )
          ? "00-README.md"
          : documents[0].id;
    }

    const layout =
      el(
        "div",
        "docs-layout"
      );

    const sidebar =
      el(
        "div",
        "docs-sidebar"
      );

    const sidebarHead =
      el(
        "div",
        "docs-sidebar-head",
        `Документы · ${documents.length}`
      );

    const list =
      el(
        "div",
        "docs-list"
      );

    const view =
      el(
        "div",
        "docs-view"
      );

    const viewHead =
      el(
        "div",
        "docs-view-head"
      );

    const title =
      el(
        "h2",
        "docs-view-title",
        "Документация"
      );

    viewHead.append(
      title
    );

    const article =
      el(
        "article",
        "docs-article"
      );

    view.append(
      viewHead,
      article
    );

    const buttons =
      new Map();

    const loadDocument =
      async (
        documentId
      ) => {
        article.replaceChildren(
          el(
            "div",
            "docs-loading",
            "Загрузка документа…"
          )
        );

        for (
          const [
            id,
            button
          ]
          of buttons
        ) {
          button.classList.toggle(
            "active",
            id === documentId
          );
        }

        try {
          const document =
            await docsReadApi(
              documentId
            );

          openDocumentId =
            document.id;

          title.textContent =
            document.title;

          article.innerHTML =
            document.html;

          for (
            const link
            of article.querySelectorAll(
              "a[href]"
            )
          ) {
            const href =
              link.getAttribute(
                "href"
              );

            if (!href) {
              continue;
            }

            const internal =
              resolveDocumentationLink(
                document.id,
                href,
                ids
              );

            if (internal) {
              link.addEventListener(
                "click",
                (event) => {
                  event.preventDefault();

                  loadDocument(
                    internal
                  );
                }
              );

              continue;
            }

            try {
              const parsed =
                new URL(
                  href,
                  window.location.href
                );

              if (
                parsed.protocol === "http:"
                || parsed.protocol === "https:"
              ) {
                link.target =
                  "_blank";

                link.rel =
                  "noopener noreferrer";
              }

            } catch {
              // Оставляем безопасную относительную ссылку как есть.
            }
          }

        } catch (error) {
          if (
            error?.message
            === "unauthorized"
          ) {
            return;
          }

          article.replaceChildren(
            el(
              "div",
              "error-box",
              error?.message
              || "Не удалось открыть документ"
            )
          );
        }
      };


    for (
      const document
      of documents
    ) {
      const button =
        el(
          "button",
          "docs-item",
          document.title
        );

      button.type =
        "button";

      button.title =
        document.id;

      button.addEventListener(
        "click",
        () => loadDocument(
          document.id
        )
      );

      buttons.set(
        document.id,
        button
      );

      list.append(
        button
      );
    }

    sidebar.append(
      sidebarHead,
      list
    );

    layout.append(
      sidebar,
      view
    );

    main.replaceChildren(
      layout
    );

    await loadDocument(
      openDocumentId
    );
  };


  const auditActionLabels = {
    "auth.login":
      "Вход",

    "auth.logout":
      "Выход",

    "service.restart":
      "Перезапуск службы",

    "docker.restart":
      "Перезапуск контейнера",

    "fail2ban.unban":
      "Разблокировка IP",

    "system.reboot":
      "Перезагрузка сервера",

    "system.poweroff":
      "Выключение сервера",

    "api.action":
      "API-действие",

    "audit.time-test":
      "Проверка журнала"
  };


  const auditResultInfo = (
    result
  ) => {
    switch (result) {
      case "ok":
        return {
          label: "Успешно",
          className: "ok"
        };

      case "requested":
        return {
          label: "Запрошено",
          className: "warn"
        };

      case "blocked":
        return {
          label: "Заблокировано",
          className: "warn"
        };

      case "failed":
      case "csrf_failed":
        return {
          label: "Ошибка",
          className: "error"
        };

      default:
        return {
          label: result || "—",
          className: ""
        };
    }
  };


  const auditActionLabel = (
    action
  ) => {
    return (
      auditActionLabels[action]
      || action
      || "—"
    );
  };


  const auditDetails = (
    details
  ) => {
    if (
      !details
      || typeof details !== "object"
    ) {
      return [];
    }

    const labels = {
      target: "Объект",
      jail: "Jail",
      ip: "IP",
      code: "Код"
    };

    return Object.entries(
      details
    ).map(
      ([key, value]) => {
        return {
          key:
            labels[key]
            || key,

          value:
            String(value)
        };
      }
    );
  };


  const renderAudit = async () => {
    showLoading();

    const data =
      await api(
        "/api/audit"
      );

    const entries =
      Array.isArray(
        data.entries
      )
        ? data.entries
        : [];

    const root =
      panel(
        "Аудит",
        "audit"
      );

    const toolbar =
      el(
        "div",
        "audit-toolbar"
      );

    const actionFilter =
      document.createElement(
        "select"
      );

    actionFilter.className =
      "audit-filter";

    const resultFilter =
      document.createElement(
        "select"
      );

    resultFilter.className =
      "audit-filter";


    const addOption = (
      select,
      value,
      label
    ) => {
      const option =
        document.createElement(
          "option"
        );

      option.value =
        value;

      option.textContent =
        label;

      select.append(
        option
      );
    };


    addOption(
      actionFilter,
      "",
      "Все действия"
    );

    const actions =
      [
        ...new Set(
          entries.map(
            (row) =>
              row.action
          )
        )
      ].sort(
        (a, b) =>
          auditActionLabel(a)
            .localeCompare(
              auditActionLabel(b),
              "ru"
            )
      );

    for (
      const action
      of actions
    ) {
      addOption(
        actionFilter,
        action,
        auditActionLabel(
          action
        )
      );
    }


    addOption(
      resultFilter,
      "",
      "Все результаты"
    );

    const results =
      [
        ...new Set(
          entries.map(
            (row) =>
              row.result
          )
        )
      ];

    for (
      const result
      of results
    ) {
      addOption(
        resultFilter,
        result,
        auditResultInfo(
          result
        ).label
      );
    }


    const count =
      el(
        "div",
        "audit-count"
      );

    toolbar.append(
      actionFilter,
      resultFilter,
      count
    );


    const wrap =
      el(
        "div",
        "table-wrap"
      );

    root.append(
      toolbar,
      wrap
    );


    const draw =
      () => {
        const action =
          actionFilter.value;

        const result =
          resultFilter.value;

        const filtered =
          entries.filter(
            (row) => {
              if (
                action
                && row.action !== action
              ) {
                return false;
              }

              if (
                result
                && row.result !== result
              ) {
                return false;
              }

              return true;
            }
          );

        const shown =
          filtered.slice(
            0,
            100
          );

        count.textContent =
          `Показано ${shown.length} из ${filtered.length}`;

        wrap.replaceChildren();

        if (
          shown.length === 0
        ) {
          wrap.append(
            el(
              "div",
              "audit-empty",
              "Записей не найдено"
            )
          );

          return;
        }

        const table =
          el(
            "table",
            "table audit-table"
          );

        const thead =
          document.createElement(
            "thead"
          );

        const header =
          document.createElement(
            "tr"
          );

        [
          "Время",
          "Пользователь",
          "IP клиента",
          "Действие",
          "Результат",
          "Подробности"
        ].forEach(
          (label) => {
            header.append(
              el(
                "th",
                "",
                label
              )
            );
          }
        );

        thead.append(
          header
        );

        const tbody =
          document.createElement(
            "tbody"
          );

        for (
          const row
          of shown
        ) {
          const tr =
            document.createElement(
              "tr"
            );

          const resultInfo =
            auditResultInfo(
              row.result
            );

          const resultCell =
            document.createElement(
              "td"
            );

          const resultNode =
            el(
              "span",
              `audit-result ${resultInfo.className}`
            );

          resultNode.append(
            el(
              "span",
              "audit-dot"
            ),
            document.createTextNode(
              resultInfo.label
            )
          );

          resultCell.append(
            resultNode
          );


          const detailsCell =
            document.createElement(
              "td"
            );

          detailsCell.className =
            "audit-details";

          const details =
            auditDetails(
              row.details
            );

          if (
            details.length === 0
          ) {
            detailsCell.textContent =
              "—";

            detailsCell.classList.add(
              "muted"
            );

          } else {
            for (
              const detail
              of details
            ) {
              const span =
                el(
                  "span",
                  "audit-detail"
                );

              span.append(
                document.createTextNode(
                  `${detail.key}: `
                ),
                el(
                  "strong",
                  "",
                  detail.value
                )
              );

              detailsCell.append(
                span
              );
            }
          }


          tr.append(
            el(
              "td",
              "muted",
              dateTime(
                row.timestamp
              )
            ),

            el(
              "td",
              "",
              row.user
              || "—"
            ),

            el(
              "td",
              "muted",
              row.client_ip
              || "—"
            ),

            el(
              "td",
              "audit-action",
              auditActionLabel(
                row.action
              )
            ),

            resultCell,
            detailsCell
          );

          tbody.append(
            tr
          );
        }

        table.append(
          thead,
          tbody
        );

        wrap.append(
          table
        );
      };


    actionFilter.addEventListener(
      "change",
      draw
    );

    resultFilter.addEventListener(
      "change",
      draw
    );

    draw();

    main.replaceChildren(
      root
    );
  };


  const registerPage = (
    moduleId,
    renderer,
    options = {}
  ) => {
    if (
      typeof moduleId !== "string"
      || !moduleId
      || typeof renderer !== "function"
    ) {
      throw new Error(
        "Некорректная регистрация страницы"
      );
    }

    renderers[moduleId] = renderer;

    if (options.live === true) {
      liveTablePages.add(
        moduleId
      );
    }
  };


  registerPage(
    "overview",
    renderOverview
  );
  registerPage(
    "services",
    renderServices,
    {live: true}
  );
  registerPage(
    "docker",
    renderDocker,
    {live: true}
  );
  registerPage(
    "fail2ban",
    renderFail2Ban,
    {live: true}
  );
  registerPage(
    "system",
    renderSystem
  );
  registerPage(
    "docs",
    renderDocs
  );
  registerPage(
    "audit",
    renderAudit
  );


  async function openPage(
    page
  ) {
    const meta =
      moduleMetadata.get(
        page
      );

    if (
      !renderers[page]
      || meta?.enabled !== true
      || meta?.page !== true
    ) {
      return;
    }

    stopOverviewLive();
    stopPagePolling();
    stopSchedulePolling();

    currentPage = page;
    setActive(page);

    document.body.classList.remove(
      "menu-open"
    );

    try {
      await renderers[page](
        false
      );

      if (
        liveTablePages.has(
          page
        )
      ) {
        schedulePagePoll();
      }

    } catch (error) {
      if (
        error?.message
        !== "unauthorized"
      ) {
        showError(error);
      }
    }
  }


  const loadAsset = (
    asset
  ) => {
    return new Promise(
      (resolve, reject) => {
        if (
          !asset
          || typeof asset.url !== "string"
        ) {
          resolve();
          return;
        }

        if (asset.type === "css") {
          const link =
            document.createElement(
              "link"
            );

          link.rel = "stylesheet";
          link.href = asset.url;
          link.onload = resolve;
          link.onerror = () => reject(
            new Error(
              `Не удалось загрузить ${asset.url}`
            )
          );
          document.head.append(
            link
          );
          return;
        }

        if (asset.type === "js") {
          const script =
            document.createElement(
              "script"
            );

          script.src = asset.url;
          script.async = false;
          script.onload = resolve;
          script.onerror = () => reject(
            new Error(
              `Не удалось загрузить ${asset.url}`
            )
          );
          document.body.append(
            script
          );
          return;
        }

        resolve();
      }
    );
  };


  const buildNavigation = (
    modules
  ) => {
    moduleNav?.replaceChildren();
    navButtons = [];

    for (const meta of modules) {
      if (
        meta.enabled !== true
        || meta.page !== true
        || typeof renderers[meta.id] !== "function"
      ) {
        continue;
      }

      const button =
        el(
          "button",
          "nav-btn"
        );

      button.type = "button";
      button.dataset.page = meta.id;

      button.append(
        icon(meta.icon),
        el(
          "span",
          "",
          meta.name
        )
      );

      button.addEventListener(
        "click",
        () => openPage(
          meta.id
        )
      );

      moduleNav?.append(
        button
      );
      navButtons.push(
        button
      );
    }
  };


  window.Dashboard = Object.freeze({
    api,
    rpc: Object.freeze({
      read: rpcRead,
      action: actionApi
    }),
    ui: Object.freeze({
      root: main,
      el,
      icon,
      panel,
      statusNode,
      compactRow,
      appendAttention: appendAttentionItem,
      appendSummary: appendSummaryRow
    }),
    format: Object.freeze({
      bytes,
      duration,
      dateTime
    }),
    modules: Object.freeze({
      registerPage,
      registerPlacement,
      isEnabled: (id) =>
        moduleMetadata.get(id)?.enabled === true,
      meta: (id) =>
        moduleMetadata.get(id) || null,
      openPage
    })
  });


  refreshButton?.addEventListener(
    "click",
    () => {
      if (currentPage) {
        openPage(
          currentPage
        );
      }
    }
  );


  mobileMenu?.addEventListener(
    "click",
    () => {
      document.body.classList.toggle(
        "menu-open"
      );
    }
  );


  document.addEventListener(
    "visibilitychange",
    async () => {
      if (document.hidden) {
        stopOverviewLive();
        stopPagePolling();
        stopSchedulePolling();
        return;
      }

      if (
        currentPage === "overview"
      ) {
        updateUptime();

        if (
          uptimeTimer === null
        ) {
          uptimeTimer =
            window.setInterval(
              updateUptime,
              1000
            );
        }

        pollHost();
        return;
      }

      if (
        currentPage === "system"
      ) {
        if (systemScheduleEnabled) {
          pollSchedule();
        }
        return;
      }

      if (
        currentPage
        && liveTablePages.has(
          currentPage
        )
      ) {
        const page = currentPage;
        stopPagePolling();

        try {
          await renderers[page](
            true
          );
        } catch (error) {
          if (
            error?.message
            !== "unauthorized"
          ) {
            console.warn(
              "Visible page refresh failed",
              error
            );
          }
        }

        if (
          currentPage === page
        ) {
          schedulePagePoll();
        }
      }
    }
  );


  const bootstrapModules = async () => {
    const registry =
      await api(
        "/api/modules"
      );

    const modules =
      Array.isArray(
        registry.modules
      )
        ? registry.modules
        : [];

    extensionErrors =
      Array.isArray(
        registry.extension_errors
      )
        ? registry.extension_errors
        : [];

    for (const meta of modules) {
      if (
        meta
        && typeof meta.id === "string"
      ) {
        moduleMetadata.set(
          meta.id,
          meta
        );
      }
    }

    const serverName =
      typeof registry.server_name === "string"
      && registry.server_name
        ? registry.server_name
        : "Server";

    const productName =
      typeof registry.product_name === "string"
      && registry.product_name
        ? registry.product_name
        : "Dashboard";

    const title =
      typeof registry.title === "string"
      && registry.title
        ? registry.title
        : `${serverName} ${productName}`;

    document.title = title;

    const serverNameNode =
      document.getElementById(
        "dashboard-server-name"
      );

    const productNameNode =
      document.getElementById(
        "dashboard-product-name"
      );

    if (serverNameNode) {
      serverNameNode.textContent =
        serverName;
    }

    if (productNameNode) {
      productNameNode.textContent =
        productName;
    }

    const systemEnabled =
      moduleMetadata.get(
        "system"
      )?.enabled === true;

    if (rebootButton) {
      rebootButton.hidden =
        !systemEnabled;
    }

    if (shutdownButton) {
      shutdownButton.hidden =
        !systemEnabled;
    }

    const extensionModules =
      modules.filter(
        (meta) =>
          meta.enabled === true
          && meta.builtin === false
      );

    for (const meta of extensionModules) {
      const assets =
        Array.isArray(
          meta.assets
        )
          ? meta.assets
          : [];

      for (const asset of assets) {
        try {
          await loadAsset(
            asset
          );
        } catch (error) {
          console.warn(
            `Extension asset failed: ${meta.id}`,
            error
          );

          extensionErrors.push({
            id: meta.id,
            message:
              error?.message
              || "Не удалось загрузить frontend расширения"
          });
        }
      }
    }

    buildNavigation(
      modules
    );

    const requestedDefaultPage =
      typeof registry.default_page === "string"
        ? registry.default_page
        : null;

    const availablePages =
      modules.filter(
        (meta) =>
          meta?.enabled === true
          && meta?.page === true
          && typeof renderers[meta.id] === "function"
      );

    const defaultPage =
      requestedDefaultPage
      && typeof renderers[requestedDefaultPage] === "function"
        ? requestedDefaultPage
        : (availablePages[0]?.id || null);

    if (!defaultPage) {
      throw new Error(
        "Нет доступной стартовой страницы"
      );
    }

    await openPage(
      defaultPage
    );
  };


  bootstrapModules()
    .catch(
      (error) => {
        if (
          error?.message
          !== "unauthorized"
        ) {
          showError(error);
        }
      }
    );

})();

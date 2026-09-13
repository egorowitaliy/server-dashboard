(() => {
  "use strict";

  const Dashboard = window.Dashboard;

  Dashboard.modules.registerPlacement(
    "example-status",
    "system",
    async ({leftColumn}) => {
      const data = await Dashboard.rpc.read(
        "ext.example-status.state"
      );

      const card = Dashboard.ui.panel(
        "Пример состояния",
        "activity"
      );

      card.append(
        Dashboard.ui.compactRow(
          "activity",
          "Состояние",
          data.value,
          data.status
        )
      );

      leftColumn.append(card);
    }
  );
})();

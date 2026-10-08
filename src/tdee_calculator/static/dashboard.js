// Draws the weight chart from the server's JSON. No math or unit conversion here:
// the payload is already in display units, and all logic is tested in Python.
(() => {
  "use strict";

  const dataElement = document.getElementById("chart-data");
  const canvas = document.getElementById("weight-chart");
  if (!dataElement || !canvas || typeof Chart === "undefined") return;

  const data = JSON.parse(dataElement.textContent);
  const fallback = canvas.parentElement.querySelector(".chart-fallback");
  const darkMode = window.matchMedia("(prefers-color-scheme: dark)");
  const unit = data.unit;
  let chart = null;

  const token = (name) =>
    getComputedStyle(document.documentElement).getPropertyValue(name).trim();

  // Nearest date under the pointer, with every tooltip series at that date, so the
  // reader aims at a day rather than at a 2px line.
  Chart.Interaction.modes.nearestDate = (instance, event) => {
    const position = Chart.helpers.getRelativePosition(event, instance);
    const candidates = [];
    instance.data.datasets.forEach((dataset, datasetIndex) => {
      if (dataset.tooltipName === undefined || !instance.isDatasetVisible(datasetIndex)) {
        return;
      }
      instance.getDatasetMeta(datasetIndex).data.forEach((element, index) => {
        candidates.push({ element, datasetIndex, index });
      });
    });
    if (candidates.length === 0) return [];
    const distance = (item) => Math.abs(item.element.x - position.x);
    const nearest = candidates.reduce((best, item) =>
      distance(item) < distance(best) ? item : best,
    );
    return candidates.filter(
      (item) => Math.abs(item.element.x - nearest.element.x) < 0.5,
    );
  };

  function datasets(colors) {
    const sets = [
      {
        label: "Trend",
        tooltipName: "trend",
        data: data.trend,
        borderColor: colors.accent,
        backgroundColor: colors.accent,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
        order: 1,
      },
      {
        label: "Weigh-ins",
        tooltipName: "weigh-in",
        data: data.weighIns,
        showLine: false,
        backgroundColor: colors.muted,
        borderColor: colors.surface,
        pointRadius: 4,
        pointHoverRadius: 5,
        pointBorderWidth: 2,
        pointHitRadius: 12,
        order: 2,
      },
    ];
    if (data.projection.length > 0) {
      sets.push({
        label: "Projection",
        tooltipName: "projected",
        data: data.projection,
        borderColor: colors.accent,
        backgroundColor: colors.accent,
        borderWidth: 2,
        borderDash: [6, 4],
        pointRadius: 0,
        pointHoverRadius: 4,
        order: 0,
      });
    }
    if (data.goal !== null) {
      sets.push({
        label: `Goal ${data.goal.toFixed(1)} ${unit}`,
        data: [
          { x: data.start, y: data.goal },
          { x: data.end, y: data.goal },
        ],
        borderColor: colors.goal,
        backgroundColor: colors.goal,
        borderWidth: 1,
        pointRadius: 0,
        pointHoverRadius: 0,
        order: 3,
      });
    }
    return sets;
  }

  function draw() {
    const colors = {
      accent: token("--chart-accent"),
      muted: token("--chart-muted"),
      goal: token("--chart-goal"),
      grid: token("--chart-grid"),
      text: token("--chart-text"),
      surface: token("--surface"),
    };
    const axis = {
      grid: { color: colors.grid },
      border: { color: colors.grid },
      ticks: { color: colors.text },
    };
    chart?.destroy();
    chart = new Chart(canvas, {
      type: "line",
      data: { datasets: datasets(colors) },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearestDate", intersect: false },
        scales: {
          x: {
            ...axis,
            // Horizontal gridlines only: one per day would be noise.
            grid: { display: false },
            ticks: { ...axis.ticks, maxRotation: 0, autoSkipPadding: 24 },
            type: "time",
            min: data.start,
            max: data.end,
            time: {
              tooltipFormat: "EEE d MMM yyyy",
              displayFormats: { day: "d MMM", week: "d MMM", month: "MMM yyyy" },
            },
          },
          y: {
            ...axis,
            title: { display: true, text: `Weight (${unit})`, color: colors.text },
            ticks: { ...axis.ticks, maxTicksLimit: 6 },
          },
        },
        plugins: {
          legend: {
            labels: {
              // Reading order, not drawing order.
              sort: (a, b) => a.datasetIndex - b.datasetIndex,
              color: colors.text,
              usePointStyle: true,
              boxHeight: 10,
              // Line keys for lines, a dot for weigh-ins: the key mirrors the mark.
              generateLabels: (instance) =>
                Chart.defaults.plugins.legend.labels
                  .generateLabels(instance)
                  .map((item) => {
                    const dataset = instance.data.datasets[item.datasetIndex];
                    const isLine = dataset.showLine !== false;
                    return {
                      ...item,
                      pointStyle: isLine ? "line" : "circle",
                      lineWidth: isLine ? 2 : 0,
                      lineDash: dataset.borderDash ?? [],
                      fillStyle: dataset.backgroundColor,
                      strokeStyle: isLine ? dataset.borderColor : dataset.backgroundColor,
                    };
                  }),
            },
          },
          tooltip: {
            callbacks: {
              // Value first, then what it is: "79.8 kg weigh-in".
              label: (item) =>
                `${item.parsed.y.toFixed(1)} ${unit} ${item.dataset.tooltipName}`,
            },
          },
        },
      },
    });
    fallback?.remove();
  }

  draw();
  darkMode.addEventListener("change", draw);
})();

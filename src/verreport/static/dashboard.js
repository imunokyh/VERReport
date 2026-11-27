(function () {
  var el = document.getElementById("report-data");
  if (!el || typeof Chart === "undefined") return;
  var data = JSON.parse(el.textContent);
  var css = getComputedStyle(document.documentElement);
  var c = function (n) { return css.getPropertyValue(n).trim(); };

  Chart.defaults.color = c("--muted");
  Chart.defaults.borderColor = c("--line");
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  var base = { responsive: true, maintainAspectRatio: false };

  function canvas(id) { var e = document.getElementById(id); return e && e.getContext("2d"); }

  if (data.gtest && canvas("chart-gtest")) {
    var g = data.gtest;
    new Chart(canvas("chart-gtest"), {
      type: "doughnut",
      data: {
        labels: ["Passed", "Failed", "Skipped"],
        datasets: [{ data: [g.passed, g.failed, g.skipped],
          backgroundColor: [c("--pass"), c("--fail"), c("--skip")], borderWidth: 0 }]
      },
      options: Object.assign({}, base, { cutout: "62%", plugins: { legend: { position: "right" } } })
    });
  }

  if (data.coverage && canvas("chart-coverage")) {
    var cv = data.coverage;
    new Chart(canvas("chart-coverage"), {
      type: "bar",
      data: {
        labels: cv.labels,
        datasets: [{ label: "Coverage %", data: cv.values, borderRadius: 4,
          backgroundColor: cv.values.map(function (v) { return v >= cv.target ? c("--pass") : c("--warn"); }) }]
      },
      options: Object.assign({}, base, {
        scales: { y: { min: 0, max: 100, ticks: { callback: function (v) { return v + "%"; } } } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: function (x) { return x.parsed.y + "% (target " + cv.target + "%)"; } } }
        }
      })
    });
  }

  var sevColor = { error: "--fail", warning: "--warn", style: "--accent", performance: "--accent",
    portability: "--skip", information: "--skip" };
  if (data.cppcheck && canvas("chart-cppcheck")) {
    var cp = data.cppcheck;
    new Chart(canvas("chart-cppcheck"), {
      type: "bar",
      data: {
        labels: cp.labels,
        datasets: [{ data: cp.values, borderRadius: 4,
          backgroundColor: cp.labels.map(function (l) { return c(sevColor[l] || "--skip"); }) }]
      },
      options: Object.assign({}, base, {
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: { legend: { display: false } }
      })
    });
  }

  if (data.lizard && canvas("chart-lizard")) {
    var lz = data.lizard;
    new Chart(canvas("chart-lizard"), {
      type: "bar",
      data: {
        labels: lz.labels,
        datasets: [{ data: lz.values, borderRadius: 4,
          backgroundColor: lz.values.map(function (v) { return v > 0 ? c("--fail") : c("--pass"); }) }]
      },
      options: Object.assign({}, base, {
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: function (x) { return x.parsed.y + " of " + lz.total + " functions"; } } }
        }
      })
    });
  }
})();

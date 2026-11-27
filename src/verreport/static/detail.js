(function () {
  var $ = function (id) { return document.getElementById(id); };
  var q = $("q"), flag = $("flag"), count = $("count"), nomatch = $("nomatch");
  var tree = $("tree");
  if (!tree) return;

  var rows = Array.prototype.slice.call(tree.querySelectorAll("tr.row"));
  var files = Array.prototype.slice.call(tree.querySelectorAll("details.file"));
  var modules = Array.prototype.slice.call(tree.querySelectorAll("details.module"));

  function hasFlag(row, f) {
    return (" " + (row.dataset.flag || "") + " ").indexOf(" " + f + " ") >= 0;
  }

  function apply() {
    var term = q.value.trim().toLowerCase();
    var f = flag.value;
    var filtering = term !== "" || f !== "";
    var shown = 0;

    rows.forEach(function (r) {
      var ok = (!term || (r.dataset.text || "").indexOf(term) >= 0) && (!f || hasFlag(r, f));
      r.hidden = !ok;
      if (ok) shown++;
    });
    files.forEach(function (d) {
      var any = d.querySelector("tr.row:not([hidden])") !== null;
      d.hidden = !any;
      if (filtering && any) d.open = true;
    });
    modules.forEach(function (d) {
      var any = d.querySelector("details.file:not([hidden])") !== null;
      d.hidden = !any;
      if (filtering && any) d.open = true;
    });
    count.textContent = filtering ? shown + " / " + rows.length + " 건 표시" : rows.length + " 건";
    if (nomatch) nomatch.hidden = shown !== 0;
  }

  q.addEventListener("input", apply);
  flag.addEventListener("change", apply);
  $("expand").addEventListener("click", function () {
    tree.querySelectorAll("details").forEach(function (d) { d.open = true; });
  });
  $("collapse").addEventListener("click", function () {
    tree.querySelectorAll("details").forEach(function (d) { d.open = false; });
  });

  // Click-to-sort on table headers.
  tree.querySelectorAll("table.sortable").forEach(function (table) {
    var ths = table.querySelectorAll("th[data-sort]");
    ths.forEach(function (th) {
      th.addEventListener("click", function () {
        var idx = Array.prototype.indexOf.call(th.parentNode.children, th);
        var numeric = th.dataset.sort === "num";
        var dir = th.dataset.dir === "asc" ? "desc" : "asc";
        ths.forEach(function (o) { delete o.dataset.dir; });
        th.dataset.dir = dir;
        var tbody = table.tBodies[0];
        var list = Array.prototype.slice.call(tbody.rows);
        function val(r) {
          var c = r.cells[idx];
          var v = c.dataset.v !== undefined ? c.dataset.v : c.textContent.trim();
          return numeric ? parseFloat(v) || 0 : v.toLowerCase();
        }
        list.sort(function (a, b) {
          var x = val(a), y = val(b);
          var r = x < y ? -1 : x > y ? 1 : 0;
          return dir === "asc" ? r : -r;
        });
        list.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });

  apply();
})();

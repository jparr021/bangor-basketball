// Sortable tables and search filters. No dependencies.
(function () {
  function cellValue(td) {
    var t = (td.textContent || "").trim();
    var n = t.replace(/[,%]/g, "").replace(/–.*$/, "");
    if (/^-?\d+(\.\d+)?$/.test(n)) return parseFloat(n);
    return t.toLowerCase();
  }
  document.querySelectorAll("table.sortable").forEach(function (table) {
    var ths = table.querySelectorAll("thead th");
    ths.forEach(function (th, idx) {
      th.addEventListener("click", function () {
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        var asc = !th.classList.contains("desc") && th.classList.contains("asc") ? false : !th.classList.contains("asc");
        // numeric columns sort high-to-low first
        var sample = rows.length ? cellValue(rows[0].cells[idx]) : "";
        if (!th.classList.contains("asc") && !th.classList.contains("desc")) asc = typeof sample !== "number";
        ths.forEach(function (o) { o.classList.remove("asc", "desc"); });
        th.classList.add(asc ? "asc" : "desc");
        rows.sort(function (a, b) {
          var x = cellValue(a.cells[idx]), y = cellValue(b.cells[idx]);
          if (x === "" || x === "—") return 1;
          if (y === "" || y === "—") return -1;
          if (x < y) return asc ? -1 : 1;
          if (x > y) return asc ? 1 : -1;
          return 0;
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });
  document.querySelectorAll("input[data-filter]").forEach(function (input) {
    var table = document.querySelector(input.getAttribute("data-filter"));
    input.addEventListener("input", function () {
      var q = input.value.trim().toLowerCase();
      Array.prototype.forEach.call(table.tBodies[0].rows, function (r) {
        r.style.display = !q || r.textContent.toLowerCase().indexOf(q) !== -1 ? "" : "none";
      });
    });
  });
})();

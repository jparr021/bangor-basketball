// Menu, site search, sortable tables and table filters. No dependencies.
(function () {
  var body = document.body;
  var ROOT = body.getAttribute("data-root") || "";
  var CLEAN = body.getAttribute("data-clean") === "1";

  // Link to a page given its path from the site root ("players/x.html").
  function href(u) {
    if (!CLEAN) return ROOT + u;
    var parts = u.split("#"), p = parts[0].replace(/\.html$/, "");
    if (p === "index") p = "";
    p = p.replace(/\/index$/, "");
    return "/" + p + (parts[1] ? "#" + parts[1] : "");
  }

  // ------------------------------------------------------------ mobile menu
  var navToggle = document.querySelector(".nav-toggle");
  function setNav(open) {
    body.classList.toggle("nav-open", open);
    navToggle.setAttribute("aria-expanded", open ? "true" : "false");
  }
  if (navToggle) {
    navToggle.addEventListener("click", function () { setNav(!body.classList.contains("nav-open")); });
  }

  // ------------------------------------------------------------ site search
  var toggle = document.querySelector(".search-toggle");
  var panel = document.getElementById("site-search");
  var input = document.getElementById("site-search-input");
  var list = document.getElementById("site-search-results");
  var status = document.getElementById("site-search-status");
  var index = null, results = [], active = -1;

  function norm(s) {
    return (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
      .replace(/[’'.]/g, "").replace(/[–—]/g, "-").replace(/&/g, "and");
  }
  var KIND_WEIGHT = { player: 3, season: 2, opponent: 2, coach: 2, page: 1 };
  var KIND_LABEL = { player: "Player", season: "Season", opponent: "Opponent", coach: "Coach", page: "Page" };

  var waiting = null;  // callbacks queued while the index script is loading
  function loadIndex(cb) {
    if (index) return cb();
    if (window.BANGOR_SEARCH) { prepare(); return cb(); }
    if (waiting) { waiting.push(cb); return; }
    waiting = [cb];
    var s = document.createElement("script");
    s.src = (CLEAN ? "/" : ROOT) + "static/search-index.js?v=" + (body.getAttribute("data-v") || "");
    s.onload = function () { prepare(); var w = waiting; waiting = null; w.forEach(function (f) { f(); }); };
    s.onerror = function () { waiting = null; status.textContent = "Search couldn't load."; };
    document.head.appendChild(s);
  }
  function prepare() {
    index = (window.BANGOR_SEARCH || []).map(function (it) {
      var t = norm(it.t), split = function (s) { return s.split(/[\s\-\/(),!]+/).filter(Boolean); };
      var tw = split(t);
      return { it: it, t: t, words: tw.concat(split(norm(it.x))), nTitle: tw.length };
    });
  }
  function score(e, q, tokens) {
    var total = 0;
    for (var i = 0; i < tokens.length; i++) {
      var tok = tokens[i], best = 0;
      for (var j = 0; j < e.words.length; j++) {
        var w = e.words[j], inTitle = j < e.nTitle ? 1 : 0;  // words in the name count a little more
        if (w === tok) best = Math.max(best, 5 + inTitle);
        else if (w.indexOf(tok) === 0) best = Math.max(best, 2 + inTitle);
      }
      if (!best && tok.length > 2 && e.t.indexOf(tok) !== -1) best = 1;
      if (!best) return 0;
      total += best;
    }
    if (e.t === q) total += 10;
    else if (e.t.indexOf(q) === 0) total += 2;
    return total * 10 + KIND_WEIGHT[e.it.k];
  }
  function search(raw) {
    var q = norm(raw).trim();
    if (!q) return [];
    var tokens = q.split(/[\s\-]+/).filter(Boolean);
    var out = [];
    index.forEach(function (e) {
      var sc = score(e, q, tokens);
      if (sc) out.push({ e: e, sc: sc });
    });
    out.sort(function (a, b) { return b.sc - a.sc || a.e.it.t.localeCompare(b.e.it.t); });
    return out.slice(0, 10).map(function (r) { return r.e.it; });
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; });
  }
  function draw() {
    results = search(input.value);
    active = results.length ? 0 : -1;
    list.innerHTML = results.map(function (it, i) {
      return '<li role="option" id="sr-' + i + '" aria-selected="' + (i === active) + '">' +
        '<a href="' + esc(href(it.u)) + '" tabindex="-1"><span class="sr-kind">' + KIND_LABEL[it.k] + '</span>' +
        '<span class="sr-t">' + esc(it.t) + '</span><span class="sr-s">' + esc(it.s) + "</span></a></li>";
    }).join("");
    if (input.value.trim() && !results.length) list.innerHTML = '<li class="sr-none">No matches</li>';
    input.setAttribute("aria-expanded", results.length ? "true" : "false");
    setActive(active);
    status.textContent = input.value.trim() ? (results.length ? results.length + " results" : "No matches") : "";
  }
  function setActive(i) {
    active = i;
    Array.prototype.forEach.call(list.querySelectorAll('[role="option"]'), function (li, j) {
      li.setAttribute("aria-selected", j === i ? "true" : "false");
      if (j === i) li.scrollIntoView({ block: "nearest" });
    });
    if (i >= 0) input.setAttribute("aria-activedescendant", "sr-" + i);
    else input.removeAttribute("aria-activedescendant");
  }
  function openSearch() {
    panel.hidden = false;
    toggle.setAttribute("aria-expanded", "true");
    setNav(false);
    input.focus();
    loadIndex(function () { if (input.value) draw(); });
  }
  function closeSearch(returnFocus) {
    panel.hidden = true;
    toggle.setAttribute("aria-expanded", "false");
    if (returnFocus) toggle.focus();
  }
  if (toggle && panel) {
    toggle.addEventListener("click", function () { panel.hidden ? openSearch() : closeSearch(true); });
    input.addEventListener("input", function () { loadIndex(draw); });
    input.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" && results.length) { ev.preventDefault(); setActive((active + 1) % results.length); }
      else if (ev.key === "ArrowUp" && results.length) { ev.preventDefault(); setActive((active - 1 + results.length) % results.length); }
      else if (ev.key === "Enter" && active >= 0) { ev.preventDefault(); window.location.href = href(results[active].u); }
      else if (ev.key === "Escape") { ev.preventDefault(); closeSearch(true); }
    });
    list.addEventListener("mousemove", function (ev) {
      var li = ev.target.closest('[role="option"]');
      if (li) setActive(parseInt(li.id.slice(3), 10));
    });
    document.addEventListener("click", function (ev) {
      if (!panel.hidden && !panel.contains(ev.target) && !toggle.contains(ev.target)) closeSearch(false);
    });
  }

  document.addEventListener("keydown", function (ev) {
    var tag = (ev.target.tagName || "").toLowerCase();
    var typing = tag === "input" || tag === "textarea" || tag === "select" || ev.target.isContentEditable;
    if (ev.key === "/" && !typing && toggle && !ev.metaKey && !ev.ctrlKey) { ev.preventDefault(); openSearch(); }
    if (ev.key === "Escape" && body.classList.contains("nav-open")) { setNav(false); navToggle.focus(); }
  });

  // ------------------------------------------------------------ sortable tables
  function cellValue(td) {
    var t = (td.textContent || "").trim();
    var n = t.replace(/[,%]/g, "").replace(/–.*$/, "");
    if (/^-?\d+(\.\d+)?$/.test(n)) return parseFloat(n);
    return t.toLowerCase();
  }
  document.querySelectorAll("table.sortable").forEach(function (table) {
    var ths = table.querySelectorAll("thead th");
    ths.forEach(function (th, idx) {
      if (!th.textContent.trim()) return;
      // a real button inside each header, so sorting works from the keyboard and is announced
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "th-sort";
      while (th.firstChild) btn.appendChild(th.firstChild);
      th.appendChild(btn);
      btn.setAttribute("aria-label", "Sort by " + btn.textContent.trim());
      btn.addEventListener("click", function () {
        var tbody = table.tBodies[0];
        var rows = Array.prototype.slice.call(tbody.rows);
        var asc;
        if (th.classList.contains("asc")) asc = false;
        else if (th.classList.contains("desc")) asc = true;
        else asc = typeof (rows.length ? cellValue(rows[0].cells[idx]) : "") !== "number"; // numbers sort high-to-low first
        ths.forEach(function (o) { o.classList.remove("asc", "desc"); o.removeAttribute("aria-sort"); });
        th.classList.add(asc ? "asc" : "desc");
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
        rows.sort(function (a, b) {
          var x = cellValue(a.cells[idx]), y = cellValue(b.cells[idx]);
          if (x === "" || x === "—") return 1;
          if (y === "" || y === "—") return -1;
          if (x < y) return asc ? -1 : 1;
          if (x > y) return asc ? 1 : -1;
          return 0;
        });
        rows.forEach(function (r) { tbody.appendChild(r); });
      });
    });
  });

  // ------------------------------------------------------------ table filters
  document.querySelectorAll("input[data-filter]").forEach(function (box) {
    var table = document.querySelector(box.getAttribute("data-filter"));
    var live = document.createElement("p");
    live.className = "sr-only";
    live.setAttribute("aria-live", "polite");
    box.parentNode.insertBefore(live, box.nextSibling);
    var timer;
    box.addEventListener("input", function () {
      var q = box.value.trim().toLowerCase(), shown = 0;
      Array.prototype.forEach.call(table.tBodies[0].rows, function (r) {
        var on = !q || r.textContent.toLowerCase().indexOf(q) !== -1;
        r.style.display = on ? "" : "none";
        if (on) shown++;
      });
      clearTimeout(timer);
      timer = setTimeout(function () { live.textContent = q ? shown + " shown" : ""; }, 400);
    });
  });
})();

// Career leaders: show one stat's list at a time (all lists show without JavaScript)
(function () {
  var tabs = document.querySelectorAll(".leader-tabs a[data-board]");
  if (!tabs.length) return;
  var boards = document.querySelectorAll(".leader-board");
  function show(stat, scroll) {
    var found = false;
    boards.forEach(function (b) { var on = b.id === stat; b.classList.toggle("hidden", !on); found = found || on; });
    if (!found) return show(boards[0].id, false);
    tabs.forEach(function (t) {
      var on = t.getAttribute("data-board") === stat;
      t.classList.toggle("on", on);
      if (on) t.setAttribute("aria-current", "true"); else t.removeAttribute("aria-current");
    });
    if (scroll === false) window.scrollTo(0, 0);
  }
  tabs.forEach(function (t) {
    t.addEventListener("click", function (ev) {
      ev.preventDefault();
      var stat = t.getAttribute("data-board");
      history.replaceState(null, "", "#" + stat);
      show(stat, true);
    });
  });
  show((location.hash || "#" + boards[0].id).slice(1), false);
  var box = document.querySelector("[data-leader-filter]");
  if (box) box.addEventListener("input", function () {
    var q = box.value.trim().toLowerCase();
    document.querySelectorAll(".leader-table tbody tr").forEach(function (r) {
      r.style.display = !q || r.cells[1].textContent.toLowerCase().indexOf(q) !== -1 ? "" : "none";
    });
  });
})();

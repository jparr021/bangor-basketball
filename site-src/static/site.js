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

  // ------------------------------------------------------------ "Add to calendar": copy link, close on outside click
  Array.prototype.forEach.call(document.querySelectorAll("[data-copy]"), function (b) {
    b.addEventListener("click", function () {
      var text = b.getAttribute("data-copy"), label = b.textContent;
      var done = function () { b.textContent = "Copied!"; setTimeout(function () { b.textContent = label; }, 1800); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, function () { window.prompt("Calendar link:", text); });
      else window.prompt("Calendar link:", text);
    });
  });
  document.addEventListener("click", function (ev) {
    Array.prototype.forEach.call(document.querySelectorAll("details.cal-menu[open]"), function (d) {
      if (!d.contains(ev.target)) d.open = false;
    });
  });

  // ------------------------------------------------------------ 404 page: "Were you looking for…"
  Array.prototype.forEach.call(document.querySelectorAll("[data-open-search]"), function (b) {
    b.addEventListener("click", function (ev) { ev.stopPropagation(); if (toggle && panel) openSearch(); });
  });
  var nfPath = document.getElementById("nf-path");
  if (nfPath) {
    var path = decodeURIComponent(window.location.pathname);
    nfPath.textContent = path;
    // the words in the address: "/players/hayden-masman.html" -> "hayden masman"
    var words = path.split("/").filter(Boolean).pop() || "";
    words = words.replace(/\.html?$/i, "").replace(/[-_+.]+/g, " ").trim();
    var guess = function (q) {
      var r = search(q);
      if (!r.length) {  // a typo: try each word alone and keep the best few
        q.split(" ").filter(function (w) { return w.length > 2; }).forEach(function (w) { r = r.concat(search(w)); });
        var seen = {};
        r = r.filter(function (it) { return seen[it.u] ? false : (seen[it.u] = true); });
      }
      return r.slice(0, 5);
    };
    if (words && !/^(index|players|seasons|games|opponents|coaches|records|history|film)$/i.test(words)) {
      loadIndex(function () {
        var r = guess(words);
        if (!r.length) return;
        document.getElementById("nf-list").innerHTML = r.map(function (it) {
          return '<li><a href="' + esc(href(it.u)) + '"><span class="sr-kind">' + KIND_LABEL[it.k] + '</span>' +
            '<span class="sr-t">' + esc(it.t) + '</span><span class="sr-s">' + esc(it.s) + "</span></a></li>";
        }).join("");
        document.getElementById("nf-guess").hidden = false;
      });
    }
  }

  document.addEventListener("keydown", function (ev) {
    var tag = (ev.target.tagName || "").toLowerCase();
    var typing = tag === "input" || tag === "textarea" || tag === "select" || ev.target.isContentEditable;
    if (ev.key === "/" && !typing && toggle && !ev.metaKey && !ev.ctrlKey) { ev.preventDefault(); openSearch(); }
    if (ev.key === "Escape" && body.classList.contains("nav-open")) { setNav(false); navToggle.focus(); }
  });

  // ------------------------------------------------------------ sortable tables
  function cellValue(td) {
    var ds = td.getAttribute("data-sort");
    if (ds !== null) return ds === "" ? "" : (/^-?\d+(\.\d+)?$/.test(ds) ? parseFloat(ds) : ds);
    var t = (td.textContent || "").trim();
    var n = t.replace(/[,%+]/g, "").replace(/–.*$/, "");
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
        else {
          var first = rows.length ? cellValue(rows[0].cells[idx]) : "";
          // numbers and dates sort high-to-low (newest) first, text A-to-Z
          asc = typeof first !== "number" && !/^\d{4}-\d{2}-\d{2}$/.test(first);
        }
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
  // rank by career total or per game (remembered for this visit)
  var rankBy = document.querySelector(".rank-by");
  if (rankBy) {
    var segs = rankBy.querySelectorAll("[data-rank]");
    var setRank = function (mode) {
      document.body.classList.toggle("rank-pg", mode === "pg");
      segs.forEach(function (b) {
        var on = b.getAttribute("data-rank") === mode;
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
      });
      try { sessionStorage.setItem("bangor-rank", mode); } catch (e) { /* private mode */ }
    };
    segs.forEach(function (b) { b.addEventListener("click", function () { setRank(b.getAttribute("data-rank")); }); });
    rankBy.hidden = false;
    document.body.classList.add("rank-ready");
    var saved = null;
    try { saved = sessionStorage.getItem("bangor-rank"); } catch (e) { /* private mode */ }
    setRank(saved === "pg" ? "pg" : "total");
  }
  var box = document.querySelector("[data-leader-filter]");
  if (box) box.addEventListener("input", function () {
    var q = box.value.trim().toLowerCase();
    document.querySelectorAll(".leader-table tbody tr").forEach(function (r) {
      r.style.display = !q || r.cells[1].textContent.toLowerCase().indexOf(q) !== -1 ? "" : "none";
    });
  });
})();

// Chart tooltips: any chart mark with data-tip shows it on hover and keyboard focus
(function () {
  if (!document.querySelector("[data-tip]")) return;
  var tip = document.createElement("div");
  tip.className = "chart-tip";
  tip.setAttribute("role", "tooltip");
  tip.hidden = true;
  document.body.appendChild(tip);
  var cur = null;
  function show(el, x, y) {
    if (el !== cur) {
      cur = el;
      tip.textContent = "";
      (el.getAttribute("data-tip") || "").split("\n").forEach(function (line, i) {
        var d = document.createElement(i ? "div" : "strong");
        d.textContent = line;
        tip.appendChild(d);
      });
    }
    tip.hidden = false;
    var r = tip.getBoundingClientRect(), pad = 12;
    var left = Math.min(Math.max(8, x - r.width / 2), window.innerWidth - r.width - 8);
    var top = y - r.height - pad;
    if (top < 8) top = y + pad + 8;
    tip.style.left = left + "px";
    tip.style.top = top + "px";
  }
  function hide() { tip.hidden = true; if (cur) cur.classList.remove("on"); cur = null; }
  document.addEventListener("pointermove", function (ev) {
    var el = ev.target.closest && ev.target.closest("[data-tip]");
    if (!el) { if (cur) hide(); return; }
    if (cur && cur !== el) cur.classList.remove("on");
    el.classList.add("on");
    show(el, ev.clientX, ev.clientY);
  });
  document.addEventListener("focusin", function (ev) {
    var el = ev.target.closest && ev.target.closest("[data-tip]");
    if (!el) return;
    el.classList.add("on");
    var r = el.getBoundingClientRect();
    show(el, r.left + r.width / 2, r.top);
  });
  document.addEventListener("focusout", hide);
  window.addEventListener("scroll", function () { if (cur) hide(); }, { passive: true });
})();

// Print buttons (shown only when JavaScript can run them)
document.querySelectorAll("[data-print]").forEach(function (b) {
  b.hidden = false;
  b.addEventListener("click", function () { window.print(); });
});

// Game-day labels. Pages are rebuilt every few hours, so an unplayed game's label is corrected to the
// visitor's moment (Wisconsin time) when the page opens: "Today", "Live now", then "Score coming soon"
// until the next rebuild brings the final. Without JavaScript the labels from the last build stay.
(function () {
  var els = document.querySelectorAll("[data-gdate]");
  if (!els.length) return;
  var LIVE_BEFORE = 15, GAME_LENGTH = 135, LATE = 22 * 60 + 30; // minutes
  function now() {
    try {
      var o = {};
      new Intl.DateTimeFormat("en-US", { timeZone: "America/Chicago", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).formatToParts(new Date())
        .forEach(function (p) { o[p.type] = p.value; });
      return { date: o.year + "-" + o.month + "-" + o.day, min: (+o.hour % 24) * 60 + (+o.minute) };
    } catch (e) { return null; }
  }
  // Start time in minutes after midnight, from "7:15", "7:15 PM", "5:45/7:15 pm" (varsity is the last time).
  function start(t) {
    var re = /(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\b/gi, m, last = null;
    while ((m = re.exec(t || ""))) if (+m[1] >= 1 && +m[1] <= 12) last = m;
    if (!last) return null;
    var h = +last[1], ap = (last[3] || "").toLowerCase();
    if (ap === "p" && h < 12) h += 12;
    else if (ap === "a" && h === 12) h = 0;
    else if (!ap && h < 10) h += 12; // no AM/PM: evening, except 10-12 (Saturday tournaments)
    return h * 60 + (+last[2] || 0);
  }
  var n = now();
  if (!n) return;
  function state(el) {
    var d = el.getAttribute("data-gdate");
    if (d > n.date) return "future";
    if (d < n.date) return "done";
    var s = start(el.getAttribute("data-gtime"));
    if (s === null) return n.min < LATE ? "today" : "done";
    if (n.min < s - LIVE_BEFORE) return "today";
    return n.min < s + GAME_LENGTH ? "live" : "done";
  }
  function label(st, time) {
    if (st === "live") return "Live now";
    if (st === "done") return "Score coming soon";
    return "Today" + (time ? " · " + time : "");
  }
  els.forEach(function (el) {
    var st = state(el), kind = el.getAttribute("data-gkind"), time = el.getAttribute("data-gtime");
    if (st === "future") { if (kind === "banner") el.hidden = true; return; }
    if (kind === "label") {
      el.textContent = label(st, time);
      el.classList.toggle("is-live", st === "live");
      el.classList.toggle("pending", st === "done");
    } else if (kind === "board") {
      el.textContent = "";
      if (st === "done") {
        el.className = "pending";
        el.appendChild(document.createTextNode("Score"));
        el.appendChild(document.createElement("br"));
        var sm = document.createElement("small"); sm.textContent = "coming soon"; el.appendChild(sm);
      } else {
        el.appendChild(document.createTextNode(st === "live" ? "LIVE NOW" : "TODAY"));
        if (time) {
          el.appendChild(document.createElement("br"));
          var t = document.createElement("small"); t.textContent = time; el.appendChild(t);
        }
      }
    } else if (kind === "row") {
      if (st === "done") el.hidden = true; else el.classList.add("today");
    } else if (kind === "banner") {
      el.hidden = false;
    } else if (kind === "live" && st === "done") {
      if (el.getAttribute("data-replay") === "1") { el.textContent = "▶ Watch replay"; el.classList.remove("live"); }
      else el.hidden = true;
    }
  });
  // the home page's upcoming-games card goes away once every game in it has been played
  document.querySelectorAll("[data-gcard]").forEach(function (c) {
    var rows = c.querySelectorAll(".up");
    if (rows.length && Array.prototype.every.call(rows, function (r) { return r.hidden; })) c.hidden = true;
  });
})();

// ------------------------------------------------------------ "On this day" (home page)
// The build writes every dated game and record-book night to static/on-this-day.js, keyed by "MM-DD".
// The card picks today's date in Wisconsin time; with nothing on today it shows this week, and with
// nothing this week (the off-season) a few big nights from the archives, the same ones all day.
(function () {
  var card = document.querySelector("[data-otd]");
  if (!card) return;
  var body = document.body, ROOT = body.getAttribute("data-root") || "", CLEAN = body.getAttribute("data-clean") === "1";
  var MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  function href(u) {
    if (!CLEAN) return ROOT + u;
    var parts = u.split("#"), p = parts[0].replace(/\.html$/, "").replace(/\/index$/, "");
    return "/" + p + (parts[1] ? "#" + parts[1] : "");
  }
  function today() {  // {y, m, d} in Wisconsin time
    var o = {};
    try {
      new Intl.DateTimeFormat("en-US", { timeZone: "America/Chicago", year: "numeric", month: "numeric", day: "numeric" })
        .formatToParts(new Date()).forEach(function (p) { o[p.type] = +p.value; });
    } catch (e) { var n = new Date(); o = { year: n.getFullYear(), month: n.getMonth() + 1, day: n.getDate() }; }
    return { y: o.year, m: o.month, d: o.day };
  }
  function key(m, d) { return (m < 10 ? "0" : "") + m + "-" + (d < 10 ? "0" : "") + d; }
  function pick(items, n) {  // the heaviest items, one per year
    var out = [], years = {};
    items.forEach(function (it) { if (out.length < n && !years[it.year]) { years[it.year] = 1; out.push(it); } });
    return out;
  }
  function render() {
    var data = window.BANGOR_OTD || {}, t = today(), shown = [], title = "", mode = "";
    function items(m, d) {
      return (data[key(m, d)] || []).map(function (r) { return { year: r[0], w: r[1], text: r[2], url: r[3], m: m, d: d }; })
        .filter(function (it) { return it.year < t.y || (it.m !== t.m || it.d !== t.d); });
    }
    shown = pick(items(t.m, t.d), 3);
    if (shown.length) { mode = "today"; title = "On this day · " + MONTHS[t.m - 1] + " " + t.d; }
    if (!shown.length) {
      var week = [];
      [-1, 1, -2, 2, -3, 3].forEach(function (off) {
        var dt = new Date(Date.UTC(t.y, t.m - 1, t.d + off));
        week = week.concat(items(dt.getUTCMonth() + 1, dt.getUTCDate()));
      });
      week.sort(function (a, b) { return b.w - a.w || b.year - a.year; });
      shown = pick(week, 3);
      if (shown.length) { mode = "week"; title = "This week in Bangor history"; }
    }
    if (!shown.length) {  // the off-season: a few big nights, the same ones all day
      var big = [];
      Object.keys(data).sort().forEach(function (k) {
        var p = k.split("-");
        data[k].forEach(function (r) { if (r[1] >= 7) big.push({ year: r[0], w: r[1], text: r[2], url: r[3], m: +p[0], d: +p[1] }); });
      });
      var seed = t.y * 372 + t.m * 31 + t.d;
      big.sort(function (a, b) { return ((a.year * 7919 + a.m * 131 + a.d * 17 + seed) % 997) - ((b.year * 7919 + b.m * 131 + b.d * 17 + seed) % 997); });
      shown = pick(big, 3);
      mode = "archive"; title = "From the archives";
    }
    if (!shown.length) return;
    card.querySelector("[data-otd-title]").textContent = title;
    var list = card.querySelector("[data-otd-list]");
    shown.forEach(function (it) {
      var li = document.createElement("li"), a = document.createElement("a");
      a.href = href(it.url);
      var when = document.createElement("span"); when.className = "otd-when";
      var ago = t.y - it.year - ((it.m > t.m || (it.m === t.m && it.d > t.d)) ? 1 : 0);
      when.textContent = mode === "today" ? it.year + " · " + (ago === 1 ? "1 year ago" : ago + " years ago")
                                          : MONTHS[it.m - 1].slice(0, 3) + " " + it.d + ", " + it.year;
      var text = document.createElement("span"); text.className = "otd-text"; text.textContent = it.text;
      a.appendChild(when); a.appendChild(text); li.appendChild(a); list.appendChild(li);
    });
    card.hidden = false;
  }
  if (window.BANGOR_OTD) return render();
  var s = document.createElement("script");
  s.src = (CLEAN ? "/" : ROOT) + "static/on-this-day.js?v=" + (body.getAttribute("data-v") || "");
  s.onload = render;
  document.head.appendChild(s);
})();

// Pre-season countdown on the home page ("Tipoff in 25 days"), counted from today in Wisconsin time so it
// stays right between rebuilds.
(function () {
  var el = document.querySelector("[data-tipoff]");
  if (!el) return;
  var o = {};
  try {
    new Intl.DateTimeFormat("en-US", { timeZone: "America/Chicago", year: "numeric", month: "numeric", day: "numeric" })
      .formatToParts(new Date()).forEach(function (p) { o[p.type] = +p.value; });
  } catch (e) { return; }
  var t = el.dataset.tipoff.split("-");
  var days = Math.round((Date.UTC(+t[0], +t[1] - 1, +t[2]) - Date.UTC(o.year, o.month - 1, o.day)) / 864e5);
  el.textContent = days > 1 ? "Tipoff in " + days + " days" : days === 1 ? "Tipoff tomorrow"
    : days === 0 ? (el.dataset.tipoffTime ? "Tipoff tonight" : "Tipoff today") : "Season under way";
})();

// Edit buttons for an admin signed in on this device (static/admin-edit.js). The admin page saves the device key;
// without it nothing more is loaded, so visitors never download the editing code.
(function () {
  var me = document.currentScript && document.currentScript.src;
  var on = false;
  try { on = !!localStorage.getItem("bbAdminToken"); } catch (e) { return; }
  if (!on || !me || document.querySelector(".admin")) return; // the admin page has its own tools
  var s = document.createElement("script");
  s.src = me.replace(/site\.js(\?.*)?$/, "admin-edit.js$1");
  document.body.appendChild(s);
})();

// Edit buttons on the site's own pages, for an admin signed in on this device (see the README's "Admin page").
// site.js loads this file only when the device has an admin sign-in key (saved by the admin page), so visitors
// never download it. It talks to the same server side as the admin page (api/admin.js): each change is one commit,
// shows in the admin page's Recent changes with Undo, and is on the site after the next rebuild.
//
// What a page can edit comes from its <body data-edit='{...}'>, written by the build:
//   season  {kind, season, stats, current}  team photo, the season line (record, coach, highlights), roster
//   player  {kind, name, slug, plain}       headshot, class year
//   game    {kind, date, opponent, season}  news stories, videos, photo galleries, YouTube film, Hudl links
(function () {
  "use strict";
  var KEY = "bbAdminToken", API = "/api/admin";
  var body = document.body, ROOT = body.getAttribute("data-root") || "", CLEAN = body.getAttribute("data-clean") === "1";
  var token = "";
  try { token = localStorage.getItem(KEY) || ""; } catch (e) { return; }
  if (!token) return;
  var ctx = {};
  try { ctx = JSON.parse(body.getAttribute("data-edit") || "{}"); } catch (e) { ctx = {}; }
  var ADMIN = CLEAN ? "/admin" : ROOT + "admin/index.html";

  // ------------------------------------------------------------ helpers
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function dash(s) { return String(s).replace("-", "–"); }
  function fmtDate(d) { return d ? new Date(d + "T12:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : ""; }
  function msg(m, text, ok) { m.textContent = text; m.className = "admin-msg" + (ok === true ? " ok" : ok === false ? " bad" : ""); }
  function saved(m) {
    msg(m, "Saved. It will be on the page in about 2–3 minutes. ", true);
    var a = el("a", "", "Undo"); a.href = ADMIN + "#log"; m.appendChild(a);
  }
  function call(b) {
    return fetch(API, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Token": token }, body: JSON.stringify(b) })
      .then(function (r) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          if (r.status === 401) signOut();
          if (!r.ok) {
            var e = new Error(j.error || (r.status === 404 ? "Saving only works on the live site." : "Something went wrong (" + r.status + ")."));
            e.status = r.status; throw e;
          }
          return j;
        });
      });
  }
  function signOut() {
    try { localStorage.removeItem(KEY); } catch (e) { /* private mode */ }
    var b = document.querySelector(".ae-bar"), p = document.querySelector(".ae-panel");
    if (b) b.remove(); if (p) p.remove();
    Array.prototype.forEach.call(document.querySelectorAll(".ae-add"), function (x) { x.remove(); });
  }
  // a labelled field; returns the input
  function field(form, label, tag, attrs, hint) {
    var l = el("label", "", label);
    if (hint) { l.appendChild(document.createTextNode(" ")); l.appendChild(el("span", "muted small", hint)); }
    var i = el(tag);
    Object.keys(attrs || {}).forEach(function (k) { i.setAttribute(k, attrs[k]); });
    l.appendChild(i); form.appendChild(l);
    return i;
  }
  function select(form, label, items) {
    var s = field(form, label, "select");
    items.forEach(function (it) { var o = el("option", "", it[1]); o.value = it[0]; s.appendChild(o); });
    return s;
  }
  function button(parent, label, cls, fn) {
    var b = el("button", cls || "btn btn-solid", label); b.type = cls ? "button" : "submit";
    if (fn) b.addEventListener("click", fn);
    parent.appendChild(b); return b;
  }
  // a list line with buttons
  function rowItem(title, sub, buttons) {
    var li = el("li"), info = el("div");
    info.appendChild(el("strong", "", title));
    if (sub) info.appendChild(el("span", "muted small", sub));
    li.appendChild(info);
    var bx = el("span", "admin-btns");
    buttons.forEach(function (b) { button(bx, b.label, "link-btn" + (b.danger ? " danger" : ""), function () { b.fn(this); }); });
    li.appendChild(bx);
    return li;
  }
  function removeBtn(table, row, what, after, m) {
    return { label: "Remove", danger: true, fn: function (x) {
      if (!confirm("Remove " + what + "?")) return;
      x.disabled = true; x.textContent = "Removing…";
      call({ action: "save", table: table, before: row, after: null }).then(function () { saved(m); after(); })
        .catch(function (err) { msg(m, err.message, false); x.disabled = false; x.textContent = "Remove"; });
    } };
  }

  // ------------------------------------------------------------ the panel
  var panel, sections = {};
  function section(id, title, intro) {
    var s = el("section", "ae-sec"); s.id = "ae-" + id;
    s.appendChild(el("h3", "", title));
    if (intro) s.appendChild(el("p", "muted small", intro));
    panel.querySelector(".ae-body").appendChild(s);
    sections[id] = s;
    return s;
  }
  function openPanel(focus) {
    if (!panel) build();
    panel.hidden = false;
    body.classList.add("ae-open");
    var s = focus && sections[focus];
    if (s) { s.scrollIntoView({ block: "start" }); var i = s.querySelector("input, textarea, select"); if (i) i.focus({ preventScroll: true }); }
    else panel.querySelector(".ae-close").focus();
  }
  function closePanel() { if (panel) panel.hidden = true; body.classList.remove("ae-open"); }
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && panel && !panel.hidden) closePanel(); });

  function build() {
    panel = el("aside", "ae-panel");
    panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Edit this page");
    var head = el("div", "ae-head");
    head.appendChild(el("strong", "", ctx.kind === "season" ? "Edit the " + dash(ctx.season) + " season"
      : ctx.kind === "player" ? "Edit " + ctx.name : ctx.kind === "game" ? "Edit this game" : "Admin"));
    var x = button(head, "×", "ae-close", closePanel); x.setAttribute("aria-label", "Close");
    panel.appendChild(head);
    panel.appendChild(el("div", "ae-body"));
    if (ctx.kind === "season") { photoSection("team"); seasonSection(); if (!ctx.stats) rosterSection(); }
    else if (ctx.kind === "player") { photoSection("player"); gradSection(); }
    else if (ctx.kind === "game") { linksSection(); }
    var foot = el("p", "muted small ae-foot");
    foot.appendChild(document.createTextNode("Scores and stats come from the season's Google Sheet. Everything else, and Undo, is on the "));
    var a = el("a", "", "admin page"); a.href = ADMIN; foot.appendChild(a); foot.appendChild(document.createTextNode("."));
    panel.querySelector(".ae-body").appendChild(foot);
    body.appendChild(panel);
  }

  // ------------------------------------------------------------ photos (team photo or headshot)
  function photoSection(kind) {
    var team = kind === "team";
    var s = section("photo", team ? "Add a team photo" : "Add a headshot",
      team ? "A season can have more than one team photo." : "A new headshot replaces the one on the page.");
    var f = el("form", "admin-form"), photo = null;
    if (!team && !ctx.plain) {
      s.appendChild(el("p", "admin-msg bad", "This page is one of two players with the same name, so a headshot added here would go to the other page. Add it by hand instead (see the README's Photos)."));
      return;
    }
    var file = field(f, "Photo", "input", { type: "file", accept: "image/*", required: "" });
    var prev = el("div", "admin-preview"); prev.hidden = true;
    var img = el("img"); img.alt = "Preview of the photo"; var size = el("span", "muted small");
    prev.appendChild(img); prev.appendChild(size); f.appendChild(prev);
    var cap = field(f, "Caption", "textarea", { rows: "2", maxlength: "300" }, team ? "(optional, e.g. names left to right)" : "(optional)");
    var cred = field(f, "Photo credit", "input", { maxlength: "120" }, "(optional, e.g. 1926 Echo yearbook)");
    f.appendChild(el("p", "muted small", "Only add photos you have permission to share: your own, the school's, or with the photographer's OK."));
    var go = button(f, "Publish"), m = el("p", "admin-msg"); m.setAttribute("role", "status"); f.appendChild(m);
    // shrink in the browser (team photos 1600 px wide, headshots 800 px), as the admin page does
    file.addEventListener("change", function () {
      var fl = file.files[0]; if (!fl) return;
      photo = null; prev.hidden = true; msg(m, "Reading the photo…");
      var im = new Image(), url = URL.createObjectURL(fl);
      im.onload = function () {
        var k = team ? Math.min(1, 1600 / im.naturalWidth) : Math.min(1, 800 / Math.max(im.naturalWidth, im.naturalHeight));
        var c = document.createElement("canvas");
        c.width = Math.round(im.naturalWidth * k); c.height = Math.round(im.naturalHeight * k);
        c.getContext("2d").drawImage(im, 0, 0, c.width, c.height);
        var data = c.toDataURL("image/jpeg", 0.86);
        photo = data.split(",")[1]; img.src = data;
        size.textContent = c.width + " × " + c.height + " px · " + Math.round(photo.length * 0.75 / 1024) + " KB";
        prev.hidden = false; msg(m, ""); URL.revokeObjectURL(url);
      };
      im.onerror = function () { msg(m, "This browser can't open that file. Save it as a JPEG or PNG and try again.", false); };
      im.src = url;
    });
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!photo) { msg(m, "Choose a photo first.", false); return; }
      go.disabled = true; msg(m, "Publishing…");
      call({ action: "add", kind: kind, season: team ? ctx.season : "", player: team ? "" : ctx.name,
             caption: cap.value, credit: cred.value, image: photo })
        .then(function () { saved(m); f.reset(); photo = null; prev.hidden = true; })
        .catch(function (err) { msg(m, err.message, false); })
        .then(function () { go.disabled = false; });
    });
    s.appendChild(f);
  }

  // ------------------------------------------------------------ season line
  function seasonSection() {
    var s = section("season", "Record, coach and highlights",
      ctx.current ? "This season's record is counted from the games on its Google Sheet, so only the coach and highlights matter until it ends." : "");
    var f = el("form", "admin-form"), row = null;
    var r3 = el("div", "admin-row3"); f.appendChild(r3);
    var w = field(r3, "Wins", "input", { inputmode: "numeric", maxlength: "3" });
    var l = field(r3, "Losses", "input", { inputmode: "numeric", maxlength: "3" });
    var t = field(r3, "Ties", "input", { inputmode: "numeric", maxlength: "3" });
    var coach = field(f, "Coach", "input", { maxlength: "80" });
    var notes = field(f, "Highlights", "textarea", { rows: "3", maxlength: "500" }, "(e.g. Scenic Bluffs Conference champions)");
    var go = button(f, "Save"), m = el("p", "admin-msg"); f.appendChild(m);
    var F = { w: w, l: l, t: t, coach: coach, notes: notes };
    go.disabled = true; msg(m, "Loading…");
    call({ action: "rows", table: "season", where: { season: ctx.season } }).then(function (j) {
      row = j.rows[0] || null;
      Object.keys(F).forEach(function (k) { F[k].value = row ? row[k] || "" : ""; });
      msg(m, row ? "" : "No line for " + dash(ctx.season) + " yet. Saving adds one.");
      go.disabled = false;
    }).catch(function (err) { msg(m, err.message, false); });
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var after = { season: ctx.season };
      Object.keys(F).forEach(function (k) { after[k] = F[k].value.trim(); });
      go.disabled = true; msg(m, "Saving…");
      call({ action: "save", table: "season", before: row, after: after })
        .then(function (j) { row = j.row; saved(m); })
        .catch(function (err) { msg(m, err.message, false); })
        .then(function () { go.disabled = false; });
    });
    s.appendChild(f);
  }

  // ------------------------------------------------------------ roster (seasons without stat sheets)
  function rosterSection() {
    var s = section("roster", "Roster", "From game programs and yearbooks. Each player listed gets a page.");
    var ul = el("ul", "admin-list admin-rows"); s.appendChild(ul);
    var f = el("form", "admin-form"), editing = null;
    var title = el("h4", "", "Add a player"); f.appendChild(title);
    var r2 = el("div", "admin-row2"); f.appendChild(r2);
    var F = { name: field(r2, "Name", "input", { required: "", maxlength: "80", autocomplete: "off" }),
              number: field(r2, "Number", "input", { maxlength: "6", inputmode: "numeric" }) };
    var r3 = el("div", "admin-row3"); f.appendChild(r3);
    F.position = field(r3, "Position", "input", { maxlength: "12", placeholder: "G, F, C…" });
    F.height = field(r3, "Height", "input", { maxlength: "10", placeholder: "6'1" });
    F.grade = select(r3, "Grade", [["", "—"], ["9", "9"], ["10", "10"], ["11", "11"], ["12", "12"]]);
    F.source = field(f, "Source", "input", { maxlength: "200", placeholder: "e.g. Bangor game program, Feb. 12, 2000" });
    var bx = el("div", "admin-actions"); f.appendChild(bx);
    var go = button(bx, "Add to the roster");
    var cancel = button(bx, "Cancel editing", "link-btn", function () { stop(); msg(m, ""); }); cancel.hidden = true;
    var m = el("p", "admin-msg"); f.appendChild(m);
    function stop() {
      var src = F.source.value; editing = null; f.reset(); F.source.value = src;
      title.textContent = "Add a player"; go.textContent = "Add to the roster"; cancel.hidden = true;
    }
    function load() {
      ul.innerHTML = '<li class="muted">Loading…</li>';
      call({ action: "rows", table: "roster", where: { season: ctx.season } }).then(function (j) {
        var rows = j.rows.sort(function (a, b) { return (parseInt(a.number, 10) || 0) - (parseInt(b.number, 10) || 0); });
        ul.innerHTML = "";
        if (!rows.length) ul.appendChild(el("li", "muted", "No roster on file yet."));
        rows.forEach(function (r) {
          ul.appendChild(rowItem((r.number ? "#" + r.number + " " : "") + r.name,
            [r.position, r.height, r.grade ? "Grade " + r.grade : ""].filter(Boolean).join(" · "), [
              { label: "Edit", fn: function () {
                editing = r; Object.keys(F).forEach(function (k) { F[k].value = r[k] || ""; });
                title.textContent = "Edit " + r.name; go.textContent = "Save changes"; cancel.hidden = false; msg(m, "");
                F.name.focus();
              } },
              removeBtn("roster", r, r.name + " from the " + dash(ctx.season) + " roster", load, m)]));
        });
        if (rows.length && !F.source.value) F.source.value = rows[rows.length - 1].source || "";
      }).catch(function (err) { ul.innerHTML = ""; ul.appendChild(el("li", "admin-msg bad", err.message)); });
    }
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var after = { season: ctx.season };
      Object.keys(F).forEach(function (k) { after[k] = F[k].value.trim(); });
      go.disabled = true; msg(m, "Saving…");
      call({ action: "save", table: "roster", before: editing, after: after })
        .then(function () { saved(m); stop(); load(); })
        .catch(function (err) { msg(m, err.message, false); })
        .then(function () { go.disabled = false; });
    });
    s.appendChild(f);
    load();
  }

  // ------------------------------------------------------------ class year
  function gradSection() {
    var s = section("grad", "Class year", "A year saved here replaces the site's own guess (marked est. on the page).");
    if (!ctx.plain) { s.appendChild(el("p", "admin-msg bad", "This page is one of two players with the same name. Fix the class year by hand in overrides/grad_years.csv instead.")); return; }
    var f = el("form", "admin-form"), row = null;
    var r2 = el("div", "admin-row2"); f.appendChild(r2);
    var year = field(r2, "Class of", "input", { inputmode: "numeric", maxlength: "4", required: "", placeholder: "2027" });
    var note = field(r2, "How you know", "input", { maxlength: "200", placeholder: "Optional, e.g. 1997–98 yearbook" });
    var bx = el("div", "admin-actions"); f.appendChild(bx);
    var go = button(bx, "Save");
    var rm = button(bx, "Remove this correction", "link-btn danger", function () {
      if (!row || !confirm("Remove the saved class year for " + ctx.name + "? The site goes back to its own guess.")) return;
      call({ action: "save", table: "grad", before: row, after: null })
        .then(function () { row = null; rm.hidden = true; year.value = ""; note.value = ""; saved(m); })
        .catch(function (err) { msg(m, err.message, false); });
    });
    rm.hidden = true;
    var m = el("p", "admin-msg"); f.appendChild(m);
    call({ action: "rows", table: "grad", where: { name: ctx.name } }).then(function (j) {
      row = j.rows[0] || null;
      if (row) { year.value = row.grad_year; note.value = row.note; rm.hidden = false; }
    }).catch(function (err) { msg(m, err.message, false); });
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      go.disabled = true; msg(m, "Saving…");
      call({ action: "save", table: "grad", before: row, after: { name: ctx.name, grad_year: year.value.trim(), note: note.value.trim() } })
        .then(function (j) { row = j.row; rm.hidden = false; saved(m); })
        .catch(function (err) { msg(m, err.message, false); })
        .then(function () { go.disabled = false; });
    });
    s.appendChild(f);
  }

  // ------------------------------------------------------------ game links
  var TYPES = {
    article: { table: "news", kind: "article", name: "News story", title: "Headline", access: [["free", "Free to read"], ["subscriber", "Subscribers only"]] },
    video: { table: "news", kind: "video", name: "News video", title: "Headline", access: [["free", "Free to watch"], ["subscriber", "Subscribers only"]] },
    photos: { table: "news", kind: "photos", name: "Photo gallery", title: "Gallery title", access: [["free", "Anyone"]] },
    film: { table: "film", name: "YouTube game film", title: "Video title", access: [["free", "Anyone (YouTube)"]], hint: "A game shows one YouTube film. If it already has one, remove the old one first." },
    hudl_full: { table: "hudl", kind: "full", name: "Hudl full-game replay", title: "Video title", access: [["free", "Free"], ["login", "Free with a Hudl login"], ["paid", "Hudl subscribers"]] },
    hudl_recap: { table: "hudl", kind: "recap", name: "Hudl highlights / recap", title: "Video title", access: [["free", "Free"], ["login", "Free with a Hudl login"], ["paid", "Hudl subscribers"]] },
  };
  function typeOf(table, r) {
    if (table === "film") return "film";
    if (table === "hudl") return r.kind === "recap" ? "hudl_recap" : "hudl_full";
    return r.kind === "photos" ? "photos" : r.kind === "video" ? "video" : "article";
  }
  function linksSection() {
    var s = section("links", "News, photos and film", "Links shown on this game's page. Scores, stats and the livestream come from the Google Sheet.");
    var ul = el("ul", "admin-list admin-rows"); s.appendChild(ul);
    var f = el("form", "admin-form");
    f.appendChild(el("h4", "", "Add a link"));
    var url = field(f, "Link", "input", { type: "url", required: "", placeholder: "https://…", autocomplete: "off" });
    var type = select(f, "What is it?", Object.keys(TYPES).map(function (k) { return [k, TYPES[k].name]; }));
    var head = field(f, "Headline", "input", { maxlength: "200" });
    var headLabel = head.parentNode.firstChild;
    var r2 = el("div", "admin-row2"); f.appendChild(r2);
    var outlet = field(r2, "Published by", "input", { maxlength: "60" });
    var pub = field(r2, "Date published", "input", { type: "date" });
    var access = select(f, "Who can see it", []);
    var hint = el("p", "muted small"); f.appendChild(hint);
    var go = button(f, "Add to the game page"), m = el("p", "admin-msg"); f.appendChild(m);
    function setType(t) {
      type.value = t; var T = TYPES[t];
      headLabel.textContent = T.title;
      r2.hidden = T.table !== "news";
      access.innerHTML = "";
      T.access.forEach(function (a) { var o = el("option", "", a[1]); o.value = a[0]; access.appendChild(o); });
      hint.textContent = T.hint || "";
      if (t === "photos" && !outlet.value) outlet.value = "GX3 Media";
    }
    type.addEventListener("change", function () { setType(type.value); });
    url.addEventListener("input", function () { // guess the kind and outlet from the link, as the admin page does
      var u = url.value.toLowerCase();
      var t = /youtu\.?be/.test(u) ? "film" : /hudl\.com/.test(u) ? "hudl_full" : /smugmug|gx3media/.test(u) ? "photos" : /\/video\//.test(u) ? "video" : null;
      if (t) setType(t);
      var o = /news8000/.test(u) ? "WKBT News 8" : /wxow/.test(u) ? "WXOW 19" : /lacrossetribune/.test(u) ? "La Crosse Tribune" : /smugmug|gx3media/.test(u) ? "GX3 Media" : "";
      if (o) outlet.value = o;
    });
    setType("article");
    function load() {
      ul.innerHTML = '<li class="muted">Loading…</li>';
      Promise.all([call({ action: "rows", table: "news", where: { game_date: ctx.date } }),
                   call({ action: "rows", table: "film", where: { date: ctx.date } }),
                   call({ action: "rows", table: "hudl", where: { date: ctx.date } })])
        .then(function (rs) {
          ul.innerHTML = "";
          var n = 0;
          ["news", "film", "hudl"].forEach(function (tb, i) {
            rs[i].rows.forEach(function (r) {
              n++;
              var t = typeOf(tb, r), link = r.url || r.youtube_url;
              var li = rowItem(r.title || link, [TYPES[t].name, r.outlet, r.published ? fmtDate(r.published) : ""].filter(Boolean).join(" · "),
                [removeBtn(tb, r, "this link from the game page", load, m)]);
              var a = el("a", "small admin-url", link); a.href = link; a.target = "_blank"; a.rel = "noopener";
              li.firstChild.appendChild(a);
              ul.appendChild(li);
            });
          });
          if (!n) ul.appendChild(el("li", "muted", "No news, film or photo links on this game yet."));
        }).catch(function (err) { ul.innerHTML = ""; ul.appendChild(el("li", "admin-msg bad", err.message)); });
    }
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      var T = TYPES[type.value], u = url.value.trim(), row;
      if (T.table === "news") {
        row = { published: pub.value || ctx.date, outlet: outlet.value, kind: T.kind, title: head.value, url: u, access: access.value,
                game_date: ctx.date, opponent: ctx.opponent, player: "", matched_by: "manual" };
      } else if (T.table === "film") {
        row = { date: ctx.date, opponent: ctx.opponent, youtube_url: u, title: head.value, matched_by: "manual" };
      } else {
        row = { date: ctx.date, opponent: ctx.opponent, kind: T.kind, access: access.value, url: u, title: head.value };
      }
      go.disabled = true; msg(m, "Saving…");
      call({ action: "save", table: T.table, before: null, after: row })
        .then(function () { saved(m); f.reset(); setType("article"); load(); })
        .catch(function (err) { msg(m, err.message, false); })
        .then(function () { go.disabled = false; });
    });
    s.appendChild(f);
    load();
  }

  // ------------------------------------------------------------ the bar and the photo placeholders
  function start() {
    var bar = el("div", "ae-bar");
    bar.setAttribute("role", "region"); bar.setAttribute("aria-label", "Admin");
    bar.appendChild(el("span", "ae-tag", "Admin"));
    if (ctx.kind) button(bar, "Edit this page", "ae-btn ae-edit", function () { openPanel(); });
    var a = el("a", "ae-btn", "Admin page"); a.href = ADMIN; bar.appendChild(a);
    button(bar, "Sign out", "ae-btn", function () { if (confirm("Hide the edit buttons on this device? Sign in on the admin page to bring them back.")) signOut(); });
    body.appendChild(bar);
    // the "No team photo yet" box and a headshot placeholder each get an Add photo button
    var ph = ctx.kind === "season" ? document.querySelector(".team-ph .ph-text") : ctx.kind === "player" ? document.querySelector(".headshot-ph") : null;
    if (ph) button(ph, ctx.kind === "season" ? "Add team photo" : "Add photo", "ae-add", function () { openPanel("photo"); });
  }

  // check the key first: an expired one signs this device out quietly; off the live site the bar still shows
  call({ action: "check" }).then(start).catch(function (err) { if (err.status !== 401) start(); });
})();

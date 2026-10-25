// FinPulse UI helpers. No inline scripts (CSP: script-src 'self').
(function () {
  "use strict";
  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Mobile navigation
  var toggle = document.querySelector("[data-nav-toggle]");
  var sidebar = document.getElementById("sidebar");
  var scrim = document.querySelector("[data-nav-close]");
  function setNav(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (scrim) scrim.classList.toggle("open", open);
    if (toggle) toggle.setAttribute("aria-expanded", String(open));
  }
  if (toggle) toggle.addEventListener("click", function () { setNav(!sidebar.classList.contains("open")); });
  if (scrim) scrim.addEventListener("click", function () { setNav(false); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") setNav(false); });

  // Progress bars: width is set from data-pct via CSSOM (inline style attributes are blocked by CSP)
  var bars = document.querySelectorAll("[data-pct]");
  requestAnimationFrame(function () {
    bars.forEach(function (bar) {
      var pct = Math.max(0, Math.min(100, parseFloat(bar.getAttribute("data-pct")) || 0));
      bar.style.width = pct + "%";
    });
  });

  // Confirm destructive actions
  document.querySelectorAll("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      if (!window.confirm(form.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  // Show the chosen CSV filename
  document.querySelectorAll(".dropzone input[type=file]").forEach(function (input) {
    input.addEventListener("change", function () {
      var label = input.closest(".dropzone").querySelector("[data-file-label]");
      if (label && input.files.length) label.textContent = input.files[0].name;
    });
  });

  // Count-up for score numbers
  if (!reduceMotion) {
    document.querySelectorAll("[data-count]").forEach(function (el) {
      var target = parseInt(el.getAttribute("data-count"), 10) || 0;
      var start = performance.now();
      var duration = 900;
      function tick(now) {
        var t = Math.min(1, (now - start) / duration);
        el.textContent = String(Math.round(target * (1 - Math.pow(1 - t, 3))));
        if (t < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }

  // Auto-fade success flashes
  document.querySelectorAll(".flash-success").forEach(function (el) {
    setTimeout(function () { el.classList.add("fade"); }, 4000);
  });
})();

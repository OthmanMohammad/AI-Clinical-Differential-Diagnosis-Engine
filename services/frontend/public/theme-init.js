// Theme bootstrap — runs before React mounts (on the main app) and before
// any content renders (on legal pages like /disclaimer.html, /privacy.html).
//
// Loaded as an external <script src="/theme-init.js"> so CSP only needs
// script-src 'self' — no hash whitelisting required.
//
// The app stores one of three values in localStorage under "mooseglove.theme":
//   "light"  — force light
//   "dark"   — force dark
//   "system" — follow OS preference
//
// If no value is stored (first visit, incognito), follow OS preference.
(function () {
  try {
    var stored = localStorage.getItem("mooseglove.theme");
    var theme;
    if (stored === "dark") {
      theme = "dark";
    } else if (stored === "light") {
      theme = "light";
    } else {
      // "system" or null — follow OS preference
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(theme);
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();

// Theme bootstrap — runs before React mounts (on the main app) and before
// any content renders (on legal pages like /disclaimer.html, /privacy.html).
//
// Loaded as an external <script src="/theme-init.js"> so CSP only needs
// script-src 'self'.
//
// The app stores one of three values in localStorage under "mooseglove.theme":
//   "light"  — force light
//   "dark"   — force dark
//   "system" — follow OS preference
//
// Default (null / first visit / incognito): light. This matches the app's
// default in ThemeContext.tsx. The OS preference only applies when the user
// has explicitly selected "system" mode.
(function () {
  try {
    var stored = localStorage.getItem("mooseglove.theme");
    var theme;
    if (stored === "dark") {
      theme = "dark";
    } else if (stored === "system") {
      // Only follow OS when user explicitly chose "system"
      theme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    } else {
      // "light" or null (default) — always light
      theme = "light";
    }
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(theme);
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();

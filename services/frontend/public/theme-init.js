// Prevent flash of wrong theme before React mounts. Default to light.
//
// This file is served from the Vite public/ directory as a static asset
// and loaded synchronously from index.html via <script src="/theme-init.js">.
// It runs BEFORE React so dark-mode users see the correct background
// color on first paint.
//
// It lives as an external file (not inlined in index.html) because inline
// scripts require CSP hash whitelisting in public/_headers, and Vite's
// HTML processing during build slightly reformats inline scripts which
// drifts the hash. An external file served from /theme-init.js only
// needs script-src 'self' in CSP, which is the default.
(function () {
  try {
    var stored = localStorage.getItem("pathodx.theme");
    var theme = stored === "dark" ? "dark" : "light";
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(theme);
    document.documentElement.setAttribute("data-theme", theme);
  } catch (e) {}
})();

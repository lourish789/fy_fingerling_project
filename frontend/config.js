// Backend location for the dashboard.
// When the dashboard is served by the AquaCount backend itself (hatchery laptop,
// offline), the backend replaces this file with one that points to its own origin.
// On Vercel this static file is served as-is, and index.html falls back to the
// hosted backend URL (or ?backend=...).
window.AQUACOUNT_API = window.AQUACOUNT_API || null;

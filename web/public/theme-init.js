// Apply the saved theme before first paint, so there is no light/dark flash.
(function () {
  try {
    var t = localStorage.getItem('aq-theme');
    if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
  } catch (e) { /* storage blocked: follow the system theme */ }
})();

/* ===========================================================================
   AA public nav - mobile menu
   The marketing pages (aa.html + the /aa-* inner pages) hide their desktop
   .nav-links on small screens but ship no replacement, so the whole menu
   vanishes on phones. This self-contained script injects a hamburger button
   and a slide-down drawer built from the page's existing nav markup, plus the
   CSS it needs - so a single <script src="/aa-nav.js" defer> on each page is
   all that's required, regardless of which stylesheet that page loads.
   =========================================================================== */
(function () {
  'use strict';

  function init() {
    var navLinks = document.querySelector('nav .nav-links');
    var nav = navLinks ? navLinks.closest('nav') : null;
    if (!nav || !navLinks || nav.querySelector('.aa-burger')) return;

    injectStyle();

    // --- hamburger button ----------------------------------------------------
    var burger = document.createElement('button');
    burger.className = 'aa-burger';
    burger.setAttribute('aria-label', 'Open menu');
    burger.setAttribute('aria-expanded', 'false');
    burger.innerHTML =
      '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">' +
      '<line class="b1" x1="3" y1="6" x2="21" y2="6"/>' +
      '<line class="b2" x1="3" y1="12" x2="21" y2="12"/>' +
      '<line class="b3" x1="3" y1="18" x2="21" y2="18"/></svg>';
    nav.appendChild(burger);

    // --- drawer (built from the existing menu) ------------------------------
    var drawer = document.createElement('div');
    drawer.className = 'aa-mnav';
    var inner = document.createElement('div');
    inner.className = 'aa-mnav-inner';
    inner.innerHTML = navLinks.innerHTML;

    var navEnd = nav.querySelector('.nav-end');
    if (navEnd) {
      var actions = document.createElement('div');
      actions.className = 'aa-mnav-actions';
      actions.innerHTML = navEnd.innerHTML;
      inner.appendChild(actions);
    }
    drawer.appendChild(inner);
    document.body.appendChild(drawer);

    // --- behaviour -----------------------------------------------------------
    function position() { drawer.style.top = Math.round(nav.getBoundingClientRect().bottom) + 'px'; }
    function open() {
      position();
      drawer.classList.add('open');
      burger.classList.add('open');
      burger.setAttribute('aria-expanded', 'true');
      burger.setAttribute('aria-label', 'Close menu');
      document.body.classList.add('aa-mnav-lock');
    }
    function close() {
      drawer.classList.remove('open');
      burger.classList.remove('open');
      burger.setAttribute('aria-expanded', 'false');
      burger.setAttribute('aria-label', 'Open menu');
      document.body.classList.remove('aa-mnav-lock');
    }
    function toggle() { drawer.classList.contains('open') ? close() : open(); }

    burger.addEventListener('click', function (e) { e.stopPropagation(); toggle(); });
    // Close after tapping a real link; leave dropdown toggle buttons alone.
    drawer.addEventListener('click', function (e) { if (e.target.closest('a')) close(); });
    document.addEventListener('click', function (e) {
      if (drawer.classList.contains('open') && !drawer.contains(e.target) && !burger.contains(e.target)) close();
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
    window.addEventListener('resize', function () {
      if (window.innerWidth > 900) close(); else if (drawer.classList.contains('open')) position();
    });
  }

  function injectStyle() {
    if (document.getElementById('aa-nav-css')) return;
    var css =
      '.aa-burger{display:none;background:none;border:none;padding:6px;margin-left:auto;cursor:pointer;color:var(--text,#14140F);align-items:center;justify-content:center;flex-shrink:0;}' +
      '.aa-burger .b1,.aa-burger .b2,.aa-burger .b3{transition:transform .25s ease,opacity .2s ease;transform-origin:center;}' +
      '.aa-burger.open .b1{transform:translateY(6px) rotate(45deg);}' +
      '.aa-burger.open .b2{opacity:0;}' +
      '.aa-burger.open .b3{transform:translateY(-6px) rotate(-45deg);}' +
      '.aa-mnav{position:fixed;top:72px;left:0;right:0;z-index:290;background:#fff;border-bottom:1px solid var(--line,#E2DFD6);' +
        'box-shadow:0 24px 50px rgba(11,11,14,.16);max-height:calc(100vh - 72px);overflow-y:auto;' +
        'transform:translateY(-12px);opacity:0;visibility:hidden;pointer-events:none;transition:transform .22s ease,opacity .22s ease,visibility .22s;}' +
      '.aa-mnav.open{transform:translateY(0);opacity:1;visibility:visible;pointer-events:auto;}' +
      '.aa-mnav-inner{padding:14px 22px 26px;display:flex;flex-direction:column;}' +
      // dropdown groups become always-open stacked sections
      '.aa-mnav .nav-item{position:static;display:block;border-top:1px solid var(--line,#E2DFD6);}' +
      '.aa-mnav .nav-item:first-child{border-top:none;}' +
      '.aa-mnav .nav-link{display:flex;width:100%;justify-content:flex-start;gap:8px;padding:14px 2px;font-size:15px;' +
        "font-family:'Helvetica Neue',Helvetica,Arial,sans-serif;font-weight:600;color:#14140F !important;text-transform:none;letter-spacing:0;background:none;border:none;text-align:left;}" +
      '.aa-mnav .nav-link .chev{display:none;}' +
      '.aa-mnav .nav-dropdown{position:static !important;opacity:1 !important;visibility:visible !important;pointer-events:auto !important;padding:0 0 8px;}' +
      '.aa-mnav .nav-dropdown-inner{border:none;box-shadow:none;padding:0;min-width:0;background:none;}' +
      '.aa-mnav .nav-dropdown-inner a{padding:11px 14px;font-size:14px;color:#4A4A44 !important;}' +
      '.aa-mnav .nav-dropdown-inner a:hover{background:var(--paper-2,#F5F4EF);color:var(--red,#E61832) !important;}' +
      // direct (non-dropdown) menu links, e.g. "Activities"
      '.aa-mnav>.aa-mnav-inner>a{display:block;padding:14px 2px;font-size:15px;font-weight:600;' +
        'color:#14140F !important;text-decoration:none;border-top:1px solid var(--line,#E2DFD6);}' +
      '.aa-mnav-actions{display:flex;flex-direction:column;gap:10px;margin-top:18px;padding-top:18px;border-top:1px solid var(--line,#E2DFD6);}' +
      '.aa-mnav-actions .btn-red,.aa-mnav-actions .btn-ghost{justify-content:center;width:100%;}' +
      '.aa-mnav-lock{overflow:hidden;}' +
      '@media (max-width:900px){nav .nav-links,nav .nav-end{display:none !important;}.aa-burger{display:inline-flex !important;}}' +
      '@media (min-width:901px){.aa-mnav{display:none !important;}}';
    var s = document.createElement('style');
    s.id = 'aa-nav-css';
    s.textContent = css;
    document.head.appendChild(s);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();

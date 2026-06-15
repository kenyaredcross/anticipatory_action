/* Shared helpers for the AA portal pages (aa-portal, aa-admin, aa-profile). */
(function () {
  window.AA = window.AA || {};
  // Token injected by each portal page's get_context (these standalone pages
  // don't load Frappe's web bundle, so window.frappe isn't available).
  var csrf = window.AA_CSRF || (window.frappe && frappe.csrf_token) || '';

  // Pull a clean, user-facing message out of a Frappe error response.
  AA.parseError = function (data) {
    try {
      if (data && data._server_messages) {
        var arr = JSON.parse(data._server_messages);
        if (arr.length) {
          var m = JSON.parse(arr[0]);
          if (m && m.message) return String(m.message).replace(/<[^>]*>/g, '');
        }
      }
    } catch (e) {}
    if (data && data.exc_type === 'PermissionError') return 'You are not authorised to do that.';
    if (data && typeof data.message === 'string') return data.message.replace(/<[^>]*>/g, '');
    return null;
  };

  // Call a whitelisted method; resolves to its `message` payload, throws on error.
  AA.call = async function (method, args) {
    var res = await fetch('/api/method/' + method, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrf },
      body: JSON.stringify(args || {})
    });
    var data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) {
      if (res.status === 403) { throw new Error(AA.parseError(data) || 'You are not authorised to do that.'); }
      throw new Error(AA.parseError(data) || 'Request failed. Please try again.');
    }
    return data.message;
  };

  // Upload a file, returns its file_url.
  AA.upload = async function (file, isPrivate) {
    var fd = new FormData();
    fd.append('file', file, file.name);
    fd.append('is_private', isPrivate ? 1 : 0);
    var res = await fetch('/api/method/upload_file', {
      method: 'POST', headers: { 'X-Frappe-CSRF-Token': csrf }, body: fd
    });
    var data = {};
    try { data = await res.json(); } catch (e) {}
    if (!res.ok) throw new Error(AA.parseError(data) || 'Upload failed.');
    return data.message && data.message.file_url;
  };

  AA.esc = function (s) {
    if (s === null || s === undefined) return '';
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  AA.fmtNum = function (n) {
    n = Number(n || 0);
    return n.toLocaleString('en-KE');
  };

  AA.toast = function (msg, ok) {
    var t = document.getElementById('toast');
    if (!t) { t = document.createElement('div'); t.id = 'toast'; document.body.appendChild(t); }
    t.textContent = msg;
    t.className = 'toast' + (ok ? ' ok' : '') + ' show';
    clearTimeout(AA._toastT);
    AA._toastT = setTimeout(function () { t.className = 'toast' + (ok ? ' ok' : ''); }, 3200);
  };

  AA.logout = async function () {
    try { await fetch('/api/method/logout', { method: 'POST', headers: { 'X-Frappe-CSRF-Token': csrf } }); } catch (e) {}
    window.location.href = '/anticipatory-login';
  };

  document.addEventListener('DOMContentLoaded', function () {
    var lo = document.getElementById('logoutBtn');
    if (lo) lo.addEventListener('click', AA.logout);
    var tg = document.getElementById('navToggle');
    if (tg) tg.addEventListener('click', function () {
      var l = document.getElementById('pbLinks');
      if (l) l.classList.toggle('open');
    });
  });
})();

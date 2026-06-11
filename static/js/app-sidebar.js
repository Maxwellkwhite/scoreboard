(function () {
  'use strict';

  var MOBILE_MAX = 768;
  var wasMobile = window.matchMedia('(max-width: 768px)').matches;
  var floatingTip = null;
  var tipAnchor = null;

  function isMobile() {
    return window.matchMedia('(max-width: 768px)').matches;
  }

  function getSidebar() {
    return document.getElementById('sidebar');
  }

  function hydrateMenuTips() {
    document.querySelectorAll('.menu-item').forEach(function (el) {
      var span = el.querySelector('.menu-item-text');
      if (span && !el.dataset.sidebarTip) {
        el.dataset.sidebarTip = span.textContent.trim();
      }
    });
  }

  function removeFloatingTip() {
    if (floatingTip && floatingTip.parentNode) {
      floatingTip.parentNode.removeChild(floatingTip);
    }
    floatingTip = null;
    tipAnchor = null;
    window.removeEventListener('scroll', onTipReposition, true);
    window.removeEventListener('resize', onTipReposition);
  }

  function onTipReposition() {
    if (!floatingTip || !tipAnchor) return;
    var r = tipAnchor.getBoundingClientRect();
    floatingTip.style.left = Math.round(r.right + 10) + 'px';
    floatingTip.style.top = Math.round(r.top + r.height / 2) + 'px';
  }

  function showFloatingTip(anchor, text) {
    removeFloatingTip();
    if (!text || !anchor) return;
    var el = document.createElement('div');
    el.className = 'sidebar-hover-label';
    el.setAttribute('role', 'tooltip');
    el.textContent = text;
    document.body.appendChild(el);
    floatingTip = el;
    tipAnchor = anchor;
    onTipReposition();
    window.addEventListener('scroll', onTipReposition, true);
    window.addEventListener('resize', onTipReposition);
  }

  function shouldShowCollapsedTips() {
    var sidebar = getSidebar();
    return !isMobile() && sidebar && sidebar.classList.contains('sidebar--collapsed');
  }

  function onMenuTipShow(ev) {
    if (!shouldShowCollapsedTips()) return;
    var t = ev.currentTarget.dataset.sidebarTip;
    if (t) showFloatingTip(ev.currentTarget, t);
  }

  function onMenuTipHide() {
    removeFloatingTip();
  }

  function bindCollapsedMenuTips() {
    document.querySelectorAll('.menu-item').forEach(function (a) {
      a.addEventListener('mouseenter', onMenuTipShow);
      a.addEventListener('mouseleave', onMenuTipHide);
      a.addEventListener('focus', onMenuTipShow);
      a.addEventListener('blur', onMenuTipHide);
    });
  }

  function syncDesktopExpandButton() {
    var btn = document.getElementById('sidebarDesktopExpand');
    var sidebar = getSidebar();
    if (!btn || !sidebar) return;

    if (isMobile()) {
      btn.setAttribute('hidden', '');
      btn.setAttribute('aria-hidden', 'true');
      return;
    }

    btn.removeAttribute('hidden');
    btn.removeAttribute('aria-hidden');

    var collapsed = sidebar.classList.contains('sidebar--collapsed');
    btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
    btn.setAttribute('aria-label', collapsed ? 'Expand sidebar' : 'Collapse sidebar');

    var icon = btn.querySelector('i');
    if (icon) {
      icon.className = collapsed ? 'bi bi-chevron-double-right' : 'bi bi-chevron-double-left';
    }
  }

  function applyLayoutForViewport() {
    removeFloatingTip();
    var sidebar = getSidebar();
    if (!sidebar) return;

    var mobile = isMobile();

    if (mobile !== wasMobile) {
      wasMobile = mobile;
      if (mobile) {
        sidebar.classList.remove('sidebar--collapsed');
      } else {
        sidebar.classList.add('sidebar--collapsed');
        sidebar.classList.remove('active');
      }
    } else if (!mobile) {
      sidebar.classList.remove('active');
    }

    syncDesktopExpandButton();
  }

  function init() {
    var sidebar = getSidebar();
    var toggle = document.getElementById('sidebarToggle');
    var expandBtn = document.getElementById('sidebarDesktopExpand');
    if (!sidebar) return;

    hydrateMenuTips();
    bindCollapsedMenuTips();

    if (isMobile()) {
      sidebar.classList.remove('sidebar--collapsed');
    } else {
      sidebar.classList.add('sidebar--collapsed');
      sidebar.classList.remove('active');
    }
    wasMobile = isMobile();
    syncDesktopExpandButton();

    if (expandBtn) {
      expandBtn.addEventListener('click', function () {
        if (isMobile()) return;
        removeFloatingTip();
        sidebar.classList.toggle('sidebar--collapsed');
        syncDesktopExpandButton();
      });
    }

    if (toggle) {
      toggle.addEventListener('click', function () {
        sidebar.classList.toggle('active');
      });
    }

    document.addEventListener('click', function (event) {
      if (!isMobile()) return;
      var t = document.getElementById('sidebarToggle');
      if (t && !t.contains(event.target) && !sidebar.contains(event.target)) {
        sidebar.classList.remove('active');
      }
    });

    window.addEventListener('resize', applyLayoutForViewport);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

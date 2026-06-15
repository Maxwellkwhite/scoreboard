(function () {
  function applyDeviceClasses() {
    var root = document.documentElement;
    var viewportWidth = window.innerWidth;
    var viewportHeight = window.innerHeight;
    var isLocalDev = /^(localhost|127\.0\.0\.1)$/.test(window.location.hostname);
    var hasCoarsePointer = window.matchMedia('(pointer: coarse)').matches;
    var hasTouchScreen = ('ontouchstart' in window) || (navigator.maxTouchPoints > 0);
    var mobileUA = /Android|iPhone|iPad|iPod|webOS|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
    var isIPad = /iPad/i.test(navigator.userAgent) ||
      (/Macintosh/i.test(navigator.userAgent) && hasTouchScreen);
    var isAndroidTablet = /Android/i.test(navigator.userAgent) && !/Mobile/i.test(navigator.userAgent);
    var isPhoneUA = /iPhone|iPod/i.test(navigator.userAgent) ||
      (/Android/i.test(navigator.userAgent) && /Mobile/i.test(navigator.userAgent));
    var isTablet = isIPad || isAndroidTablet || (hasTouchScreen && viewportWidth >= 768 && !isPhoneUA);
    var isPhoneViewport = viewportWidth <= 767 || (viewportWidth <= 932 && viewportHeight <= 767);
    var isRealMobile = hasCoarsePointer && hasTouchScreen && mobileUA && !isTablet && isPhoneViewport;

    root.classList.toggle('is-desktop', isLocalDev || !isRealMobile);
    root.classList.toggle('is-mobile-gate', !isLocalDev && isRealMobile);
  }

  applyDeviceClasses();
  window.addEventListener('resize', applyDeviceClasses);
  window.addEventListener('orientationchange', applyDeviceClasses);
})();

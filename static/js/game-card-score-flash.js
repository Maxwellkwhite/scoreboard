(function () {
  var cardFlashTimers = new WeakMap();
  var FLASH_MS = 5000;
  var RIPPLE_DELAYS_MS = [0, 500, 1000, 1600, 2200];

  function teamColor(team) {
    return team && (team.win_color || team.color) || null;
  }

  function ensureRippleLayer(card) {
    var layer = card.querySelector('.game-card-ripple-layer');
    if (layer) {
      return layer;
    }
    layer = document.createElement('span');
    layer.className = 'game-card-ripple-layer';
    layer.setAttribute('aria-hidden', 'true');
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function spawnCardRipples(card, teamEl) {
    if (!teamEl) {
      return;
    }

    var layer = ensureRippleLayer(card);
    var cardRect = card.getBoundingClientRect();
    var teamRect = teamEl.getBoundingClientRect();
    var x = teamRect.right - cardRect.left - 10;
    var y = teamRect.top + teamRect.height / 2 - cardRect.top;

    RIPPLE_DELAYS_MS.forEach(function (delayMs) {
      var ripple = document.createElement('span');
      ripple.className = 'game-card-ripple';
      ripple.style.left = x + 'px';
      ripple.style.top = y + 'px';
      ripple.style.animationDelay = (delayMs / 1000) + 's';
      layer.appendChild(ripple);
      ripple.addEventListener('animationend', function () {
        ripple.remove();
      });
    });
  }

  function flashScoreOnCard(card, side, team) {
    var color = teamColor(team);
    if (!color || !card) {
      return;
    }

    var teamEl = card.querySelector('.game-card-team--' + side);
    card.style.setProperty('--score-flash-color', color);
    card.style.setProperty('--score-flash-duration', (FLASH_MS / 1000) + 's');
    card.classList.remove('game-card--score-flash');
    void card.offsetWidth;
    card.classList.add('game-card--score-flash');
    if (teamEl) {
      teamEl.classList.add('game-card-team--scored');
    }
    spawnCardRipples(card, teamEl);

    var prev = cardFlashTimers.get(card);
    if (prev) {
      clearTimeout(prev.timer);
      if (prev.teamEl && prev.teamEl !== teamEl) {
        prev.teamEl.classList.remove('game-card-team--scored');
      }
    }

    var timer = setTimeout(function () {
      card.classList.remove('game-card--score-flash');
      if (teamEl) {
        teamEl.classList.remove('game-card-team--scored');
      }
      cardFlashTimers.delete(card);
    }, FLASH_MS);

    cardFlashTimers.set(card, { timer: timer, teamEl: teamEl });
  }

  window.gameCardScoreFlash = {
    flash: flashScoreOnCard,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--score-flash'));
    }
  };
})();

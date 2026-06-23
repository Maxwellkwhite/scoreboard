(function () {
  var MATCH_START_MS = 10000;

  var matchStartTimers = new WeakMap();

  function teamColor(team) {
    return (team && (team.win_color || team.color)) || '#1a2332';
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildMetaFromGame(game) {
    var away = (game && game.away) || {};
    var home = (game && game.home) || {};
    return {
      away: {
        abbr: away.abbr || 'AWY',
        name: away.short_name || away.name || 'Away',
        logo: away.logo || '',
        color: teamColor(away)
      },
      home: {
        abbr: home.abbr || 'HME',
        name: home.short_name || home.name || 'Home',
        logo: home.logo || '',
        color: teamColor(home)
      }
    };
  }

  function extractMetaFromCard(card) {
    function readTeam(side) {
      var row = card.querySelector('.game-card-team--' + side);
      if (!row) {
        return { abbr: side.toUpperCase(), name: side, logo: '', color: '#1a2332' };
      }
      var abbrEl = row.querySelector('.game-card-abbr');
      var nameEl = row.querySelector('.game-card-name');
      var logoEl = row.querySelector('.game-card-logo');
      return {
        abbr: abbrEl ? abbrEl.textContent.trim() : side.toUpperCase(),
        name: nameEl ? nameEl.textContent.trim() : side,
        logo: logoEl && logoEl.tagName === 'IMG' ? logoEl.getAttribute('src') : '',
        color: row.style.getPropertyValue('--team-color').trim() || '#1a2332'
      };
    }

    return {
      away: readTeam('away'),
      home: readTeam('home')
    };
  }

  function teamLogoHtml(team) {
    if (team.logo) {
      return (
        '<img class="game-card-match-start__logo" src="' + escapeHtml(team.logo) +
        '" alt="" width="56" height="56">'
      );
    }
    return (
      '<span class="game-card-match-start__logo game-card-match-start__logo--placeholder">' +
        escapeHtml(team.abbr) +
      '</span>'
    );
  }

  function buildBallHtml() {
    return (
      '<span class="game-card-match-start__ball" aria-hidden="true">' +
        '<img class="game-card-match-start__ball-img" src="/static/images/soccer-ball.svg" alt="" width="40" height="40">' +
      '</span>'
    );
  }

  function buildMarkingsHtml() {
    return (
      '<span class="game-card-match-start__markings" aria-hidden="true">' +
        '<span class="game-card-match-start__line game-card-match-start__line--half"></span>' +
        '<span class="game-card-match-start__circle"></span>' +
        '<span class="game-card-match-start__box game-card-match-start__box--left"></span>' +
        '<span class="game-card-match-start__box game-card-match-start__box--right"></span>' +
      '</span>'
    );
  }

  function buildMatchStartLayerHtml(meta) {
    return (
      '<span class="game-card-match-start__pitch">' +
        buildMarkingsHtml() +
      '</span>' +
      '<span class="game-card-match-start__team game-card-match-start__team--away" style="--team-color:' +
        escapeHtml(meta.away.color) + '">' +
        teamLogoHtml(meta.away) +
      '</span>' +
      '<span class="game-card-match-start__team game-card-match-start__team--home" style="--team-color:' +
        escapeHtml(meta.home.color) + '">' +
        teamLogoHtml(meta.home) +
      '</span>' +
      buildBallHtml()
    );
  }

  function ensureMatchStartLayer(card, meta) {
    var layer = card.querySelector('.game-card-match-start-layer');
    if (layer) {
      layer.remove();
    }
    layer = document.createElement('span');
    layer.className = 'game-card-match-start-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = buildMatchStartLayerHtml(meta);
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function playMatchStart(card, game) {
    if (!card) {
      return;
    }

    var meta = game ? buildMetaFromGame(game) : extractMetaFromCard(card);
    ensureMatchStartLayer(card, meta);
    card.style.setProperty('--match-start-duration', (MATCH_START_MS / 1000) + 's');
    card.classList.remove('game-card--match-start');
    void card.offsetWidth;
    card.classList.add('game-card--match-start');

    var prev = matchStartTimers.get(card);
    if (prev) {
      clearTimeout(prev);
    }

    var timer = setTimeout(function () {
      card.classList.remove('game-card--match-start');
      var layer = card.querySelector('.game-card-match-start-layer');
      if (layer) {
        layer.remove();
      }
      matchStartTimers.delete(card);
    }, MATCH_START_MS);

    matchStartTimers.set(card, timer);
  }

  window.gameCardMatchStart = {
    play: playMatchStart,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--match-start'));
    }
  };
})();

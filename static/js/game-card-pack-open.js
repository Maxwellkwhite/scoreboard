(function () {
  var PACK_MS = 10000;

  var packTimers = new WeakMap();

  function teamColor(team) {
    return (team && (team.win_color || team.color)) || '#1a2332';
  }

  function pitcherLabel(pitcher) {
    if (!pitcher || !pitcher.name) {
      return 'TBD';
    }
    var hand = pitcher.throws ? ' (' + pitcher.throws.charAt(0) + ')' : '';
    return pitcher.name + hand;
  }

  function buildMetaFromGame(game) {
    var away = (game && game.away) || {};
    var home = (game && game.home) || {};
    var awayRecord = away.record || '—';
    var homeRecord = home.record || '—';
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
      },
      records: away.abbr + ' ' + awayRecord + ' · ' + home.abbr + ' ' + homeRecord,
      pitchers: pitcherLabel(away.probable_pitcher) + ' vs ' + pitcherLabel(home.probable_pitcher)
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

    var away = readTeam('away');
    var home = readTeam('home');
    return {
      away: away,
      home: home,
      records: away.abbr + ' — · ' + home.abbr + ' —',
      pitchers: 'Pitchers TBD'
    };
  }

  function packLogoHtml(team) {
    if (team.logo) {
      return (
        '<img class="game-card-pack__pack-logo" src="' + escapeHtml(team.logo) +
        '" alt="" width="48" height="48">'
      );
    }
    return (
      '<span class="game-card-pack__pack-logo game-card-pack__pack-logo--placeholder">' +
        escapeHtml(team.abbr) +
      '</span>'
    );
  }

  function buildPackBrandingHtml(meta) {
    return (
      '<span class="game-card-pack__branding">' +
        '<span class="game-card-pack__pack-team game-card-pack__pack-team--away" style="--team-color:' +
          escapeHtml(meta.away.color) + '">' +
          packLogoHtml(meta.away) +
        '</span>' +
        '<span class="game-card-pack__pack-vs">VS</span>' +
        '<span class="game-card-pack__pack-team game-card-pack__pack-team--home" style="--team-color:' +
          escapeHtml(meta.home.color) + '">' +
          packLogoHtml(meta.home) +
        '</span>' +
      '</span>'
    );
  }

  function logoHtml(team) {
    if (team.logo) {
      return '<img class="game-card-pack__fan-logo" src="' + team.logo + '" alt="" width="32" height="32">';
    }
    return '<span class="game-card-pack__fan-logo game-card-pack__fan-logo--placeholder">' +
      escapeHtml(team.abbr) + '</span>';
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildFanCardsHtml(meta) {
    return (
      '<div class="game-card-pack__fan">' +
        '<div class="game-card-pack__fan-card game-card-pack__fan-card--away" style="--fan-color:' +
          escapeHtml(meta.away.color) + '">' +
          '<span class="game-card-pack__fan-kicker">Away</span>' +
          logoHtml(meta.away) +
          '<span class="game-card-pack__fan-abbr">' + escapeHtml(meta.away.abbr) + '</span>' +
          '<span class="game-card-pack__fan-name">' + escapeHtml(meta.away.name) + '</span>' +
        '</div>' +
        '<div class="game-card-pack__fan-card game-card-pack__fan-card--home" style="--fan-color:' +
          escapeHtml(meta.home.color) + '">' +
          '<span class="game-card-pack__fan-kicker">Home</span>' +
          logoHtml(meta.home) +
          '<span class="game-card-pack__fan-abbr">' + escapeHtml(meta.home.abbr) + '</span>' +
          '<span class="game-card-pack__fan-name">' + escapeHtml(meta.home.name) + '</span>' +
        '</div>' +
        '<div class="game-card-pack__fan-card game-card-pack__fan-card--records">' +
          '<span class="game-card-pack__fan-kicker">Records</span>' +
          '<span class="game-card-pack__fan-detail">' + escapeHtml(meta.records) + '</span>' +
        '</div>' +
        '<div class="game-card-pack__fan-card game-card-pack__fan-card--pitchers">' +
          '<span class="game-card-pack__fan-kicker">Pitchers</span>' +
          '<span class="game-card-pack__fan-detail">' + escapeHtml(meta.pitchers) + '</span>' +
        '</div>' +
      '</div>'
    );
  }

  function buildParticlesHtml() {
    var parts = [];
    for (var i = 0; i < 16; i += 1) {
      var angle = (360 / 16) * i;
      var dist = 36 + (i % 5) * 14;
      parts.push(
        '<span class="game-card-pack__particle" style="--particle-angle:' + angle +
        'deg;--particle-dist:' + dist + 'px"></span>'
      );
    }
    return '<div class="game-card-pack__particles">' + parts.join('') + '</div>';
  }

  function buildStreaksHtml() {
    return (
      '<div class="game-card-pack__streaks">' +
        '<span class="game-card-pack__streak game-card-pack__streak--a"></span>' +
        '<span class="game-card-pack__streak game-card-pack__streak--b"></span>' +
        '<span class="game-card-pack__streak game-card-pack__streak--c"></span>' +
      '</div>'
    );
  }

  function buildPackLayerHtml(meta) {
    return (
      '<span class="game-card-pack__shell">' +
        '<span class="game-card-pack__top"></span>' +
        '<span class="game-card-pack__bottom"></span>' +
        buildPackBrandingHtml(meta) +
        '<span class="game-card-pack__tear"></span>' +
      '</span>' +
      buildParticlesHtml() +
      buildStreaksHtml() +
      buildFanCardsHtml(meta)
    );
  }

  function ensurePackLayer(card, meta) {
    var layer = card.querySelector('.game-card-pack-layer');
    if (layer) {
      layer.remove();
    }
    layer = document.createElement('span');
    layer.className = 'game-card-pack-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = buildPackLayerHtml(meta);
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function playPackOpen(card, game) {
    if (!card) {
      return;
    }

    var meta = game ? buildMetaFromGame(game) : extractMetaFromCard(card);
    ensurePackLayer(card, meta);
    card.style.setProperty('--pack-open-duration', (PACK_MS / 1000) + 's');
    card.classList.remove('game-card--pack-open');
    void card.offsetWidth;
    card.classList.add('game-card--pack-open');

    var prev = packTimers.get(card);
    if (prev) {
      clearTimeout(prev);
    }

    var timer = setTimeout(function () {
      card.classList.remove('game-card--pack-open');
      var layer = card.querySelector('.game-card-pack-layer');
      if (layer) {
        layer.remove();
      }
      packTimers.delete(card);
    }, PACK_MS);

    packTimers.set(card, timer);
  }

  window.gameCardPackOpen = {
    play: playPackOpen,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--pack-open'));
    }
  };
})();

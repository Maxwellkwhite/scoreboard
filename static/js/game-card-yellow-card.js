(function () {
  var YELLOW_CARD_ANIM_MS = 6000;
  var YELLOW_CARD_FADE_RATIO = 0.72;
  var NAME_HOLD_MS = 5000;
  var NAME_FADE_MS = 700;

  var YELLOW_CARD_FADE_AT_MS = Math.round(YELLOW_CARD_ANIM_MS * YELLOW_CARD_FADE_RATIO);
  var TOTAL_MS = YELLOW_CARD_FADE_AT_MS + NAME_HOLD_MS + NAME_FADE_MS;

  var yellowCardTimers = new WeakMap();

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function normalizeOptions(options, card) {
    if (!options) {
      return { playerName: '', side: null, teamAbbr: '' };
    }
    if (typeof options === 'string') {
      return { playerName: options, side: null, teamAbbr: '' };
    }
    var side = options.side || null;
    var teamAbbr = options.teamAbbr || options.abbr || '';
    if (!teamAbbr && side && card) {
      teamAbbr = teamAbbrFromCard(card, side);
    }
    return {
      playerName: options.playerName || options.player || '',
      side: side,
      teamAbbr: teamAbbr
    };
  }

  function teamAbbrFromCard(card, side) {
    var row = card.querySelector('.game-card-team--' + side);
    if (!row) {
      return '';
    }
    var abbrEl = row.querySelector('.game-card-abbr');
    return abbrEl ? abbrEl.textContent.trim() : '';
  }

  function buildPlayerLabelHtml(meta, nameClass, abbrClass) {
    var name = escapeHtml(meta.playerName);
    if (meta.teamAbbr) {
      return (
        '<span class="' + nameClass + '">' + name + '</span>' +
        '<span class="' + abbrClass + '"> (' + escapeHtml(meta.teamAbbr) + ')</span>'
      );
    }
    return '<span class="' + nameClass + '">' + name + '</span>';
  }

  function buildLayerHtml(meta) {
    return (
      '<span class="game-card-yellow-card__flash" aria-hidden="true"></span>' +
      '<span class="game-card-yellow-card__card" aria-hidden="true">' +
        '<span class="game-card-yellow-card__card-face"></span>' +
      '</span>' +
      '<span class="game-card-yellow-card__player" aria-hidden="true">' +
        buildPlayerLabelHtml(meta, 'game-card-yellow-card__player-name', 'game-card-yellow-card__player-abbr') +
      '</span>'
    );
  }

  function ensureYellowCardLayer(card, meta) {
    var layer = card.querySelector('.game-card-yellow-card-layer');
    if (layer) {
      layer.remove();
    }
    layer = document.createElement('span');
    layer.className = 'game-card-yellow-card-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = buildLayerHtml(meta);
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function clearTimers(card) {
    var timers = yellowCardTimers.get(card);
    if (!timers) {
      return;
    }
    if (timers.endTimer) {
      clearTimeout(timers.endTimer);
    }
    yellowCardTimers.delete(card);
  }

  function finishYellowCard(card) {
    if (!card) {
      return;
    }
    card.classList.remove('game-card--yellow-card');
    var layer = card.querySelector('.game-card-yellow-card-layer');
    if (layer) {
      layer.remove();
    }
    card.style.removeProperty('--yellow-card-duration');
    card.style.removeProperty('--yellow-card-name-duration');
    clearTimers(card);
  }

  function playYellowCard(card, options) {
    if (!card) {
      return;
    }

    var meta = normalizeOptions(options, card);
    if (!meta.playerName) {
      return;
    }

    if (window.gameCardRedCard && window.gameCardRedCard.cancel) {
      window.gameCardRedCard.cancel(card);
    }

    clearTimers(card);
    finishYellowCard(card);

    ensureYellowCardLayer(card, meta);
    card.style.setProperty('--yellow-card-duration', (YELLOW_CARD_ANIM_MS / 1000) + 's');
    card.style.setProperty('--yellow-card-name-duration', (TOTAL_MS / 1000) + 's');
    card.classList.remove('game-card--yellow-card');
    void card.offsetWidth;
    card.classList.add('game-card--yellow-card');

    var endTimer = window.setTimeout(function () {
      finishYellowCard(card);
    }, TOTAL_MS);

    yellowCardTimers.set(card, { endTimer: endTimer });
  }

  window.gameCardYellowCard = {
    play: playYellowCard,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--yellow-card'));
    },
    cancel: finishYellowCard
  };
})();

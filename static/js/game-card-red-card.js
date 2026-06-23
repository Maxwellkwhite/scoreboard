(function () {
  var RED_CARD_ANIM_MS = 6000;
  var RED_CARD_FADE_RATIO = 0.72;
  var NAME_HOLD_MS = 5000;
  var NAME_FADE_MS = 700;

  var RED_CARD_FADE_AT_MS = Math.round(RED_CARD_ANIM_MS * RED_CARD_FADE_RATIO);
  var TOTAL_MS = RED_CARD_FADE_AT_MS + NAME_HOLD_MS + NAME_FADE_MS;

  var redCardTimers = new WeakMap();

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
      '<span class="game-card-red-card__flash" aria-hidden="true"></span>' +
      '<span class="game-card-red-card__card" aria-hidden="true">' +
        '<span class="game-card-red-card__card-face"></span>' +
      '</span>' +
      '<span class="game-card-red-card__player" aria-hidden="true">' +
        buildPlayerLabelHtml(meta, 'game-card-red-card__player-name', 'game-card-red-card__player-abbr') +
      '</span>'
    );
  }

  function ensureRedCardLayer(card, meta) {
    var layer = card.querySelector('.game-card-red-card-layer');
    if (layer) {
      layer.remove();
    }
    layer = document.createElement('span');
    layer.className = 'game-card-red-card-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = buildLayerHtml(meta);
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function clearTimers(card) {
    var timers = redCardTimers.get(card);
    if (!timers) {
      return;
    }
    if (timers.endTimer) {
      clearTimeout(timers.endTimer);
    }
    redCardTimers.delete(card);
  }

  function finishRedCard(card) {
    if (!card) {
      return;
    }
    card.classList.remove('game-card--red-card');
    var layer = card.querySelector('.game-card-red-card-layer');
    if (layer) {
      layer.remove();
    }
    card.style.removeProperty('--red-card-duration');
    card.style.removeProperty('--red-card-name-duration');
    clearTimers(card);
  }

  function playRedCard(card, options) {
    if (!card) {
      return;
    }

    var meta = normalizeOptions(options, card);
    if (!meta.playerName) {
      return;
    }

    clearTimers(card);
    finishRedCard(card);

    if (window.gameCardYellowCard && window.gameCardYellowCard.cancel) {
      window.gameCardYellowCard.cancel(card);
    }

    ensureRedCardLayer(card, meta);
    card.style.setProperty('--red-card-duration', (RED_CARD_ANIM_MS / 1000) + 's');
    card.style.setProperty('--red-card-name-duration', (TOTAL_MS / 1000) + 's');
    card.classList.remove('game-card--red-card');
    void card.offsetWidth;
    card.classList.add('game-card--red-card');

    var endTimer = window.setTimeout(function () {
      finishRedCard(card);
    }, TOTAL_MS);

    redCardTimers.set(card, { endTimer: endTimer });
  }

  window.gameCardRedCard = {
    play: playRedCard,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--red-card'));
    },
    cancel: finishRedCard
  };
})();

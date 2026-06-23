(function () {
  var STRIKEOUT_ANIM_MS = 6000;
  var GLYPH_FADE_RATIO = 0.72;
  var NAME_HOLD_MS = 5000;
  var NAME_FADE_MS = 700;

  var GLYPH_FADE_AT_MS = Math.round(STRIKEOUT_ANIM_MS * GLYPH_FADE_RATIO);
  var TOTAL_MS = GLYPH_FADE_AT_MS + NAME_HOLD_MS + NAME_FADE_MS;

  var strikeoutTimers = new WeakMap();

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function normalizeOptions(options, card) {
    if (!options) {
      return { playerName: '', side: null, teamAbbr: '', looking: false };
    }
    if (typeof options === 'string') {
      return { playerName: options, side: null, teamAbbr: '', looking: false };
    }
    var side = options.side || null;
    var teamAbbr = options.teamAbbr || options.abbr || '';
    if (!teamAbbr && side && card) {
      teamAbbr = teamAbbrFromCard(card, side);
    }
    var looking = Boolean(
      options.looking ||
      options.lookingStrikeout ||
      options.type === 'looking' ||
      options.strikeoutType === 'looking'
    );
    return {
      playerName: options.playerName || options.player || '',
      side: side,
      teamAbbr: teamAbbr,
      looking: looking
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
    var kClass = 'game-card-strikeout__k';
    if (meta.looking) {
      kClass += ' game-card-strikeout__k--looking';
    }
    return (
      '<span class="game-card-strikeout__flash" aria-hidden="true"></span>' +
      '<span class="game-card-strikeout__glyph" aria-hidden="true">' +
        '<span class="' + kClass + '" aria-hidden="true">K</span>' +
      '</span>' +
      '<span class="game-card-strikeout__player" aria-hidden="true">' +
        buildPlayerLabelHtml(meta, 'game-card-strikeout__player-name', 'game-card-strikeout__player-abbr') +
      '</span>'
    );
  }

  function ensureStrikeoutLayer(card, meta) {
    var layer = card.querySelector('.game-card-strikeout-layer');
    if (layer) {
      layer.remove();
    }
    layer = document.createElement('span');
    layer.className = 'game-card-strikeout-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = buildLayerHtml(meta);
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function clearTimers(card) {
    var timers = strikeoutTimers.get(card);
    if (!timers) {
      return;
    }
    if (timers.endTimer) {
      clearTimeout(timers.endTimer);
    }
    strikeoutTimers.delete(card);
  }

  function finishStrikeout(card) {
    if (!card) {
      return;
    }
    card.classList.remove('game-card--strikeout');
    var layer = card.querySelector('.game-card-strikeout-layer');
    if (layer) {
      layer.remove();
    }
    card.style.removeProperty('--strikeout-duration');
    card.style.removeProperty('--strikeout-name-duration');
    clearTimers(card);
  }

  function playStrikeout(card, options) {
    if (!card) {
      return;
    }

    var meta = normalizeOptions(options, card);
    if (!meta.playerName) {
      return;
    }

    clearTimers(card);
    finishStrikeout(card);

    if (window.gameCardWalk && window.gameCardWalk.cancel) {
      window.gameCardWalk.cancel(card);
    }

    ensureStrikeoutLayer(card, meta);
    card.style.setProperty('--strikeout-duration', (STRIKEOUT_ANIM_MS / 1000) + 's');
    card.style.setProperty('--strikeout-name-duration', (TOTAL_MS / 1000) + 's');
    card.classList.remove('game-card--strikeout');
    void card.offsetWidth;
    card.classList.add('game-card--strikeout');

    var endTimer = window.setTimeout(function () {
      finishStrikeout(card);
    }, TOTAL_MS);

    strikeoutTimers.set(card, { endTimer: endTimer });
  }

  window.gameCardStrikeout = {
    play: playStrikeout,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--strikeout'));
    },
    cancel: finishStrikeout
  };
})();

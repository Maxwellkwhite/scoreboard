(function () {
  var WALK_ANIM_MS = 6000;
  var GLYPH_FADE_RATIO = 0.72;
  var NAME_HOLD_MS = 5000;
  var NAME_FADE_MS = 700;

  var GLYPH_FADE_AT_MS = Math.round(WALK_ANIM_MS * GLYPH_FADE_RATIO);
  var TOTAL_MS = GLYPH_FADE_AT_MS + NAME_HOLD_MS + NAME_FADE_MS;

  var walkTimers = new WeakMap();

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
      '<span class="game-card-walk__flash" aria-hidden="true"></span>' +
      '<span class="game-card-walk__glyph" aria-hidden="true">' +
        '<span class="game-card-walk__bb" aria-hidden="true">BB</span>' +
      '</span>' +
      '<span class="game-card-walk__player" aria-hidden="true">' +
        buildPlayerLabelHtml(meta, 'game-card-walk__player-name', 'game-card-walk__player-abbr') +
      '</span>'
    );
  }

  function ensureWalkLayer(card, meta) {
    var layer = card.querySelector('.game-card-walk-layer');
    if (layer) {
      layer.remove();
    }
    layer = document.createElement('span');
    layer.className = 'game-card-walk-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = buildLayerHtml(meta);
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function clearTimers(card) {
    var timers = walkTimers.get(card);
    if (!timers) {
      return;
    }
    if (timers.endTimer) {
      clearTimeout(timers.endTimer);
    }
    walkTimers.delete(card);
  }

  function finishWalk(card) {
    if (!card) {
      return;
    }
    card.classList.remove('game-card--walk');
    var layer = card.querySelector('.game-card-walk-layer');
    if (layer) {
      layer.remove();
    }
    card.style.removeProperty('--walk-duration');
    card.style.removeProperty('--walk-name-duration');
    clearTimers(card);
  }

  function playWalk(card, options) {
    if (!card) {
      return;
    }

    var meta = normalizeOptions(options, card);
    if (!meta.playerName) {
      return;
    }

    if (window.gameCardStrikeout && window.gameCardStrikeout.cancel) {
      window.gameCardStrikeout.cancel(card);
    }

    clearTimers(card);
    finishWalk(card);

    ensureWalkLayer(card, meta);
    card.style.setProperty('--walk-duration', (WALK_ANIM_MS / 1000) + 's');
    card.style.setProperty('--walk-name-duration', (TOTAL_MS / 1000) + 's');
    card.classList.remove('game-card--walk');
    void card.offsetWidth;
    card.classList.add('game-card--walk');

    var endTimer = window.setTimeout(function () {
      finishWalk(card);
    }, TOTAL_MS);

    walkTimers.set(card, { endTimer: endTimer });
  }

  window.gameCardWalk = {
    play: playWalk,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--walk'));
    },
    cancel: finishWalk
  };
})();

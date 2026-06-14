(function () {
  var GAME_END_MS = 12000;

  var endTimers = new WeakMap();
  var fireworkTimers = new WeakMap();

  var FIREWORK_SHOWS = [
    { x: 18, y: 72, delay: 300, count: 18, scale: 1, palette: 'mixed' },
    { x: 78, y: 68, delay: 1200, count: 20, scale: 1.05, palette: 'mixed' },
    { x: 48, y: 28, delay: 2100, count: 22, scale: 1.15, palette: 'winner' },
    { x: 28, y: 42, delay: 3000, count: 16, scale: 0.95, palette: 'mixed' },
    { x: 72, y: 38, delay: 3900, count: 18, scale: 1, palette: 'mixed' },
    { x: 52, y: 58, delay: 4800, count: 24, scale: 1.2, palette: 'winner' },
    { x: 14, y: 34, delay: 5700, count: 16, scale: 0.9, palette: 'mixed' },
    { x: 86, y: 52, delay: 6600, count: 18, scale: 1, palette: 'mixed' },
    { x: 38, y: 22, delay: 7500, count: 26, scale: 1.25, palette: 'winner' },
    { x: 62, y: 48, delay: 8400, count: 28, scale: 1.35, palette: 'winner' }
  ];

  function teamColor(team) {
    return (team && (team.win_color || team.color)) || null;
  }

  function winnerSide(game) {
    if (!game) {
      return null;
    }
    if (game.away && game.away.winner) {
      return 'away';
    }
    if (game.home && game.home.winner) {
      return 'home';
    }
    if (game.away && game.home && game.away.score != null && game.home.score != null) {
      if (game.away.score > game.home.score) {
        return 'away';
      }
      if (game.home.score > game.away.score) {
        return 'home';
      }
    }
    return null;
  }

  function uniqueColors(list) {
    var seen = {};
    var out = [];
    list.forEach(function (color) {
      if (!color) {
        return;
      }
      var key = String(color).toLowerCase();
      if (seen[key]) {
        return;
      }
      seen[key] = true;
      out.push(color);
    });
    return out;
  }

  function teamColors(team) {
    return uniqueColors([
      team && team.color,
      team && team.alternate_color,
      team && team.win_color
    ]);
  }

  function runMargin(game) {
    if (!game) {
      return 0;
    }
    var away = game.away && game.away.score != null ? Number(game.away.score) : 0;
    var home = game.home && game.home.score != null ? Number(game.home.score) : 0;
    return Math.abs(away - home);
  }

  function intensityForGame(game) {
    var margin = runMargin(game);
    if (margin <= 1) {
      return 1;
    }
    if (margin <= 3) {
      return 0.82;
    }
    if (margin <= 5) {
      return 0.62;
    }
    return 0.45;
  }

  function buildMetaFromGame(game) {
    var side = winnerSide(game);
    var winner = side && game[side] ? game[side] : null;
    var away = game.away || {};
    var home = game.home || {};
    return {
      winnerSide: side,
      mixedColors: uniqueColors(
        teamColors(away).concat(teamColors(home))
      ),
      winnerColors: teamColors(winner),
      intensity: intensityForGame(game)
    };
  }

  function readTeamColorsFromRow(row) {
    if (!row) {
      return [];
    }
    var primary = row.style.getPropertyValue('--team-color').trim();
    return uniqueColors([primary]);
  }

  function extractMetaFromCard(card) {
    var awayRow = card.querySelector('.game-card-team--away');
    var homeRow = card.querySelector('.game-card-team--home');
    var awayScore = awayRow ? parseInt(awayRow.querySelector('.game-card-score').textContent, 10) : 0;
    var homeScore = homeRow ? parseInt(homeRow.querySelector('.game-card-score').textContent, 10) : 0;
    if (isNaN(awayScore)) awayScore = 0;
    if (isNaN(homeScore)) homeScore = 0;

    var side = null;
    if (awayScore > homeScore) {
      side = 'away';
    } else if (homeScore > awayScore) {
      side = 'home';
    } else if (awayRow && awayRow.classList.contains('game-card-team--winner')) {
      side = 'away';
    } else if (homeRow && homeRow.classList.contains('game-card-team--winner')) {
      side = 'home';
    }

    var awayColors = readTeamColorsFromRow(awayRow);
    var homeColors = readTeamColorsFromRow(homeRow);
    var winnerRow = side === 'home' ? homeRow : awayRow;

    return {
      winnerSide: side,
      mixedColors: uniqueColors(awayColors.concat(homeColors)),
      winnerColors: readTeamColorsFromRow(winnerRow),
      intensity: intensityForGame({ away: { score: awayScore }, home: { score: homeScore } })
    };
  }

  function pickColor(colors, index) {
    if (!colors.length) {
      return '#ffffff';
    }
    return colors[index % colors.length];
  }

  function spawnFirework(container, show, colors, winnerColors) {
    var palette = show.palette === 'winner' && winnerColors.length
      ? winnerColors
      : colors;
    if (!palette.length) {
      palette = ['#ffffff'];
    }

    var shell = document.createElement('span');
    shell.className = 'game-card-firework';
    shell.style.left = show.x + '%';
    shell.style.top = show.y + '%';
    shell.style.setProperty('--fw-scale', String(show.scale));

    var rocket = document.createElement('span');
    rocket.className = 'game-card-firework__rocket';
    rocket.style.background = pickColor(palette, 0);
    rocket.style.boxShadow = '0 0 8px ' + pickColor(palette, 0);
    shell.appendChild(rocket);

    var flash = document.createElement('span');
    flash.className = 'game-card-firework__flash';
    shell.appendChild(flash);

    var count = Math.max(12, Math.round(show.count * (show.scale || 1)));
    for (var i = 0; i < count; i += 1) {
      var particle = document.createElement('span');
      var streak = i % 4 === 0;
      particle.className = 'game-card-firework__particle' +
        (streak ? ' game-card-firework__particle--streak' : '');
      var angle = (360 / count) * i + ((i * 17) % 11) - 5;
      var dist = (28 + (i % 6) * 7 + (show.scale || 1) * 10);
      var color = pickColor(palette, i + (streak ? 1 : 0));
      particle.style.setProperty('--fw-angle', angle + 'deg');
      particle.style.setProperty('--fw-dist', dist + 'px');
      particle.style.setProperty('--fw-color', color);
      particle.style.background = color;
      particle.style.boxShadow = streak
        ? '0 0 10px ' + color
        : '0 0 6px ' + color + ', 0 0 12px ' + color;
      shell.appendChild(particle);
    }

    for (var j = 0; j < 8; j += 1) {
      var ember = document.createElement('span');
      ember.className = 'game-card-firework__ember';
      var emberAngle = j * 45 + 10;
      var emberDist = 12 + (j % 3) * 8;
      var emberColor = pickColor(palette, j + 2);
      ember.style.setProperty('--fw-angle', emberAngle + 'deg');
      ember.style.setProperty('--fw-dist', emberDist + 'px');
      ember.style.setProperty('--fw-color', emberColor);
      ember.style.background = emberColor;
      ember.style.boxShadow = '0 0 5px ' + emberColor;
      shell.appendChild(ember);
    }

    container.appendChild(shell);
    shell.addEventListener('animationend', function () {
      shell.remove();
    });
  }

  function scheduleFireworks(container, meta) {
    var intensity = meta.intensity || 0.7;
    var showCount = Math.max(3, Math.round(FIREWORK_SHOWS.length * intensity));
    var timers = [];

    FIREWORK_SHOWS.slice(0, showCount).forEach(function (show) {
      var timer = setTimeout(function () {
        spawnFirework(container, show, meta.mixedColors, meta.winnerColors);
      }, show.delay);
      timers.push(timer);
    });

    return timers;
  }

  function buildLayerHtml() {
    return (
      '<span class="game-card-game-end__sky"></span>' +
      '<span class="game-card-game-end__fireworks"></span>' +
      '<span class="game-card-game-end__ribbon">' +
        '<span class="game-card-game-end__ribbon-text">Final</span>' +
      '</span>'
    );
  }

  function ensureEndLayer(card) {
    var layer = card.querySelector('.game-card-game-end-layer');
    if (layer) {
      layer.remove();
    }
    layer = document.createElement('span');
    layer.className = 'game-card-game-end-layer';
    layer.setAttribute('aria-hidden', 'true');
    layer.innerHTML = buildLayerHtml();
    card.insertBefore(layer, card.firstChild);
    return layer;
  }

  function clearFireworkTimers(card) {
    var timers = fireworkTimers.get(card);
    if (timers) {
      timers.forEach(clearTimeout);
      fireworkTimers.delete(card);
    }
  }

  function playGameEnd(card, game) {
    if (!card) {
      return;
    }

    var meta = game ? buildMetaFromGame(game) : extractMetaFromCard(card);
    if (!meta.winnerSide || !meta.mixedColors.length) {
      return;
    }

    clearFireworkTimers(card);

    var layer = ensureEndLayer(card);
    var fireworksRoot = layer.querySelector('.game-card-game-end__fireworks');
    if (!fireworksRoot) {
      return;
    }

    card.style.setProperty('--game-end-duration', (GAME_END_MS / 1000) + 's');
    card.classList.remove('game-card--game-end');
    void card.offsetWidth;
    card.classList.add('game-card--game-end');

    fireworkTimers.set(card, scheduleFireworks(fireworksRoot, meta));

    var prev = endTimers.get(card);
    if (prev) {
      clearTimeout(prev);
    }

    var timer = setTimeout(function () {
      card.classList.remove('game-card--game-end');
      clearFireworkTimers(card);
      if (layer.parentNode) {
        layer.remove();
      }
      card.style.removeProperty('--game-end-duration');
      endTimers.delete(card);
    }, GAME_END_MS);

    endTimers.set(card, timer);
  }

  window.gameCardGameEnd = {
    play: playGameEnd,
    isActive: function (card) {
      return Boolean(card && card.classList.contains('game-card--game-end'));
    }
  };
})();

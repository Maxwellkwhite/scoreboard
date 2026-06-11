(function () {
  var todayPanel = document.getElementById('today-panel');
  var todayGamesGrid = document.getElementById('today-games');
  var liveHint = document.getElementById('live-hint');
  var pollUrl = document.body.getAttribute('data-today-api');
  var activeDay = 'today';
  var pollTimer = null;
  var POLL_MS_LIVE = 15000;
  var POLL_MS_IDLE = 30000;
  var lastScores = {};

  if (!pollUrl || !todayGamesGrid) {
    return;
  }

  function formatPreGameTime(el) {
    var iso = el.getAttribute('data-start-time');
    if (!iso) return;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return;
    el.textContent = d.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit'
    });
  }

  function outsLabel(outs) {
    return outs + ' out' + (outs === 1 ? '' : 's');
  }

  function scoreForTeam(game, team) {
    if (game.status_state === 'pre') {
      return '—';
    }
    if (team.score === null || team.score === undefined) {
      return '—';
    }
    return String(team.score);
  }

  function battingTeamColor(game) {
    var side = game.batting_side;
    if (!side || !game[side]) return null;
    var team = game[side];
    return team.win_color || team.color || null;
  }

  function pulseScoreElement(scoreEl, team) {
    var color = team && (team.win_color || team.color);
    if (color) {
      scoreEl.style.setProperty('--score-pulse-color', color);
    }
    scoreEl.classList.remove('game-card-score--pulse');
    void scoreEl.offsetWidth;
    scoreEl.classList.add('game-card-score--pulse');
  }

  function pulseGameCard(card) {
    card.classList.remove('game-card--score-changed');
    void card.offsetWidth;
    card.classList.add('game-card--score-changed');
  }

  function applyBattingTheme(card, game) {
    var pill = card.querySelector('.status-pill');
    var color = battingTeamColor(game);

    if (game.status_state === 'in' && color) {
      card.style.setProperty('--batting-team-color', color);
      if (pill) pill.classList.add('status-pill--batting-team');
    } else {
      card.style.removeProperty('--batting-team-color');
      if (pill) pill.classList.remove('status-pill--batting-team');
    }
  }

  function applyGameToCard(card, game) {
    card.className = 'game-card game-card--' + game.status_state + ' game-card--link';
    card.setAttribute('data-game-id', game.id);
    card.setAttribute('href', '/game/' + game.id);

    var statusWrap = card.querySelector('.game-card-status');
    var pill = card.querySelector('.status-pill');
    if (!pill || !statusWrap) return;

    pill.className = 'status-pill status-pill--' + game.status_state;
    if (game.status_state === 'pre' && game.start_time) {
      pill.setAttribute('data-start-time', game.start_time);
      formatPreGameTime(pill);
    } else {
      pill.removeAttribute('data-start-time');
      pill.textContent = game.status_detail || '';
    }

    var countEl = card.querySelector('.game-card-count');
    if (game.status_state === 'in' && game.balls !== null && game.balls !== undefined) {
      if (!countEl) {
        countEl = document.createElement('span');
        countEl.className = 'game-card-count';
        statusWrap.appendChild(countEl);
      }
      countEl.textContent = game.balls + '-' + game.strikes + ', ' + outsLabel(game.outs);
    } else if (countEl) {
      countEl.remove();
    }

    var teamEls = card.querySelectorAll('.game-card-team');
    var sides = [
      { el: teamEls[0], team: game.away, side: 'away' },
      { el: teamEls[1], team: game.home, side: 'home' }
    ];

    var awayScore = scoreForTeam(game, game.away);
    var homeScore = scoreForTeam(game, game.home);
    var prevScores = lastScores[String(game.id)];
    var scoreChanged = false;

    sides.forEach(function (entry) {
      if (!entry.el || !entry.team) return;
      entry.el.className = 'game-card-team game-card-team--' + entry.side +
        (entry.team.winner ? ' game-card-team--winner' : '');
      var scoreEl = entry.el.querySelector('.game-card-score');
      if (!scoreEl) return;

      var newScore = entry.side === 'away' ? awayScore : homeScore;
      if (prevScores) {
        var oldScore = entry.side === 'away' ? prevScores.away : prevScores.home;
        if (oldScore !== newScore && newScore !== '—') {
          scoreChanged = true;
          pulseScoreElement(scoreEl, entry.team);
        }
      }

      scoreEl.textContent = newScore;
    });

    lastScores[String(game.id)] = { away: awayScore, home: homeScore };

    if (scoreChanged) {
      pulseGameCard(card);
    }

    applyBattingTheme(card, game);
  }

  function updateGameCards(games) {
    var gamesById = {};
    games.forEach(function (game) {
      gamesById[String(game.id)] = game;
    });

    todayGamesGrid.querySelectorAll('.game-card').forEach(function (card) {
      var id = card.getAttribute('data-game-id');
      if (gamesById[id]) {
        applyGameToCard(card, gamesById[id]);
      }
    });
  }

  function schedulePoll(ms) {
    if (pollTimer) {
      clearInterval(pollTimer);
    }
    pollTimer = setInterval(refreshTodayScores, ms);
  }

  function isTodayVisible() {
    return activeDay === 'today' && todayPanel && !todayPanel.hidden;
  }

  function refreshTodayScores() {
    if (!isTodayVisible()) {
      return;
    }

    fetch(pollUrl, { cache: 'no-store' })
      .then(function (response) { return response.json(); })
      .then(function (data) {
        if (!data.games) return;

        if (liveHint) {
          liveHint.hidden = !data.has_live;
        }

        updateGameCards(data.games);
        schedulePoll(data.has_live ? POLL_MS_LIVE : POLL_MS_IDLE);
      })
      .catch(function () {});
  }

  window.scoreboardLive = {
    setActiveDay: function (day) {
      activeDay = day;
      if (day === 'today') {
        refreshTodayScores();
      } else if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
    }
  };

  refreshTodayScores();
})();

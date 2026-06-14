(function () {
  var todayPanel = document.getElementById('today-panel');
  var todayGamesGrid = document.getElementById('today-games');
  var pollUrl = document.body.getAttribute('data-today-api');
  function getInitialDay() {
    var hash = (location.hash || '').replace(/^#/, '').toLowerCase();
    if (hash === 'yesterday' || hash === 'standings') {
      return hash;
    }
    return 'today';
  }

  var activeDay = getInitialDay();
  var pollTimer = null;
  var POLL_MS_LIVE = 15000;
  var POLL_MS_IDLE = 30000;
  var lastScores = {};
  var lastStatus = {};

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

  function battingTeam(game) {
    var side = game.batting_side;
    if (!side || !game[side]) return null;
    return game[side];
  }

  function battingTeamColor(game) {
    var team = battingTeam(game);
    if (!team) return null;
    return team.win_color || team.color || null;
  }

  function flashScoreOnCard(card, side, team) {
    if (window.gameCardScoreFlash) {
      window.gameCardScoreFlash.flash(card, side, team);
    }
  }

  function applyBattingTheme(card, game) {
    var pill = card.querySelector('.status-pill');
    var team = battingTeam(game);
    var borderColor = battingTeamColor(game);

    if (game.status_state === 'in' && team) {
      if (window.teamBattingPill) {
        window.teamBattingPill.apply(card, team, borderColor);
      } else if (borderColor) {
        card.style.setProperty('--batting-team-color', borderColor);
      }
      if (pill) pill.classList.add('status-pill--batting-team');
    } else {
      if (window.teamBattingPill) {
        window.teamBattingPill.clear(card);
      } else {
        card.style.removeProperty('--batting-team-color');
        card.style.removeProperty('--batting-team-bg');
        card.style.removeProperty('--batting-team-text');
      }
      if (pill) pill.classList.remove('status-pill--batting-team');
    }
  }

  function applyGameToCard(card, game) {
    var gameId = String(game.id);
    var prevStatus = lastStatus[gameId];
    var flashActive = window.gameCardScoreFlash &&
      window.gameCardScoreFlash.isActive(card);
    var packActive = window.gameCardPackOpen &&
      window.gameCardPackOpen.isActive(card);
    var gameEndActive = window.gameCardGameEnd &&
      window.gameCardGameEnd.isActive(card);
    card.className = 'game-card game-card--' + game.status_state + ' game-card--link';
    if (flashActive) {
      card.classList.add('game-card--score-flash');
    }
    if (packActive) {
      card.classList.add('game-card--pack-open');
    }
    if (gameEndActive) {
      card.classList.add('game-card--game-end');
    }
    card.setAttribute('data-game-id', game.id);
    card.setAttribute('data-game-href', '/game/' + game.id);
    card.setAttribute('role', 'link');
    card.setAttribute('tabindex', '0');

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

    var hasWinner = Boolean(game.away && game.away.winner) || Boolean(game.home && game.home.winner);

    sides.forEach(function (entry) {
      if (!entry.el || !entry.team) return;
      var teamClass = 'game-card-team game-card-team--' + entry.side;
      if (entry.team.winner) {
        teamClass += ' game-card-team--winner';
      } else if (game.status_state === 'post' && hasWinner) {
        teamClass += ' game-card-team--loser';
      }
      var scoredActive = entry.el.classList.contains('game-card-team--scored');
      entry.el.className = teamClass;
      if (scoredActive) {
        entry.el.classList.add('game-card-team--scored');
      }
      entry.el.style.setProperty(
        '--team-color',
        entry.team.win_color || entry.team.color || '#1a2332'
      );
      var scoreEl = entry.el.querySelector('.game-card-score');
      if (!scoreEl) return;

      var newScore = entry.side === 'away' ? awayScore : homeScore;
      if (prevScores) {
        var oldScore = entry.side === 'away' ? prevScores.away : prevScores.home;
        if (oldScore !== newScore && newScore !== '—') {
          scoreEl.textContent = newScore;
          flashScoreOnCard(card, entry.side, entry.team);
          return;
        }
      }

      scoreEl.textContent = newScore;
    });

    lastScores[gameId] = { away: awayScore, home: homeScore };

    if (prevStatus === 'pre' && game.status_state === 'in' && window.gameCardPackOpen) {
      window.gameCardPackOpen.play(card, game);
    }
    if (prevStatus && prevStatus !== 'post' && game.status_state === 'post' && window.gameCardGameEnd) {
      window.gameCardGameEnd.play(card, game);
    }
    lastStatus[gameId] = game.status_state;

    applyBattingTheme(card, game);
  }

  var statusSortOrder = { in: 0, pre: 1, post: 2 };

  function compareGames(a, b) {
    var aPriority = statusSortOrder[a.status_state];
    var bPriority = statusSortOrder[b.status_state];
    if (aPriority === undefined) aPriority = 1;
    if (bPriority === undefined) bPriority = 1;
    if (aPriority !== bPriority) {
      return aPriority - bPriority;
    }
    return String(a.start_time || '').localeCompare(String(b.start_time || ''));
  }

  function reorderGameCards(games) {
    games.slice().sort(compareGames).forEach(function (game) {
      var card = todayGamesGrid.querySelector('[data-game-id="' + game.id + '"]');
      if (card) {
        todayGamesGrid.appendChild(card);
      }
    });
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

    reorderGameCards(games);
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

  if (activeDay === 'today') {
    refreshTodayScores();
  }

  function navigateGameCard(card) {
    var href = card.getAttribute('data-game-href');
    if (href) {
      window.location.href = href;
    }
  }

  document.addEventListener('click', function (event) {
    if (event.target.closest('.team-link')) {
      return;
    }
    var card = event.target.closest('.game-card--link, .game-mini-card--link');
    if (card) {
      navigateGameCard(card);
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') {
      return;
    }
    if (event.target.closest('.team-link')) {
      return;
    }
    var card = event.target.closest('.game-card--link, .game-mini-card--link');
    if (!card) {
      return;
    }
    if (event.key === ' ') {
      event.preventDefault();
    }
    navigateGameCard(card);
  });
})();

(function () {
  var todayPanel = document.getElementById('today-panel');
  var todayGamesGrid = document.getElementById('today-games');
  var pollUrl = document.body.getAttribute('data-today-api');
  var matchHrefPrefix = document.body.getAttribute('data-match-href-prefix') || '/world-cup/match/';

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
  var lastGamesList = [];

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

  function scoreForTeam(game, team) {
    if (game.status_state === 'pre') {
      return '—';
    }
    if (team.score === null || team.score === undefined) {
      return '—';
    }
    return String(team.score);
  }

  function numericScore(value) {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    var normalized = String(value).trim();
    if (normalized === '—' || normalized === '–' || normalized === '-') {
      return null;
    }
    var parsed = Number(normalized);
    return isNaN(parsed) ? null : parsed;
  }

  function shouldFlashScoreChange(oldScore, newScore, options) {
    options = options || {};
    if (options.gameStarting) {
      return false;
    }
    var oldNum = numericScore(oldScore);
    var newNum = numericScore(newScore);
    if (newNum === null || oldNum === null) {
      return false;
    }
    return newNum > oldNum;
  }

  function flashScoreOnCard(card, side, team) {
    if (window.gameCardScoreFlash) {
      window.gameCardScoreFlash.flash(card, side, team);
    }
  }

  function applyGameToCard(card, game) {
    var gameId = String(game.id);
    var prevStatus = lastStatus[gameId];
    var flashActive = window.gameCardScoreFlash &&
      window.gameCardScoreFlash.isActive(card);
    var matchStartActive = window.gameCardMatchStart &&
      window.gameCardMatchStart.isActive(card);
    var redCardActive = window.gameCardRedCard &&
      window.gameCardRedCard.isActive(card);
    var yellowCardActive = window.gameCardYellowCard &&
      window.gameCardYellowCard.isActive(card);
    var gameEndActive = window.gameCardGameEnd &&
      window.gameCardGameEnd.isActive(card);

    card.className = 'game-card game-card--' + game.status_state + ' game-card--link';
    if (flashActive) {
      card.classList.add('game-card--score-flash');
    }
    if (matchStartActive) {
      card.classList.add('game-card--match-start');
    }
    if (redCardActive) {
      card.classList.add('game-card--red-card');
    }
    if (yellowCardActive) {
      card.classList.add('game-card--yellow-card');
    }
    if (gameEndActive) {
      card.classList.add('game-card--game-end');
    }
    card.setAttribute('data-game-id', game.id);
    card.setAttribute('data-game-href', matchHrefPrefix + game.id);
    card.setAttribute('role', 'link');
    card.setAttribute('tabindex', '0');

    var pill = card.querySelector('.status-pill');
    if (!pill) return;

    pill.className = 'status-pill status-pill--' + game.status_state;
    if (game.status_state === 'pre' && game.start_time) {
      pill.setAttribute('data-start-time', game.start_time);
      formatPreGameTime(pill);
    } else {
      pill.removeAttribute('data-start-time');
      pill.textContent = game.status_detail || '';
    }

    var teamEls = card.querySelectorAll('.game-card-team');
    var sides = [
      { el: teamEls[0], team: game.away, side: 'away' },
      { el: teamEls[1], team: game.home, side: 'home' }
    ];

    var awayScore = scoreForTeam(game, game.away);
    var homeScore = scoreForTeam(game, game.home);
    var prevScores = lastScores[gameId];
    var gameStarting = prevStatus === 'pre' && game.status_state === 'in';
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
        if (shouldFlashScoreChange(oldScore, newScore, { gameStarting: gameStarting })) {
          scoreEl.textContent = newScore;
          flashScoreOnCard(card, entry.side, entry.team);
          return;
        }
      }

      scoreEl.textContent = newScore;
    });

    lastScores[gameId] = { away: awayScore, home: homeScore };

    if (prevStatus === 'pre' && game.status_state === 'in' && window.gameCardMatchStart) {
      window.gameCardMatchStart.play(card, game);
    }
    if (prevStatus && prevStatus !== 'post' && game.status_state === 'post' && window.gameCardGameEnd) {
      window.gameCardGameEnd.play(card, game);
    }
    if (window.gameCardCardEvents) {
      window.gameCardCardEvents.apply(card, game, gameId);
    }
    lastStatus[gameId] = game.status_state;
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

  function isGameEndPinned(card) {
    return window.gameCardGameEnd && window.gameCardGameEnd.isActive(card);
  }

  function reorderGameCards(games) {
    var currentCards = Array.prototype.slice.call(
      todayGamesGrid.querySelectorAll('.game-card')
    );
    var pinnedIds = {};
    currentCards.forEach(function (card) {
      if (isGameEndPinned(card)) {
        pinnedIds[card.getAttribute('data-game-id')] = true;
      }
    });

    var sortableGames = games.filter(function (game) {
      return !pinnedIds[String(game.id)];
    }).sort(compareGames);

    var sortableCards = sortableGames.map(function (game) {
      return todayGamesGrid.querySelector('[data-game-id="' + game.id + '"]');
    }).filter(Boolean);

    var sortIdx = 0;
    var fragment = document.createDocumentFragment();

    currentCards.forEach(function (card) {
      var id = card.getAttribute('data-game-id');
      if (pinnedIds[id]) {
        fragment.appendChild(card);
        return;
      }
      if (sortIdx < sortableCards.length) {
        fragment.appendChild(sortableCards[sortIdx]);
        sortIdx += 1;
      }
    });

    while (sortIdx < sortableCards.length) {
      fragment.appendChild(sortableCards[sortIdx]);
      sortIdx += 1;
    }

    todayGamesGrid.appendChild(fragment);
  }

  function seedCardStateFromDom(card) {
    var gameId = card.getAttribute('data-game-id');
    if (!gameId || lastStatus[gameId] !== undefined) {
      return;
    }

    var statusMatch = card.className.match(/game-card--(pre|in|post)/);
    var awayEl = card.querySelector('.game-card-team--away .game-card-score');
    var homeEl = card.querySelector('.game-card-team--home .game-card-score');

    lastStatus[gameId] = statusMatch ? statusMatch[1] : 'pre';
    lastScores[gameId] = {
      away: awayEl ? awayEl.textContent.trim() : '—',
      home: homeEl ? homeEl.textContent.trim() : '—'
    };
  }

  function updateGameCards(games) {
    lastGamesList = games;
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

  if (window.gameCardGameEnd) {
    window.gameCardGameEnd.setOnComplete(function () {
      if (lastGamesList.length) {
        reorderGameCards(lastGamesList);
      }
    });
  }

  todayGamesGrid.querySelectorAll('.game-card').forEach(seedCardStateFromDom);

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
    var card = event.target.closest('.game-card--link');
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
    var card = event.target.closest('.game-card--link');
    if (!card) {
      return;
    }
    event.preventDefault();
    navigateGameCard(card);
  });
})();

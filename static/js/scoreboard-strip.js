(function () {
  'use strict';

  var POLL_MS_LIVE = 15000;
  var POLL_MS_IDLE = 30000;
  var pollTimer = null;

  function battingTeam(game) {
    if (!game || game.status_state !== 'in') return null;
    if (game.batting_side === 'away') return game.away;
    if (game.batting_side === 'home') return game.home;
    return null;
  }

  function battingTeamColor(game) {
    var team = battingTeam(game);
    return team ? (team.win_color || team.color || '#1a2332') : '';
  }

  function miniCardStatusLabel(game) {
    if (game.status_detail && /rain delay/i.test(game.status_detail)) {
      return 'Rain Delay';
    }
    return game.status_detail || '';
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

  function applyMiniCard(card, game) {
    var team = battingTeam(game);
    var borderColor = battingTeamColor(game);

    if (game.status_state === 'in' && team) {
      if (window.teamBattingPill) {
        window.teamBattingPill.apply(card, team, borderColor);
      } else if (borderColor) {
        card.style.setProperty('--batting-team-color', borderColor);
      }
    } else if (window.teamBattingPill) {
      window.teamBattingPill.clear(card);
    } else {
      card.style.removeProperty('--batting-team-color');
      card.style.removeProperty('--batting-team-bg');
      card.style.removeProperty('--batting-team-text');
    }

    card.className = 'game-mini-card game-mini-card--' + game.status_state + ' game-mini-card--link';
    card.removeAttribute('aria-current');
    card.setAttribute('role', 'link');
    card.setAttribute('tabindex', '0');
    card.setAttribute('data-game-href', '/game/' + game.id);

    var pill = card.querySelector('.status-pill');
    if (pill) {
      pill.className = 'status-pill status-pill--' + game.status_state;
      if (game.status_state === 'in' && team) {
        pill.classList.add('status-pill--batting-team');
      }
      if (game.status_state === 'pre' && game.start_time) {
        pill.setAttribute('data-start-time', game.start_time);
        formatPreGameTime(pill);
      } else {
        pill.removeAttribute('data-start-time');
        pill.textContent = miniCardStatusLabel(game);
      }
    }

    var hasWinner = Boolean(game.away && game.away.winner) ||
      Boolean(game.home && game.home.winner);
    var teamRows = card.querySelectorAll('.game-mini-card__team');
    var sides = [{ team: game.away }, { team: game.home }];

    sides.forEach(function (entry, index) {
      var sideTeam = entry.team;
      var row = teamRows[index];
      if (!row || !sideTeam) return;

      var rowClass = 'game-mini-card__team';
      if (sideTeam.winner) {
        rowClass += ' game-mini-card__team--winner';
      } else if (game.status_state === 'post' && hasWinner) {
        rowClass += ' game-mini-card__team--loser';
      }
      row.className = rowClass;
      row.style.setProperty(
        '--team-color',
        sideTeam.win_color || sideTeam.color || '#1a2332'
      );

      var scoreEl = row.querySelector('.game-mini-card__score');
      if (scoreEl) {
        scoreEl.textContent = game.status_state === 'pre'
          ? '—'
          : (sideTeam.score != null ? sideTeam.score : '0');
      }
    });
  }

  function updateStripGames(games) {
    var track = document.querySelector('.game-detail-live-strip__track');
    if (!track || !games || !games.length) return;

    var gamesById = {};
    games.forEach(function (game) {
      gamesById[String(game.id)] = game;
    });

    track.querySelectorAll('.game-mini-card[data-game-id]').forEach(function (card) {
      var id = card.getAttribute('data-game-id');
      if (gamesById[id]) {
        applyMiniCard(card, gamesById[id]);
      }
    });
  }

  function initStripCardNavigation() {
    function navigateStripCard(card) {
      var href = card.getAttribute('data-game-href');
      if (href) {
        window.location.href = href;
      }
    }

    document.addEventListener('click', function (event) {
      if (event.target.closest('.team-link')) {
        return;
      }
      var card = event.target.closest('.game-mini-card--link');
      if (card) {
        navigateStripCard(card);
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') {
        return;
      }
      if (event.target.closest('.team-link')) {
        return;
      }
      var card = event.target.closest('.game-mini-card--link');
      if (!card) {
        return;
      }
      if (event.key === ' ') {
        event.preventDefault();
      }
      navigateStripCard(card);
    });
  }

  function schedulePoll(ms) {
    if (pollTimer) {
      clearInterval(pollTimer);
    }
    pollTimer = setInterval(refreshTodayScores, ms);
  }

  function refreshTodayScores() {
    fetch('/api/mlb/scoreboard/today')
      .then(function (response) {
        if (!response.ok) throw new Error('scoreboard unavailable');
        return response.json();
      })
      .then(function (data) {
        updateStripGames(data.games || []);
        schedulePoll(data.has_live ? POLL_MS_LIVE : POLL_MS_IDLE);
      })
      .catch(function () {
        schedulePoll(POLL_MS_IDLE);
      });
  }

  if (!document.querySelector('.game-detail-live-strip-wrap')) {
    return;
  }

  initStripCardNavigation();
  schedulePoll(POLL_MS_IDLE);
  refreshTodayScores();
})();

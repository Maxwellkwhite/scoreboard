(function () {
  'use strict';

  var body = document.body;
  var apiUrl = body.getAttribute('data-game-api');
  var pollTimer = null;
  var POLL_MS_LIVE = 15000;
  var POLL_MS_FINAL = 60000;
  var POLL_MS_PREVIEW = 60000;
  var initialStatus = body.getAttribute('data-game-status') || '';

  if (!body.classList.contains('game-live-page')) {
    return;
  }

  var currentGameId = '';
  if (apiUrl) {
    var match = apiUrl.match(/\/match\/([^/]+)\/?$/);
    if (match) {
      currentGameId = match[1];
    }
  }

  function formatPreGameDateTime(el) {
    var iso = el.getAttribute('data-start-time');
    if (!iso) return;
    var d = new Date(iso);
    if (isNaN(d.getTime())) return;
    el.textContent = d.toLocaleString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit'
    });
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

  function miniCardStatusLabel(game) {
    return game.status_detail || '';
  }

  function applyMiniCard(card, game) {
    var isCurrent = String(game.id) === String(currentGameId);
    card.className = 'game-mini-card game-mini-card--' + game.status_state +
      (isCurrent ? ' game-mini-card--active' : ' game-mini-card--link');

    if (isCurrent) {
      card.setAttribute('aria-current', 'page');
      card.removeAttribute('role');
      card.removeAttribute('tabindex');
      card.removeAttribute('data-game-href');
    } else {
      card.removeAttribute('aria-current');
      card.setAttribute('role', 'link');
      card.setAttribute('tabindex', '0');
      card.setAttribute('data-game-href', '/world-cup/match/' + game.id);
    }

    var pill = card.querySelector('.status-pill');
    if (pill) {
      pill.className = 'status-pill status-pill--' + game.status_state;
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

  function applyTeamSide(el, team, game, side) {
    if (!el || !team) return;

    el.classList.remove('game-card-team--winner', 'game-card-team--loser');
    var hasWinner = Boolean(game.away && game.away.winner) ||
      Boolean(game.home && game.home.winner);
    if (team.winner) {
      el.classList.add('game-card-team--winner');
    } else if (game.status_state === 'post' && hasWinner) {
      el.classList.add('game-card-team--loser');
    }

    el.style.setProperty(
      '--team-color',
      team.win_color || team.color || '#1a2332'
    );
  }

  function initRosterToggle() {
    var container = document.getElementById('wc-preview-rosters');
    if (!container) return;

    container.querySelectorAll('.game-preview-rosters-toggle .player-panel-toggle__btn').forEach(function (btn) {
      if (btn.getAttribute('data-wc-roster-toggle-bound') === 'true') return;
      btn.setAttribute('data-wc-roster-toggle-bound', 'true');
      btn.addEventListener('click', function () {
        var side = btn.getAttribute('data-roster-side');
        if (!side) return;

        container.querySelectorAll('.game-preview-rosters-toggle .player-panel-toggle__btn').forEach(function (toggleBtn) {
          var isActive = toggleBtn.getAttribute('data-roster-side') === side;
          toggleBtn.classList.toggle('is-active', isActive);
          toggleBtn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        container.querySelectorAll('.game-preview-rosters-view').forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-roster-side') !== side;
        });
      });
    });
  }

  function initLineupToggle() {
    var container = document.getElementById('wc-lineup-panel');
    if (!container) return;

    container.querySelectorAll('.wc-lineup-toggle .player-panel-toggle__btn').forEach(function (btn) {
      if (btn.getAttribute('data-lineup-toggle-bound') === 'true') return;
      btn.setAttribute('data-lineup-toggle-bound', 'true');
      btn.addEventListener('click', function () {
        var side = btn.getAttribute('data-lineup-side');
        if (!side) return;

        container.querySelectorAll('.wc-lineup-toggle .player-panel-toggle__btn').forEach(function (toggleBtn) {
          var isActive = toggleBtn.getAttribute('data-lineup-side') === side;
          toggleBtn.classList.toggle('is-active', isActive);
          toggleBtn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        container.querySelectorAll('.wc-lineup-view').forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-lineup-side') !== side;
        });
      });
    });
  }

  function parseStatNumber(value) {
    if (value == null || value === '') return null;
    var num = parseFloat(String(value).replace('%', ''));
    return isNaN(num) ? null : num;
  }

  function updateTeamStats(teamBox) {
    if (!teamBox || !teamBox.length) return;
    var away = teamBox.find(function (row) { return row.home_away === 'away'; });
    var home = teamBox.find(function (row) { return row.home_away === 'home'; });
    if (!away || !home) return;

    document.querySelectorAll('[data-stat-away]').forEach(function (el) {
      var key = el.getAttribute('data-stat-away');
      if (key && away[key] != null) {
        el.textContent = away[key];
      }
    });
    document.querySelectorAll('[data-stat-home]').forEach(function (el) {
      var key = el.getAttribute('data-stat-home');
      if (key && home[key] != null) {
        el.textContent = home[key];
      }
    });

    document.querySelectorAll('.team-stats__row[data-stat-key]').forEach(function (row) {
      var key = row.getAttribute('data-stat-key');
      if (!key) return;
      var awayRaw = away[key];
      var homeRaw = home[key];
      var awayNum = parseStatNumber(awayRaw);
      var homeNum = parseStatNumber(homeRaw);
      var awayBar = row.querySelector('[data-stat-bar-away="' + key + '"]');
      var homeBar = row.querySelector('[data-stat-bar-home="' + key + '"]');
      if (awayNum == null || homeNum == null || !awayBar || !homeBar) return;
      var lowerIsBetter = key === 'foulsCommitted' || key === 'yellowCards' ||
        key === 'redCards' || key === 'offsides' || key === 'goalsConceded';
      var awayBarVal = lowerIsBetter ? homeNum : awayNum;
      var homeBarVal = lowerIsBetter ? awayNum : homeNum;
      var total = awayBarVal + homeBarVal;
      if (total <= 0) return;
      awayBar.style.width = ((awayBarVal / total) * 100).toFixed(1) + '%';
      homeBar.style.width = ((homeBarVal / total) * 100).toFixed(1) + '%';
    });
  }

  function formatFormDates() {
    document.querySelectorAll('.wc-form-list__date[data-start-time]').forEach(function (el) {
      var iso = el.getAttribute('data-start-time');
      if (!iso) return;
      var d = new Date(iso);
      if (isNaN(d.getTime())) return;
      el.textContent = d.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      });
    });
  }

  var lastEventCount = document.querySelectorAll('#wc-key-events .wc-timeline-feed__item').length;

  function applyLivePanels(game) {
    if (!game || !game.live) return;
    updateTeamStats(game.live.team_box);
    var eventCount = (game.live.key_events || []).length;
    if (game.status_state === 'in' && eventCount > lastEventCount) {
      window.location.reload();
    }
    lastEventCount = eventCount;
  }

  function applyGame(game) {
    if (!game) return;

    body.setAttribute('data-game-status', game.status_state || '');
    body.classList.toggle('game-preview-page', game.status_state === 'pre');

    var hero = document.getElementById('game-matchup');
    if (hero) {
      hero.className = 'game-card game-card--' + game.status_state + ' game-detail-hero';
    }

    var pill = document.getElementById('game-status-pill');
    if (pill) {
      pill.className = 'status-pill status-pill--' + game.status_state;
      if (game.status_state === 'pre' && game.start_time) {
        pill.setAttribute('data-start-time', game.start_time);
        formatPreGameDateTime(pill);
      } else {
        pill.removeAttribute('data-start-time');
        pill.textContent = game.status_detail || '';
      }
    }

    var matchupRow = document.querySelector('.game-detail-matchup-row');
    if (matchupRow) {
      matchupRow.classList.toggle('game-detail-matchup-row--no-scores', game.status_state === 'pre');
    }

    applyTeamSide(document.getElementById('game-team-away'), game.away, game, 'away');
    applyTeamSide(document.getElementById('game-team-home'), game.home, game, 'home');

    var awayScore = document.getElementById('game-away-score');
    var homeScore = document.getElementById('game-home-score');
    if (game.status_state !== 'pre') {
      if (awayScore && game.away) {
        awayScore.textContent = game.away.score != null ? game.away.score : '0';
      }
      if (homeScore && game.home) {
        homeScore.textContent = game.home.score != null ? game.home.score : '0';
      }
    }

    applyLivePanels(game);

    if (game.status_state !== initialStatus && initialStatus) {
      window.location.reload();
    }
  }

  function initDetailTabs() {
    var tabs = document.getElementById('game-detail-tabs');
    if (!tabs) return;

    var buttons = tabs.querySelectorAll('.game-detail-tab');
    var panels = document.querySelectorAll('.game-detail-panel');

    function panelFromHash() {
      var hash = (location.hash || '').replace(/^#/, '').toLowerCase();
      if (!hash) return null;
      for (var i = 0; i < buttons.length; i++) {
        if (buttons[i].getAttribute('data-panel') === hash) {
          return hash;
        }
      }
      return null;
    }

    function setPanelHash(panelId) {
      var nextHash = '#' + panelId;
      if (location.hash !== nextHash) {
        history.replaceState(null, '', nextHash);
      }
    }

    function showPanel(panelId) {
      buttons.forEach(function (btn) {
        var isActive = btn.getAttribute('data-panel') === panelId;
        btn.classList.toggle('is-active', isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
      panels.forEach(function (panel) {
        panel.hidden = panel.getAttribute('data-panel') !== panelId;
      });
    }

    function scrollToPanel(panelId) {
      var panel = document.querySelector('.game-detail-panel[data-panel="' + panelId + '"]');
      if (!panel || panel.hidden) return;
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var panelId = btn.getAttribute('data-panel');
        showPanel(panelId);
        setPanelHash(panelId);
        requestAnimationFrame(function () {
          scrollToPanel(panelId);
        });
      });
    });

    window.addEventListener('hashchange', function () {
      var panelId = panelFromHash();
      if (panelId) {
        showPanel(panelId);
      }
    });

    var initial = panelFromHash();
    if (initial) {
      showPanel(initial);
    } else {
      var active = tabs.querySelector('.game-detail-tab.is-active');
      if (active) {
        showPanel(active.getAttribute('data-panel'));
      }
    }
  }

  function initStripCardNavigation() {
    function navigateStripCard(card) {
      var href = card.getAttribute('data-game-href');
      if (href) {
        window.location.href = href;
      }
    }

    document.addEventListener('click', function (event) {
      var card = event.target.closest('.game-mini-card--link');
      if (card) {
        navigateStripCard(card);
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Enter' && event.key !== ' ') {
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
    pollTimer = setInterval(refreshGame, ms);
  }

  function refreshGame() {
    if (!apiUrl) return;

    fetch(apiUrl, { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('fetch failed');
        return response.json();
      })
      .then(function (data) {
        if (!data.game) return;
        applyGame(data.game);
        if (data.strip_games) {
          updateStripGames(data.strip_games);
        }
        schedulePoll(
          data.game.status_state === 'in'
            ? POLL_MS_LIVE
            : (data.game.status_state === 'pre' ? POLL_MS_PREVIEW : POLL_MS_FINAL)
        );
      })
      .catch(function () {});
  }

  initDetailTabs();
  initStripCardNavigation();
  initRosterToggle();
  initLineupToggle();
  formatFormDates();

  if (initialStatus === 'pre') {
    var statusPill = document.getElementById('game-status-pill');
    if (statusPill) formatPreGameDateTime(statusPill);
  }

  if (apiUrl) {
    refreshGame();
  }
})();

(function () {
  var body = document.body;
  var apiUrl = body.getAttribute('data-game-api');
  var pollTimer = null;
  var POLL_MS_LIVE = 15000;
  var POLL_MS_FINAL = 60000;

  if (!apiUrl || !body.classList.contains('game-live-page')) {
    return;
  }

  function outsLabel(outs) {
    return outs + ' out' + (outs === 1 ? '' : 's');
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value;
  }

  function setHidden(id, hidden) {
    var el = document.getElementById(id);
    if (el) el.hidden = hidden;
  }

  function renderPlayList(containerId, plays, scoringOnly) {
    var container = document.getElementById(containerId);
    if (!container) return;

    var items = (plays || []).filter(function (play) {
      return !scoringOnly || play.scoring;
    });

    if (!items.length) {
      container.innerHTML = '';
      var section = container.closest('.game-detail-section');
      if (section) section.hidden = true;
      return;
    }

    var section = container.closest('.game-detail-section');
    if (section) section.hidden = false;

    container.innerHTML = items.map(function (play) {
      var score = '';
      if (play.away_score !== null && play.away_score !== undefined &&
          play.home_score !== null && play.home_score !== undefined) {
        score = '<span class="play-feed-score">' + play.away_score + '-' + play.home_score + '</span>';
      }
      var period = play.period
        ? '<span class="play-feed-period">' + play.period + '</span>'
        : '<span></span>';
      var scoringClass = play.scoring ? ' play-feed-item--scoring' : '';
      return '<li class="play-feed-item' + scoringClass + '">' +
        period +
        '<span class="play-feed-text">' + play.text + '</span>' +
        score +
        '</li>';
    }).join('');
  }

  function renderLinescore(linescore) {
    var table = document.getElementById('game-linescore-table');
    if (!table || !linescore) return;

    var headerCells = ['<th></th>'];
    linescore.columns.forEach(function (col) {
      headerCells.push('<th>' + col.number + '</th>');
    });
    headerCells.push('<th>R</th>', '<th>H</th>', '<th>E</th>');

    function row(side) {
      var team = linescore[side];
      var cells = ['<th>' + linescore[side + '_abbr'] + '</th>'];
      linescore.columns.forEach(function (col) {
        cells.push('<td>' + col[side] + '</td>');
      });
      cells.push(
        '<td class="linescore-total">' + (team.runs != null ? team.runs : '0') + '</td>',
        '<td>' + team.hits + '</td>',
        '<td>' + team.errors + '</td>'
      );
      return '<tr>' + cells.join('') + '</tr>';
    }

    table.innerHTML =
      '<thead><tr>' + headerCells.join('') + '</tr></thead>' +
      '<tbody>' + row('away') + row('home') + '</tbody>';

    var section = document.getElementById('game-linescore-section');
    if (section) section.hidden = false;
  }

  function renderTeamBox(teamBox) {
    var container = document.getElementById('game-team-box');
    if (!container) return;

    if (!teamBox || !teamBox.length) {
      var section = document.getElementById('game-team-box-section');
      if (section) section.hidden = true;
      return;
    }

    var section = document.getElementById('game-team-box-section');
    if (section) section.hidden = false;

    container.innerHTML = teamBox.map(function (team) {
      var stats = [];
      if (team.batting_hits != null) stats.push(['Hits', team.batting_hits]);
      if (team.batting_runs != null) stats.push(['Runs', team.batting_runs]);
      if (team.batting_strikeouts != null) stats.push(['Strikeouts', team.batting_strikeouts]);
      if (team.batting_walks != null) stats.push(['Walks', team.batting_walks]);
      if (team.pitching_strikeouts != null) stats.push(['Pitcher K', team.pitching_strikeouts]);
      if (team.pitching_hits != null) stats.push(['Pitcher H', team.pitching_hits]);

      return '<div class="team-box-card">' +
        '<p class="team-box-abbr">' + team.abbr + '</p>' +
        '<ul class="team-box-stats">' +
        stats.map(function (item) {
          return '<li><span>' + item[0] + '</span><strong>' + item[1] + '</strong></li>';
        }).join('') +
        '</ul></div>';
    }).join('');
  }

  function renderSituation(live, statusState) {
    var section = document.getElementById('game-situation-section');
    if (!live || !live.situation || statusState !== 'in') {
      if (section) section.hidden = true;
      return;
    }

    if (section) section.hidden = false;
    var situation = live.situation;

  var baseConfig = [
      { base: '1st', occupiedKey: 'on_first', runnerKey: 'first_runner', runnerId: 'game-runner-first' },
      { base: '2nd', occupiedKey: 'on_second', runnerKey: 'second_runner', runnerId: 'game-runner-second' },
      { base: '3rd', occupiedKey: 'on_third', runnerKey: 'third_runner', runnerId: 'game-runner-third' }
    ];

    baseConfig.forEach(function (item) {
      var el = document.querySelector('.base--' + item.base);
      if (el) el.classList.toggle('base--occupied', !!situation[item.occupiedKey]);

      var runnerEl = document.getElementById(item.runnerId);
      if (!runnerEl) return;
      var runnerName = situation[item.runnerKey];
      runnerEl.hidden = !runnerName;
      if (runnerName) runnerEl.textContent = runnerName;
    });

    var pitcherEl = document.getElementById('game-pitcher-name');
    if (pitcherEl) {
      var pitcherName = situation.pitcher_name;
      pitcherEl.hidden = !pitcherName;
      var pitcherNameEl = pitcherEl.querySelector('.bases-player-name');
      if (pitcherNameEl && pitcherName) pitcherNameEl.textContent = pitcherName;
    }

    var batterEl = document.getElementById('game-batter-name');
    if (batterEl) {
      var batterName = situation.batter_name;
      batterEl.hidden = !batterName;
      var batterNameEl = batterEl.querySelector('.bases-player-name');
      if (batterNameEl && batterName) batterNameEl.textContent = batterName;
    }
  }

  function applyGame(game) {
    var pill = document.getElementById('game-status-pill');
    var countEl = document.getElementById('game-count');

    var matchup = document.getElementById('game-matchup');
    if (matchup) {
      matchup.className = 'game-card game-card--' + game.status_state + ' game-detail-hero';
    }

    if (pill) {
      pill.className = 'status-pill status-pill--' + game.status_state;
      pill.textContent = game.status_detail || '';
    }

    if (countEl) {
      if (game.status_state === 'in' && game.balls !== null && game.balls !== undefined) {
        countEl.hidden = false;
        countEl.textContent = game.balls + '-' + game.strikes + ', ' + outsLabel(game.outs);
      } else {
        countEl.hidden = true;
      }
    }

    ['away', 'home'].forEach(function (side) {
      var team = game[side];
      var row = document.getElementById('game-team-' + side);
      if (!row || !team) return;

      row.classList.toggle('game-card-team--winner', !!team.winner);

      var scoreEl = document.getElementById('game-' + side + '-score');
      if (scoreEl) {
        scoreEl.textContent = team.score != null ? team.score : '0';
      }
    });

    var preview = game.preview || {};
    var awayWin = preview.away_win_pct;
    var homeWin = preview.home_win_pct;
    var winBar = document.getElementById('game-win-bar');

    if (awayWin != null || homeWin != null) {
      if (winBar) {
        winBar.hidden = false;
        if (game.away) {
          winBar.style.setProperty(
            '--away-win-color',
            game.away.win_color || game.away.color || '#56b6c6'
          );
        }
        if (game.home) {
          winBar.style.setProperty(
            '--home-win-color',
            game.home.win_color || game.home.color || '#22a06b'
          );
        }
      }
      if (awayWin != null) setText('game-away-win-pct-value', awayWin);
      if (homeWin != null) setText('game-home-win-pct-value', homeWin);

      var awayFill = document.getElementById('game-away-win-fill');
      var homeFill = document.getElementById('game-home-win-fill');
      if (awayFill && awayWin != null) awayFill.style.width = awayWin + '%';
      if (homeFill && homeWin != null) homeFill.style.width = homeWin + '%';
    } else if (winBar) {
      winBar.hidden = true;
    }

    var live = game.live || {};
    if (live.linescore) renderLinescore(live.linescore);
    renderTeamBox(live.team_box);
    renderSituation(live, game.status_state);
    renderPlayList('game-scoring-plays', live.scoring_plays, false);
    renderPlayList('game-recent-plays', live.recent_plays, false);

    document.title = game.away.abbr + ' @ ' + game.home.abbr + ' — Scoreboard';
  }

  function schedulePoll(ms) {
    if (pollTimer) {
      clearInterval(pollTimer);
    }
    pollTimer = setInterval(refreshGame, ms);
  }

  function refreshGame() {
    fetch(apiUrl, { cache: 'no-store' })
      .then(function (response) {
        if (!response.ok) throw new Error('fetch failed');
        return response.json();
      })
      .then(function (data) {
        if (!data.game) return;
        applyGame(data.game);
        schedulePoll(data.game.status_state === 'in' ? POLL_MS_LIVE : POLL_MS_FINAL);
      })
      .catch(function () {});
  }

  refreshGame();
})();

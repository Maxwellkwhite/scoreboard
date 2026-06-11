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
      container.innerHTML = '<li class="play-feed-empty">No plays yet.</li>';
      return;
    }

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

  function linescoreTeamColor(team) {
    if (!team) return '';
    return team.win_color || team.color || '';
  }

  function renderLinescore(linescore, awayTeam, homeTeam) {
    var table = document.getElementById('game-linescore-table');
    if (!table || !linescore) return;

    var headerCells = ['<th></th>'];
    linescore.columns.forEach(function (col) {
      headerCells.push('<th>' + col.number + '</th>');
    });
    headerCells.push('<th>R</th>', '<th>H</th>', '<th>E</th>');

    function row(side, teamMeta) {
      var team = linescore[side];
      var color = linescoreTeamColor(teamMeta);
      var rowStyle = color ? ' style="--linescore-team-color:' + color + '"' : '';
      var cells = ['<th>' + linescore[side + '_abbr'] + '</th>'];
      linescore.columns.forEach(function (col) {
        cells.push('<td>' + col[side] + '</td>');
      });
      cells.push(
        '<td class="linescore-total">' + (team.runs != null ? team.runs : '0') + '</td>',
        '<td>' + team.hits + '</td>',
        '<td>' + team.errors + '</td>'
      );
      return '<tr class="linescore-row"' + rowStyle + '>' + cells.join('') + '</tr>';
    }

    table.innerHTML =
      '<thead><tr>' + headerCells.join('') + '</tr></thead>' +
      '<tbody>' + row('away', awayTeam) + row('home', homeTeam) + '</tbody>';

  }

  var TEAM_BOX_STATS = [
    ['batting_hits', 'Hits'],
    ['batting_runs', 'Runs'],
    ['batting_strikeouts', 'Strikeouts'],
    ['batting_walks', 'Walks']
  ];

  function teamBoxEntry(teamBox, side) {
    if (!teamBox || !teamBox.length) return null;
    for (var i = 0; i < teamBox.length; i++) {
      if (teamBox[i].home_away === side) return teamBox[i];
    }
    return side === 'away' ? teamBox[0] : teamBox[1];
  }

  function teamBoxStatValue(team, key) {
    if (!team) return '—';
    var value = team[key];
    return value != null && value !== '' ? value : '—';
  }

  function teamBoxNumericValue(team, key) {
    if (!team || team[key] == null || team[key] === '') return null;
    var num = parseFloat(String(team[key]).replace(/[^\d.-]/g, ''));
    return isNaN(num) ? null : num;
  }

  function teamStatsLogo(team) {
    if (!team) return '';
    if (team.logo) {
      return '<img class="team-stats__logo" src="' + team.logo + '" alt="" width="32" height="32" loading="lazy">';
    }
    return '<span class="team-stats__logo-fallback">' + (team.abbr || '') + '</span>';
  }

  function teamStatsBar(awayNum, homeNum) {
    if (awayNum == null || homeNum == null) return '';
    var total = awayNum + homeNum;
    var awayPct = total > 0 ? (awayNum / total * 100) : 50;
    var homePct = total > 0 ? (homeNum / total * 100) : 50;
    return '<div class="team-stats__bar"' + (total === 0 ? ' team-stats__bar--even' : '') + ' role="presentation">' +
      '<span class="team-stats__bar-away" style="width:' + awayPct.toFixed(1) + '%;"></span>' +
      '<span class="team-stats__bar-home" style="width:' + homePct.toFixed(1) + '%;"></span>' +
      '</div>';
  }

  function renderTeamBox(teamBox, awayTeam, homeTeam) {
    var container = document.getElementById('game-team-box');
    if (!container) return;

    if (!teamBox || !teamBox.length) {
      container.innerHTML = '<p class="play-feed-empty">No team stats yet.</p>';
      return;
    }

    var awayBox = teamBoxEntry(teamBox, 'away');
    var homeBox = teamBoxEntry(teamBox, 'home');
    var awayColor = linescoreTeamColor(awayTeam) || '#1a2332';
    var homeColor = linescoreTeamColor(homeTeam) || '#1a2332';
    var awayAbbr = (awayBox && awayBox.abbr) || (awayTeam && awayTeam.abbr) || '';
    var homeAbbr = (homeBox && homeBox.abbr) || (homeTeam && homeTeam.abbr) || '';

    var rows = TEAM_BOX_STATS.filter(function (item) {
      var key = item[0];
      return (awayBox && awayBox[key] != null) || (homeBox && homeBox[key] != null);
    }).map(function (item) {
      var key = item[0];
      var awayNum = teamBoxNumericValue(awayBox, key);
      var homeNum = teamBoxNumericValue(homeBox, key);
      var comparable = awayNum != null && homeNum != null;
      var awayLead = comparable && awayNum >= homeNum;
      var homeLead = comparable && homeNum >= awayNum;
      return '<div class="team-stats__row">' +
        '<div class="team-stats__values">' +
        '<div class="team-stats__cell team-stats__cell--away' + (awayLead ? ' team-stats__cell--lead' : '') + '">' +
        '<span class="team-stats__value">' + teamBoxStatValue(awayBox, key) + '</span></div>' +
        '<div class="team-stats__label">' + item[1] + '</div>' +
        '<div class="team-stats__cell team-stats__cell--home' + (homeLead ? ' team-stats__cell--lead' : '') + '">' +
        '<span class="team-stats__value">' + teamBoxStatValue(homeBox, key) + '</span></div>' +
        '</div>' +
        teamStatsBar(awayNum, homeNum) +
        '</div>';
    }).join('');

    container.className = 'team-stats';
    container.style.setProperty('--away-team-color', awayColor);
    container.style.setProperty('--home-team-color', homeColor);
    container.innerHTML =
      '<div class="team-stats__head">' +
      '<div class="team-stats__team team-stats__team--away">' +
      teamStatsLogo(awayTeam) + '<span class="team-stats__abbr">' + awayAbbr + '</span></div>' +
      '<div class="team-stats__team team-stats__team--home">' +
      teamStatsLogo(homeTeam) + '<span class="team-stats__abbr">' + homeAbbr + '</span></div>' +
      '</div>' +
      '<div class="team-stats__rows">' + rows + '</div>';
  }

  function formatDueUpStats(batter) {
    var line = batter.line || '0-0';
    var runs = batter.runs != null ? batter.runs : '0';
    var rbi = batter.rbi != null ? batter.rbi : '0';
    return line + ', ' + runs + ' R, ' + rbi + ' RBI';
  }

  function renderSituation(live, statusState) {
    var section = document.getElementById('game-situation-section');
    if (!live || !live.situation || statusState !== 'in') {
      if (section) section.hidden = true;
      return;
    }

    if (section) section.hidden = false;
    var situation = live.situation;
    var showDueUp = !!(situation.show_due_up && situation.due_up && situation.due_up.length);
    var dueUpPanel = document.getElementById('game-due-up-panel');
    var bases = document.getElementById('game-bases');

    if (section) section.classList.toggle('is-due-up', showDueUp);
    if (dueUpPanel) dueUpPanel.hidden = !showDueUp;
    if (bases) bases.hidden = showDueUp;

    var dueUpList = document.getElementById('game-due-up');
    if (dueUpList) {
      dueUpList.textContent = '';
      if (showDueUp) {
        situation.due_up.forEach(function (batter) {
          var row = document.createElement('li');
          row.className = 'due-up-row';

          var nameEl = document.createElement('span');
          nameEl.className = 'due-up-name';
          nameEl.textContent = batter.name;

          var statsEl = document.createElement('span');
          statsEl.className = 'due-up-stats';
          statsEl.textContent = formatDueUpStats(batter);

          row.appendChild(nameEl);
          row.appendChild(statsEl);
          dueUpList.appendChild(row);
        });
      }
    }

    if (showDueUp) return;

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

  function battingTeamColor(game) {
    var side = game.batting_side;
    if (!side || !game[side]) return null;
    var team = game[side];
    return team.win_color || team.color || null;
  }

  function pitchingTeamColor(game) {
    var batting = game.batting_side;
    if (!batting) return null;
    var pitching = batting === 'away' ? 'home' : 'away';
    if (!game[pitching]) return null;
    var team = game[pitching];
    return team.win_color || team.color || null;
  }

  function applySituationTheme(game) {
    var section = document.getElementById('game-situation-section');
    var bases = document.getElementById('game-bases');
    if (!section && !bases) return;

    var battingColor = battingTeamColor(game);
    var pitchingColor = pitchingTeamColor(game);
    var themeTarget = section || bases;

    if (game.status_state === 'in' && battingColor) {
      themeTarget.style.setProperty('--batting-team-color', battingColor);
      if (pitchingColor) {
        themeTarget.style.setProperty('--pitching-team-color', pitchingColor);
      }
    } else {
      themeTarget.style.removeProperty('--batting-team-color');
      themeTarget.style.removeProperty('--pitching-team-color');
    }
  }

  function applyBattingTheme(game) {
    var matchup = document.getElementById('game-matchup');
    var pill = document.getElementById('game-status-pill');
    var color = battingTeamColor(game);

    if (matchup) {
      matchup.className = 'game-card game-card--' + game.status_state + ' game-detail-hero';
    }

    if (game.status_state === 'in' && color && matchup) {
      matchup.style.setProperty('--batting-team-color', color);
      if (pill) pill.classList.add('status-pill--batting-team');
    } else {
      if (matchup) matchup.style.removeProperty('--batting-team-color');
      if (pill) pill.classList.remove('status-pill--batting-team');
    }
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
    if (game.status_detail && /rain delay/i.test(game.status_detail)) {
      return 'Rain Delay';
    }
    return game.status_detail || '';
  }

  function applyMiniCard(card, game) {
    var isLink = card.tagName === 'A';
    var color = battingTeamColor(game);

    if (game.status_state === 'in' && color) {
      card.style.setProperty('--batting-team-color', color);
    } else {
      card.style.removeProperty('--batting-team-color');
    }

    card.className = 'game-mini-card game-mini-card--' + game.status_state +
      (isLink ? ' game-mini-card--link' : ' game-mini-card--active');

    var pill = card.querySelector('.status-pill');
    if (pill) {
      pill.className = 'status-pill status-pill--' + game.status_state;
      if (game.status_state === 'in' && color) {
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
    var sides = [
      { team: game.away },
      { team: game.home }
    ];

    sides.forEach(function (entry, index) {
      var team = entry.team;
      var row = teamRows[index];
      if (!row || !team) return;

      var rowClass = 'game-mini-card__team';
      if (team.winner) {
        rowClass += ' game-mini-card__team--winner';
      } else if (game.status_state === 'post' && hasWinner) {
        rowClass += ' game-mini-card__team--loser';
      }
      row.className = rowClass;
      row.style.setProperty(
        '--team-color',
        team.win_color || team.color || '#1a2332'
      );

      var scoreEl = row.querySelector('.game-mini-card__score');
      if (scoreEl) {
        scoreEl.textContent = game.status_state === 'pre'
          ? '—'
          : (team.score != null ? team.score : '0');
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

  function applyGame(game) {
    var pill = document.getElementById('game-status-pill');
    var countEl = document.getElementById('game-count');

    if (pill) {
      pill.className = 'status-pill status-pill--' + game.status_state;
      pill.textContent = game.status_detail || '';
    }

    applyBattingTheme(game);
    applySituationTheme(game);

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
      row.style.setProperty(
        '--team-color',
        team.win_color || team.color || '#1a2332'
      );

      var scoreEl = document.getElementById('game-' + side + '-score');
      if (scoreEl) {
        scoreEl.textContent = team.score != null ? team.score : '0';
      }

      var roleEl = document.getElementById('game-' + side + '-role');
      if (!roleEl) return;

      if (game.status_state === 'in' && game.batting_side) {
        var role = game.batting_side === side ? 'batting' : 'pitching';
        var color = team.win_color || team.color;
        roleEl.hidden = false;
        roleEl.textContent = role === 'batting' ? 'Batting' : 'Pitching';
        roleEl.className = 'game-card-role game-card-role--' + role;
        if (color) {
          roleEl.style.color = color;
          roleEl.style.borderColor = color;
        }
      } else {
        roleEl.hidden = true;
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
    if (live.linescore) renderLinescore(live.linescore, game.away, game.home);
    renderTeamBox(live.team_box, game.away, game.home);
    renderSituation(live, game.status_state);
    renderPlayList('game-scoring-plays', live.scoring_plays, false);
    renderPlayList('game-recent-plays', live.recent_plays, false);

    document.title = game.away.abbr + ' @ ' + game.home.abbr + ' — Scoreboard';
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
        if (data.strip_games) {
          updateStripGames(data.strip_games);
        }
        schedulePoll(data.game.status_state === 'in' ? POLL_MS_LIVE : POLL_MS_FINAL);
      })
      .catch(function () {});
  }

  initDetailTabs();
  refreshGame();
})();

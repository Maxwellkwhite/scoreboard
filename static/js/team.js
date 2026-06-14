(function () {
  var section = document.getElementById('team-stats-section');
  if (!section) return;

  var teamId = section.getAttribute('data-team-id');
  var loadingEl = document.getElementById('team-stats-loading');
  var errorEl = document.getElementById('team-stats-error');
  var summaryEl = document.getElementById('team-stats-summary');
  var tabsEl = document.getElementById('team-stats-tabs');
  var panelsEl = document.getElementById('team-stats-panels');

  if (!teamId || !loadingEl || !summaryEl) return;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function playerLink(id, name) {
    if (!id || !name) return escapeHtml(name || '');
    return (
      '<a href="/player/' + encodeURIComponent(id) + '" class="player-link">' +
      escapeHtml(name) + '</a>'
    );
  }

  function teamLink(id, label) {
    if (!id || !label) return escapeHtml(label || '');
    return (
      '<a href="/team/' + encodeURIComponent(id) + '" class="team-link">' +
      escapeHtml(label) + '</a>'
    );
  }

  function buildSeasonTableHtml(statsTable) {
    var columns = statsTable.columns || [];
    if (!columns.length) return '';

    var seasonLabel = statsTable.season_year || 'Season';
    var headerCells = '<th scope="col" class="player-stats-table__corner"></th>' +
      columns.map(function (col) {
        return '<th scope="col">' + escapeHtml(col.label) + '</th>';
      }).join('');

    var seasonCells = '<th scope="row">' + escapeHtml(seasonLabel) + '</th>' +
      columns.map(function (col) {
        return '<td>' + escapeHtml(col.season) + '</td>';
      }).join('');

    return (
      '<div class="player-stats-table-wrap">' +
        '<table class="player-stats-table">' +
          '<thead><tr>' + headerCells + '</tr></thead>' +
          '<tbody><tr class="player-stats-table__season">' + seasonCells + '</tr></tbody>' +
        '</table>' +
      '</div>'
    );
  }

  function buildToggleHtml(panelId, views, defaultView) {
    var activeView = defaultView || (views[0] && views[0].id) || '';
    var buttons = views.map(function (view) {
      var isActive = view.id === activeView;
      return (
        '<button type="button" class="player-panel-toggle__btn' +
        (isActive ? ' is-active' : '') +
        '" data-panel="' + escapeHtml(panelId) +
        '" data-view="' + escapeHtml(view.id) + '"' +
        ' aria-pressed="' + (isActive ? 'true' : 'false') + '">' +
        escapeHtml(view.label) +
        '</button>'
      );
    }).join('');

    return '<div class="player-panel-toggle" data-panel="' + escapeHtml(panelId) + '">' + buttons + '</div>';
  }

  function teamStatBarColor(metric) {
    if (metric.better !== false) return '#22a06b';
    return '#d4183d';
  }

  function buildTeamStatValueHtml(metric) {
    var teamValue =
      '<span class="team-stat-bar-row__value pitch-mix-bar-row__value">' +
        escapeHtml(metric.display) +
      '</span>';

    if (!metric.league_display) {
      return teamValue + '<span class="team-stat-bar-row__league-compare" aria-hidden="true"></span>';
    }

    var compareClass = 'team-stat-bar-row__league-compare';
    var arrow = '';
    if (metric.above_median === true) {
      arrow = '<span class="team-stat-bar-row__arrow" aria-hidden="true">▲</span>';
    } else if (metric.above_median === false) {
      arrow = '<span class="team-stat-bar-row__arrow" aria-hidden="true">▼</span>';
    }
    if (metric.better !== false) {
      compareClass += ' team-stat-bar-row__league-compare--better';
    } else {
      compareClass += ' team-stat-bar-row__league-compare--worse';
    }

    var compareLabel = metric.better === false
      ? 'Worse than league median'
      : (metric.above_median == null && metric.league_display
        ? 'Tied with league median'
        : 'Better than league median');
    var compareHtml =
      '<span class="' + compareClass + '" title="' + escapeHtml(compareLabel) + '">' +
        arrow +
        '<span class="team-stat-bar-row__league-value">' + escapeHtml(metric.league_display) + '</span>' +
      '</span>';

    return teamValue + compareHtml;
  }

  function buildStatBarsHtml(view) {
    var metrics = view.metrics || [];
    if (!metrics.length) {
      return '<p class="player-splits-empty">No stats available.</p>';
    }

    var rows = metrics.map(function (metric) {
      var barPct = Math.max(0, Math.min(100, Number(metric.bar_pct) || 0));
      var leaguePct = metric.league_pct == null ? null : Math.max(0, Math.min(100, Number(metric.league_pct) || 0));
      var leagueMarker = leaguePct == null
        ? ''
        : (
          '<span class="team-stat-bar-row__league" style="left:' + leaguePct.toFixed(1) +
          '%" title="League median ' + escapeHtml(metric.league_display || '') + '"></span>'
        );

      return (
        '<div class="pitch-mix-bar-row team-stat-bar-row">' +
          '<span class="pitch-mix-bar-row__label">' + escapeHtml(metric.label) + '</span>' +
          '<div class="team-stat-bar-row__track" aria-hidden="true">' +
            '<span class="team-stat-bar-row__fill" style="width:' + barPct.toFixed(1) +
            '%;background:' + teamStatBarColor(metric) + '"></span>' +
            leagueMarker +
          '</div>' +
          buildTeamStatValueHtml(metric) +
        '</div>'
      );
    }).join('');

    return (
      '<div class="team-stat-bars">' +
        '<div class="team-stat-bars__legend">' +
          '<span class="team-stat-bars__legend-mark" aria-hidden="true"></span>' +
          '<span>League median</span>' +
        '</div>' +
        '<div class="team-stat-bars__rows">' + rows + '</div>' +
      '</div>'
    );
  }

  function buildStatTableHtml(panel) {
    var rows = (panel.rows || []).map(function (row) {
      return (
        '<tr>' +
          '<th scope="row">' + escapeHtml(row.label) + '</th>' +
          '<td>' + escapeHtml(row.value) + '</td>' +
        '</tr>'
      );
    }).join('');
    if (!rows) {
      return '<p class="player-splits-empty">No stats available.</p>';
    }
    return (
      '<div class="team-stat-table-wrap">' +
        '<table class="team-stat-table">' +
          '<tbody>' + rows + '</tbody>' +
        '</table>' +
      '</div>'
    );
  }

  function buildLeadersHtml(panel) {
    var groups = panel.groups || [];
    if (!groups.length) {
      return '<p class="player-splits-empty">No leaders available.</p>';
    }

    return groups.map(function (group) {
      var categories = (group.categories || []).map(function (category) {
        var leaders = (category.leaders || []).map(function (leader, index) {
          return (
            '<li class="team-leader-row">' +
              '<span class="team-leader-row__rank">' + (index + 1) + '</span>' +
              '<span class="team-leader-row__name">' + playerLink(leader.id, leader.name) + '</span>' +
              '<span class="team-leader-row__value">' + escapeHtml(leader.value) + '</span>' +
            '</li>'
          );
        }).join('');
        if (!leaders) return '';
        return (
          '<section class="team-leader-category">' +
            '<h4 class="team-leader-category__title">' + escapeHtml(category.title) + '</h4>' +
            '<ol class="team-leader-list">' + leaders + '</ol>' +
          '</section>'
        );
      }).join('');

      return (
        '<section class="team-leaders-group">' +
          '<h3 class="team-leaders-group__title">' + escapeHtml(group.title) + '</h3>' +
          '<div class="team-leaders-grid">' + categories + '</div>' +
        '</section>'
      );
    }).join('');
  }

  function buildRosterHtml(panel) {
    var groups = panel.groups || [];
    if (!groups.length) {
      return '<p class="player-splits-empty">Roster unavailable.</p>';
    }

    return groups.map(function (group) {
      var players = (group.players || []).map(function (player) {
        var jersey = player.jersey ? '#' + player.jersey + ' ' : '';
        return (
          '<li class="team-roster-row">' +
            '<span class="team-roster-row__player">' +
              jersey + playerLink(player.id, player.name) +
            '</span>' +
            '<span class="team-roster-row__pos">' + escapeHtml(player.position || '') + '</span>' +
          '</li>'
        );
      }).join('');
      return (
        '<section class="team-roster-group">' +
          '<h4 class="team-roster-group__title">' + escapeHtml(group.title) + '</h4>' +
          '<ul class="team-roster-list">' + players + '</ul>' +
        '</section>'
      );
    }).join('');
  }

  function formatGameDate(value) {
    if (!value) return '';
    var date = new Date(value);
    if (isNaN(date.getTime())) return '';
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  }

  function buildScheduleSection(title, games) {
    if (!games.length) return '';
    var rows = games.map(function (game) {
      var prefix = game.home_away === 'away' ? '@ ' : 'vs ';
      var opponent = teamLink(game.opponent_id, prefix + (game.opponent_abbr || game.opponent_name || ''));
      var score = '';
      if (game.result && game.team_score != null && game.opponent_score != null) {
        score =
          '<span class="team-schedule-row__result team-schedule-row__result--' +
          escapeHtml(String(game.result).toLowerCase()) + '">' +
          escapeHtml(game.result) + ' ' +
          escapeHtml(String(game.team_score)) + '–' + escapeHtml(String(game.opponent_score)) +
          '</span>';
      } else {
        score = '<span class="team-schedule-row__status">' + escapeHtml(game.status || '') + '</span>';
      }
      var gameLink = game.id
        ? '<a href="/game/' + encodeURIComponent(game.id) + '" class="team-schedule-row__game-link">Box</a>'
        : '';
      return (
        '<li class="team-schedule-row">' +
          '<span class="team-schedule-row__date">' + escapeHtml(formatGameDate(game.date)) + '</span>' +
          '<span class="team-schedule-row__matchup">' + opponent + '</span>' +
          score +
          gameLink +
        '</li>'
      );
    }).join('');

    return (
      '<section class="team-schedule-section">' +
        '<h3 class="team-schedule-section__title">' + escapeHtml(title) + '</h3>' +
        '<ul class="team-schedule-list">' + rows + '</ul>' +
      '</section>'
    );
  }

  function buildScheduleHtml(panel) {
    var recent = buildScheduleSection('Recent Games', panel.recent || []);
    var upcoming = buildScheduleSection('Upcoming', panel.upcoming || []);
    if (!recent && !upcoming) {
      return '<p class="player-splits-empty">Schedule unavailable.</p>';
    }
    return '<div class="team-schedule">' + recent + upcoming + '</div>';
  }

  function buildInfoCardsHtml(panel) {
    var cards = (panel.cards || []).map(function (card) {
      return (
        '<div class="team-info-card">' +
          '<span class="team-info-card__label">' + escapeHtml(card.label) + '</span>' +
          '<span class="team-info-card__value">' + escapeHtml(card.value) + '</span>' +
        '</div>'
      );
    }).join('');
    if (!cards) {
      return '<p class="player-splits-empty">No team info available.</p>';
    }
    return '<div class="team-info-grid">' + cards + '</div>';
  }

  function buildPanelInnerHtml(panel) {
    if (panel.panel_kind === 'toggle_stat_bars' || panel.panel_kind === 'toggle_stat_table') {
      var defaultView = panel.default_view || (panel.views[0] && panel.views[0].id);
      var toggleHtml = buildToggleHtml(panel.id, panel.views, defaultView);
      var viewsHtml = (panel.views || []).map(function (view) {
        var bodyHtml = view.metrics
          ? buildStatBarsHtml(view)
          : buildStatTableHtml(view);
        return (
          '<div class="player-panel-view" data-panel="' + escapeHtml(panel.id) +
          '" data-view="' + escapeHtml(view.id) + '"' +
          (view.id === defaultView ? '' : ' hidden') + '>' +
          bodyHtml +
          '</div>'
        );
      }).join('');
      return (
        '<div class="player-panel-header">' + toggleHtml + '</div>' +
        '<div class="team-panel-body">' + viewsHtml + '</div>'
      );
    }
    if (panel.panel_kind === 'stat_table') {
      return '<div class="team-panel-body">' + buildStatTableHtml(panel) + '</div>';
    }
    if (panel.panel_kind === 'leaders_table') {
      return '<div class="team-panel-body">' + buildLeadersHtml(panel) + '</div>';
    }
    if (panel.panel_kind === 'roster_groups') {
      return '<div class="team-panel-body team-panel-body--roster">' + buildRosterHtml(panel) + '</div>';
    }
    if (panel.panel_kind === 'schedule_list') {
      return '<div class="team-panel-body">' + buildScheduleHtml(panel) + '</div>';
    }
    if (panel.panel_kind === 'info_cards') {
      return '<div class="team-panel-body">' + buildInfoCardsHtml(panel) + '</div>';
    }
    if (panel.panel_kind === 'season_table' && panel.stats_table) {
      return '<div class="team-panel-body">' + buildSeasonTableHtml(panel.stats_table) + '</div>';
    }
    return '<div class="team-panel-body"><p class="player-splits-empty">No data available.</p></div>';
  }

  function initStatPanels(statPanels) {
    if (!tabsEl || !panelsEl || !statPanels.length) return;

    tabsEl.innerHTML = statPanels.map(function (panel, index) {
      return (
        '<button type="button" class="game-detail-tab' +
        (index === 0 ? ' is-active' : '') +
        '" data-panel="' + escapeHtml(panel.id) + '"' +
        ' aria-selected="' + (index === 0 ? 'true' : 'false') + '">' +
        escapeHtml(panel.label) +
        '</button>'
      );
    }).join('');

    panelsEl.innerHTML = statPanels.map(function (panel, index) {
      return (
        '<section class="game-detail-section game-detail-panel team-stats-panel"' +
        ' data-panel="' + escapeHtml(panel.id) + '"' +
        (index === 0 ? '' : ' hidden') + '>' +
        buildPanelInnerHtml(panel) +
        '</section>'
      );
    }).join('');

    tabsEl.hidden = false;
    initPanelToggles(panelsEl);

    var buttons = tabsEl.querySelectorAll('.game-detail-tab');
    var panels = panelsEl.querySelectorAll('.team-stats-panel');

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
      var panel = panelsEl.querySelector('.team-stats-panel[data-panel="' + panelId + '"]');
      if (!panel || panel.hidden) return;
      panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        var panelId = btn.getAttribute('data-panel');
        showPanel(panelId);
        requestAnimationFrame(function () {
          scrollToPanel(panelId);
        });
      });
    });
  }

  function initPanelToggles(root) {
    root.querySelectorAll('.player-panel-toggle__btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var panelId = btn.getAttribute('data-panel');
        var viewId = btn.getAttribute('data-view');
        var panel = root.querySelector('.team-stats-panel[data-panel="' + panelId + '"]');
        if (!panel) return;

        panel.querySelectorAll('.player-panel-toggle__btn').forEach(function (toggleBtn) {
          var isActive = toggleBtn.getAttribute('data-view') === viewId;
          toggleBtn.classList.toggle('is-active', isActive);
          toggleBtn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        panel.querySelectorAll('.player-panel-view').forEach(function (viewEl) {
          viewEl.hidden = viewEl.getAttribute('data-view') !== viewId;
        });
      });
    });
  }

  function finishLoading() {
    section.setAttribute('aria-busy', 'false');
  }

  function showError() {
    loadingEl.hidden = true;
    summaryEl.hidden = true;
    if (tabsEl) tabsEl.hidden = true;
    if (panelsEl) panelsEl.innerHTML = '';
    if (errorEl) errorEl.hidden = false;
    finishLoading();
  }

  function showStats(payload) {
    var hasSummary = payload.stats_table && buildSeasonTableHtml(payload.stats_table);
    var hasPanels = payload.stat_panels && payload.stat_panels.length;

    if (!hasSummary && !hasPanels) {
      showError();
      return;
    }

    loadingEl.hidden = true;
    if (errorEl) errorEl.hidden = true;

    if (hasSummary) {
      summaryEl.innerHTML = hasSummary;
      summaryEl.hidden = false;
    } else {
      summaryEl.hidden = true;
    }

    if (hasPanels) {
      initStatPanels(payload.stat_panels);
    }

    finishLoading();
  }

  fetch('/api/mlb/team/' + encodeURIComponent(teamId) + '/stats')
    .then(function (response) {
      if (!response.ok) throw new Error('Stats unavailable');
      return response.json();
    })
    .then(showStats)
    .catch(showError);
})();

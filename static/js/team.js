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

  function playerInitials(name) {
    if (!name) return '?';
    return name.split(' ').map(function (part) {
      return part.charAt(0);
    }).join('').slice(0, 2).toUpperCase();
  }

  function leaderHeadshotHtml(leader) {
    var label = playerInitials(leader.name);
    if (!leader.headshot) {
      return (
        '<span class="team-leader-card__headshot team-leader-card__headshot--placeholder">' +
          escapeHtml(label) +
        '</span>'
      );
    }
    return (
      '<span class="team-leader-card__headshot-wrap">' +
        '<img class="team-leader-card__headshot" src="' + escapeHtml(leader.headshot) +
        '" alt="" width="36" height="36" loading="lazy">' +
        '<span class="team-leader-card__headshot team-leader-card__headshot--placeholder team-leader-card__headshot--fallback" hidden>' +
          escapeHtml(label) +
        '</span>' +
      '</span>'
    );
  }

  function wireLeaderHeadshotFallbacks(root) {
    root.querySelectorAll('.team-leader-card__headshot-wrap img').forEach(function (img) {
      img.addEventListener('error', function () {
        var wrap = img.closest('.team-leader-card__headshot-wrap');
        if (!wrap) return;
        img.hidden = true;
        var fallback = wrap.querySelector('.team-leader-card__headshot--fallback');
        if (fallback) fallback.hidden = false;
      }, { once: true });
    });
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
        '<div class="team-stat-bars__rows">' + rows + '</div>' +
        '<div class="team-stat-bars__footer">' +
          '<p class="team-stat-bars__color-note">' +
            'Bar color: <span class="team-stat-bars__color-swatch team-stat-bars__color-swatch--better">green</span> ' +
            'at or above league median, ' +
            '<span class="team-stat-bars__color-swatch team-stat-bars__color-swatch--worse">red</span> below. ' +
            'Bar length ranks this team among all 30 teams for that stat.' +
          '</p>' +
          '<div class="team-stat-bars__legend">' +
            '<span class="team-stat-bars__legend-mark" aria-hidden="true"></span>' +
            '<span>League median</span>' +
          '</div>' +
        '</div>' +
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

  function buildLeadersViewHtml(view) {
    var categories = view.categories || [];
    if (!categories.length) {
      return '<p class="player-splits-empty">No leaders available.</p>';
    }

    return (
      '<div class="team-leaders">' +
        '<div class="team-leaders-grid">' +
        categories.map(function (category) {
          var leaders = (category.leaders || []).map(function (leader, index) {
            var rank = index + 1;
            return (
              '<li class="team-leader-card__row' + (rank === 1 ? ' team-leader-card__row--first' : '') + '">' +
                '<span class="team-leader-card__rank">' + rank + '</span>' +
                '<div class="team-leader-card__player">' +
                  leaderHeadshotHtml(leader) +
                  '<span class="team-leader-card__name">' + playerLink(leader.id, leader.name) + '</span>' +
                '</div>' +
                '<span class="team-leader-card__value">' + escapeHtml(leader.value) + '</span>' +
              '</li>'
            );
          }).join('');
          if (!leaders) return '';
          return (
            '<article class="team-leader-card">' +
              '<h4 class="team-leader-card__title">' + escapeHtml(category.title) + '</h4>' +
              '<ol class="team-leader-card__list">' + leaders + '</ol>' +
            '</article>'
          );
        }).join('') +
        '</div>' +
      '</div>'
    );
  }

  function rosterAvatarClass(player) {
    var filter = player.filter || 'other';
    if (filter === 'sp' || filter === 'rp' || filter === 'c' || filter === 'if' || filter === 'of') {
      return 'team-roster-card__avatar--' + filter;
    }
    return 'team-roster-card__avatar--other';
  }

  function rosterHeadshotHtml(player) {
    var label = playerInitials(player.name);
    var avatarClass = rosterAvatarClass(player);
    if (!player.headshot) {
      return (
        '<span class="team-roster-card__avatar ' + avatarClass + ' team-roster-card__avatar--placeholder">' +
          escapeHtml(label) +
        '</span>'
      );
    }
    return (
      '<span class="team-roster-card__avatar-wrap">' +
        '<img class="team-roster-card__avatar ' + avatarClass + '" src="' + escapeHtml(player.headshot) +
        '" alt="" width="52" height="52" loading="lazy">' +
        '<span class="team-roster-card__avatar ' + avatarClass +
        ' team-roster-card__avatar--placeholder team-roster-card__avatar--fallback" hidden>' +
          escapeHtml(label) +
        '</span>' +
      '</span>'
    );
  }

  function buildRosterCard(player) {
    var statusVariant = player.status_variant || 'active';
    var meta = player.meta || '';
    var jersey = player.jersey ? '#' + player.jersey : '';
    var cardClass =
      'team-roster-card' +
      ' team-roster-card--' + escapeHtml(player.filter || 'other') +
      ' team-roster-card--status-' + escapeHtml(statusVariant);

    var inner =
      (jersey ? '<span class="team-roster-card__jersey">' + escapeHtml(jersey) + '</span>' : '') +
      rosterHeadshotHtml(player) +
      '<span class="team-roster-card__name">' + escapeHtml(player.name) + '</span>' +
      '<span class="team-roster-card__pos">' + escapeHtml(player.position || '') + '</span>' +
      (meta ? '<span class="team-roster-card__meta">' + escapeHtml(meta) + '</span>' : '') +
      '<span class="team-roster-card__status" aria-hidden="true"></span>';

    return (
      '<a href="/player/' + encodeURIComponent(player.id) + '" class="' + cardClass + '"' +
      ' data-filter="' + escapeHtml(player.filter || 'other') + '">' +
      inner +
      '</a>'
    );
  }

  function buildRosterFilterHtml(panel) {
    var defaultFilter = panel.default_filter || 'all';
    var filters = panel.filters || [];
    return (
      '<div class="player-panel-toggle" role="group" aria-label="Roster position filter">' +
      filters.map(function (filter) {
        var isActive = filter.id === defaultFilter;
        return (
          '<button type="button" class="player-panel-toggle__btn' +
          (isActive ? ' is-active' : '') +
          '" data-filter="' + escapeHtml(filter.id) + '"' +
          ' aria-pressed="' + (isActive ? 'true' : 'false') + '">' +
          escapeHtml(filter.label) +
          '</button>'
        );
      }).join('') +
      '</div>'
    );
  }

  function buildRosterSectionsHtml(panel) {
    var sections = panel.sections || [];
    if (!sections.length) {
      return '<p class="player-splits-empty">Roster unavailable.</p>';
    }

    return sections.map(function (section) {
      var cards = (section.players || []).map(buildRosterCard).join('');
      if (!cards) return '';
      return (
        '<section class="team-roster-section" data-section="' + escapeHtml(section.id) + '">' +
          '<h3 class="team-roster-section__title">' + escapeHtml(section.title) + '</h3>' +
          '<div class="team-roster-grid">' + cards + '</div>' +
        '</section>'
      );
    }).join('');
  }

  function buildRosterHtml(panel) {
    var sections = panel.sections || [];
    if (!sections.length) {
      return '<p class="player-splits-empty">Roster unavailable.</p>';
    }

    return (
      '<div class="team-roster" data-default-filter="' + escapeHtml(panel.default_filter || 'all') + '">' +
        buildRosterSectionsHtml(panel) +
      '</div>'
    );
  }

  function wireRosterHeadshotFallbacks(root) {
    root.querySelectorAll('.team-roster-card__avatar-wrap img').forEach(function (img) {
      img.addEventListener('error', function () {
        var wrap = img.closest('.team-roster-card__avatar-wrap');
        if (!wrap) return;
        img.hidden = true;
        var fallback = wrap.querySelector('.team-roster-card__avatar--fallback');
        if (fallback) fallback.hidden = false;
      }, { once: true });
    });
  }

  function initRosterPanels(root) {
    root.querySelectorAll('.team-stats-panel').forEach(function (panelEl) {
      var roster = panelEl.querySelector('.team-roster');
      if (!roster) return;

      var sections = Array.prototype.slice.call(roster.querySelectorAll('.team-roster-section'));
      var cards = Array.prototype.slice.call(roster.querySelectorAll('.team-roster-card'));
      var buttons = Array.prototype.slice.call(
        panelEl.querySelectorAll('.player-panel-header .player-panel-toggle__btn[data-filter]')
      );

      function applyFilter(filterId) {
        buttons.forEach(function (btn) {
          var isActive = btn.getAttribute('data-filter') === filterId;
          btn.classList.toggle('is-active', isActive);
          btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
        });

        cards.forEach(function (card) {
          var cardFilter = card.getAttribute('data-filter') || '';
          var show = filterId === 'all' || cardFilter === filterId;
          card.hidden = !show;
        });

        sections.forEach(function (section) {
          var visibleCards = section.querySelectorAll('.team-roster-card:not([hidden])');
          section.hidden = visibleCards.length === 0;
        });
      }

      buttons.forEach(function (btn) {
        btn.addEventListener('click', function () {
          applyFilter(btn.getAttribute('data-filter') || 'all');
        });
      });

      applyFilter(roster.getAttribute('data-default-filter') || 'all');
    });
  }

  function formatGameTime(value) {
    if (!value) return '';
    var date = new Date(value);
    if (isNaN(date.getTime())) return '';
    return date.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  }

  function isPostponedGame(game) {
    if (game.postponed) return true;
    return /postpon/i.test(String(game.status || ''));
  }

  function normalizeScheduleGame(game) {
    if (isPostponedGame(game)) {
      return {
        teamScore: null,
        oppScore: null,
        result: null,
        postponed: true,
        statusLabel: 'Postponed',
        isFinal: false,
      };
    }

    function parseScore(score) {
      if (score == null) return null;
      if (typeof score === 'object') {
        if (score.displayValue != null && String(score.displayValue).trim() !== '') {
          return String(score.displayValue);
        }
        if (score.value != null) {
          return String(Math.round(Number(score.value)));
        }
        return null;
      }
      return String(score);
    }

    var teamScore = parseScore(game.team_score);
    var oppScore = parseScore(game.opponent_score);
    var result = game.result || null;
    var isFinal = Boolean(result) || /final/i.test(String(game.status || ''));
    if (!result && isFinal && teamScore != null && oppScore != null) {
      var teamRuns = Number(teamScore);
      var oppRuns = Number(oppScore);
      if (!isNaN(teamRuns) && !isNaN(oppRuns)) {
        result = teamRuns > oppRuns ? 'W' : (teamRuns < oppRuns ? 'L' : 'T');
      }
    }

    return {
      teamScore: teamScore,
      oppScore: oppScore,
      result: result,
      postponed: false,
      statusLabel: game.status || '',
      isFinal: isFinal,
    };
  }

  function scheduleStatusHtml(game, normalized) {
    if (normalized.postponed) {
      return '<span class="team-schedule-calendar__status team-schedule-calendar__status--postponed">Postponed</span>';
    }
    return (
      '<span class="team-schedule-calendar__status">' +
        escapeHtml(game.status || formatGameTime(game.date)) +
      '</span>'
    );
  }

  function scheduleResultClass(normalized) {
    if (normalized.postponed) return 'postponed';
    if (normalized.result) return String(normalized.result).toLowerCase();
    return 'upcoming';
  }

  function buildScheduleGameCard(game) {
    var normalized = normalizeScheduleGame(game);
    var resultKey = scheduleResultClass(normalized);
    var classes = ['team-schedule-calendar__game-card', 'team-schedule-calendar__game-card--' + resultKey];

    var prefix = game.home_away === 'away' ? '@' : 'vs';
    var opponent = game.opponent_abbr || game.opponent_name || '';
    var badge = normalized.result
      ? (
        '<span class="team-schedule-calendar__result-badge team-schedule-calendar__result-badge--' +
        escapeHtml(resultKey) + '">' + escapeHtml(normalized.result) + '</span>'
      )
      : '';

    var scoreHtml;
    if (!normalized.postponed && normalized.teamScore != null && normalized.oppScore != null) {
      scoreHtml =
        '<span class="team-schedule-calendar__score">' +
          escapeHtml(normalized.teamScore) + '–' + escapeHtml(normalized.oppScore) +
        '</span>';
    } else {
      scoreHtml = scheduleStatusHtml(game, normalized);
    }

    var inner =
      '<div class="team-schedule-calendar__matchup">' +
        badge +
        '<span class="team-schedule-calendar__opponent">' +
          escapeHtml(prefix + ' ' + opponent) +
        '</span>' +
      '</div>' +
      scoreHtml;

    if (game.id) {
      return (
        '<a href="/game/' + encodeURIComponent(game.id) + '" class="' + classes.join(' ') + '">' +
        inner +
        '</a>'
      );
    }

    return '<div class="' + classes.join(' ') + '">' + inner + '</div>';
  }

  function buildScheduleDayCell(day, dayGames, isToday) {
    if (!dayGames.length) {
      return (
        '<div class="team-schedule-calendar__day' + (isToday ? ' team-schedule-calendar__day--today' : '') + '">' +
          '<span class="team-schedule-calendar__day-num">' + day + '</span>' +
        '</div>'
      );
    }

    if (dayGames.length === 1) {
      var game = dayGames[0];
      var normalized = normalizeScheduleGame(game);
      var resultKey = scheduleResultClass(normalized);
      var classes = ['team-schedule-calendar__day', 'team-schedule-calendar__day--game', 'team-schedule-calendar__day--' + resultKey];
      if (isToday) classes.push('team-schedule-calendar__day--today');

      var prefix = game.home_away === 'away' ? '@' : 'vs';
      var opponent = game.opponent_abbr || game.opponent_name || '';
      var badge = normalized.result
        ? (
          '<span class="team-schedule-calendar__result-badge team-schedule-calendar__result-badge--' +
          escapeHtml(resultKey) + '">' + escapeHtml(normalized.result) + '</span>'
        )
        : '';

      var scoreHtml;
      if (!normalized.postponed && normalized.teamScore != null && normalized.oppScore != null) {
        scoreHtml =
          '<span class="team-schedule-calendar__score">' +
            escapeHtml(normalized.teamScore) + '–' + escapeHtml(normalized.oppScore) +
          '</span>';
      } else {
        scoreHtml = scheduleStatusHtml(game, normalized);
      }

      var inner =
        '<span class="team-schedule-calendar__day-num">' + day + '</span>' +
        '<div class="team-schedule-calendar__matchup">' +
          badge +
          '<span class="team-schedule-calendar__opponent">' +
            escapeHtml(prefix + ' ' + opponent) +
          '</span>' +
        '</div>' +
        scoreHtml;

      if (game.id) {
        return (
          '<a href="/game/' + encodeURIComponent(game.id) + '" class="' + classes.join(' ') + '">' +
          inner +
          '</a>'
        );
      }

      return '<div class="' + classes.join(' ') + '">' + inner + '</div>';
    }

    return (
      '<div class="team-schedule-calendar__day team-schedule-calendar__day--double' +
      (isToday ? ' team-schedule-calendar__day--today' : '') + '">' +
        '<span class="team-schedule-calendar__day-num">' + day + '</span>' +
        '<div class="team-schedule-calendar__day-games">' +
          dayGames.map(buildScheduleGameCard).join('') +
        '</div>' +
      '</div>'
    );
  }

  function buildScheduleMonthGrid(month) {
    var games = month.games || [];
    var year = month.year;
    var monthIndex = month.month - 1;
    var firstDay = new Date(year, monthIndex, 1).getDay();
    var daysInMonth = new Date(year, monthIndex + 1, 0).getDate();
    var gamesByDay = {};

    games.forEach(function (game) {
      var day = game.day;
      if (!day) return;
      if (!gamesByDay[day]) gamesByDay[day] = [];
      gamesByDay[day].push(game);
    });

    var weekdayLabels = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    var weekdays = weekdayLabels.map(function (label) {
      return '<div class="team-schedule-calendar__weekday">' + label + '</div>';
    }).join('');

    var cells = [];
    var pad = 0;
    while (pad < firstDay) {
      cells.push('<div class="team-schedule-calendar__day team-schedule-calendar__day--empty" aria-hidden="true"></div>');
      pad += 1;
    }

    for (var day = 1; day <= daysInMonth; day += 1) {
      var dayGames = gamesByDay[day] || [];
      var today = new Date();
      var isToday = today.getFullYear() === year &&
        today.getMonth() === monthIndex &&
        today.getDate() === day;
      cells.push(buildScheduleDayCell(day, dayGames, isToday));
    }

    return (
      '<div class="team-schedule-calendar__grid">' +
        '<div class="team-schedule-calendar__weekdays">' + weekdays + '</div>' +
        '<div class="team-schedule-calendar__days">' + cells.join('') + '</div>' +
      '</div>'
    );
  }

  function monthRecordLabel(month) {
    var wins = 0;
    var losses = 0;
    var ties = 0;
    (month.games || []).forEach(function (game) {
      var normalized = normalizeScheduleGame(game);
      if (normalized.postponed || !normalized.result) return;
      if (normalized.result === 'W') wins += 1;
      else if (normalized.result === 'L') losses += 1;
      else if (normalized.result === 'T') ties += 1;
    });
    if (ties) {
      return wins + '–' + losses + '–' + ties;
    }
    return wins + '–' + losses;
  }

  function buildScheduleMonthNav(months, defaultMonth) {
    var active = months.find(function (month) {
      return month.id === defaultMonth;
    }) || months[0];

    return (
      '<div class="team-schedule-calendar__nav">' +
        '<button type="button" class="team-schedule-calendar__arrow team-schedule-calendar__arrow--prev" aria-label="Previous month">' +
          '<span aria-hidden="true">‹</span>' +
        '</button>' +
        '<div class="team-schedule-calendar__month-meta">' +
          '<h3 class="team-schedule-calendar__month-label">' + escapeHtml(active.label) + '</h3>' +
          '<p class="team-schedule-calendar__month-record">' + escapeHtml(monthRecordLabel(active)) + '</p>' +
        '</div>' +
        '<button type="button" class="team-schedule-calendar__arrow team-schedule-calendar__arrow--next" aria-label="Next month">' +
          '<span aria-hidden="true">›</span>' +
        '</button>' +
      '</div>'
    );
  }

  function buildScheduleCalendarHtml(panel) {
    var months = panel.months || [];
    if (!months.length) {
      return '<p class="player-splits-empty">Schedule unavailable.</p>';
    }

    var defaultMonth = panel.default_month || months[0].id;
    var viewsHtml = months.map(function (month) {
      return (
        '<div class="team-schedule-calendar__month"' +
        ' data-month="' + escapeHtml(month.id) + '"' +
        ' data-label="' + escapeHtml(month.label) + '"' +
        ' data-record="' + escapeHtml(monthRecordLabel(month)) + '"' +
        (month.id === defaultMonth ? '' : ' hidden') + '>' +
        buildScheduleMonthGrid(month) +
        '</div>'
      );
    }).join('');

    return (
      '<div class="team-schedule-calendar">' +
        '<div class="team-schedule-calendar__header">' +
          buildScheduleMonthNav(months, defaultMonth) +
        '</div>' +
        '<div class="team-schedule-calendar__body">' + viewsHtml + '</div>' +
      '</div>'
    );
  }

  function initScheduleCalendars(root) {
    root.querySelectorAll('.team-schedule-calendar').forEach(function (calendar) {
      var views = Array.prototype.slice.call(
        calendar.querySelectorAll('.team-schedule-calendar__month')
      );
      if (!views.length) return;

      var labelEl = calendar.querySelector('.team-schedule-calendar__month-label');
      var recordEl = calendar.querySelector('.team-schedule-calendar__month-record');
      var prevBtn = calendar.querySelector('.team-schedule-calendar__arrow--prev');
      var nextBtn = calendar.querySelector('.team-schedule-calendar__arrow--next');
      if (!labelEl || !recordEl || !prevBtn || !nextBtn) return;

      var currentIndex = views.findIndex(function (viewEl) {
        return !viewEl.hidden;
      });
      if (currentIndex < 0) currentIndex = 0;

      function showMonth(index) {
        currentIndex = index;
        views.forEach(function (viewEl, viewIndex) {
          viewEl.hidden = viewIndex !== index;
        });
        labelEl.textContent = views[index].getAttribute('data-label') || '';
        recordEl.textContent = views[index].getAttribute('data-record') || '';
        var atStart = index <= 0;
        var atEnd = index >= views.length - 1;
        prevBtn.classList.toggle('is-disabled', atStart);
        nextBtn.classList.toggle('is-disabled', atEnd);
        prevBtn.disabled = atStart;
        nextBtn.disabled = atEnd;
      }

      prevBtn.addEventListener('click', function () {
        if (currentIndex > 0) showMonth(currentIndex - 1);
      });
      nextBtn.addEventListener('click', function () {
        if (currentIndex < views.length - 1) showMonth(currentIndex + 1);
      });

      showMonth(currentIndex);
    });
  }

  function buildPanelInnerHtml(panel) {
    if (panel.panel_kind === 'toggle_stat_bars' || panel.panel_kind === 'toggle_stat_table' || panel.panel_kind === 'toggle_leaders') {
      var defaultView = panel.default_view || (panel.views[0] && panel.views[0].id);
      var toggleHtml = buildToggleHtml(panel.id, panel.views, defaultView);
      var viewsHtml = (panel.views || []).map(function (view) {
        var bodyHtml;
        if (panel.panel_kind === 'toggle_leaders') {
          bodyHtml = buildLeadersViewHtml(view);
        } else if (view.metrics) {
          bodyHtml = buildStatBarsHtml(view);
        } else {
          bodyHtml = buildStatTableHtml(view);
        }
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
    if (panel.panel_kind === 'roster_cards' || panel.panel_kind === 'roster_groups') {
      return (
        '<div class="player-panel-header">' + buildRosterFilterHtml(panel) + '</div>' +
        '<div class="team-panel-body team-panel-body--roster">' + buildRosterHtml(panel) + '</div>'
      );
    }
    if (panel.panel_kind === 'schedule_calendar') {
      return '<div class="team-panel-body">' + buildScheduleCalendarHtml(panel) + '</div>';
    }
    if (panel.panel_kind === 'loading') {
      return buildPanelLoadingHtml();
    }
    if (panel.panel_kind === 'season_table' && panel.stats_table) {
      return '<div class="team-panel-body">' + buildSeasonTableHtml(panel.stats_table) + '</div>';
    }
    return '<div class="team-panel-body"><p class="player-splits-empty">No data available.</p></div>';
  }

  var PANEL_ORDER = ['team_stats', 'leaders', 'roster', 'schedule'];
  var activePanelId = null;
  var tabNavigationBound = false;

  function panelSortIndex(panelId) {
    var idx = PANEL_ORDER.indexOf(panelId);
    return idx === -1 ? PANEL_ORDER.length : idx;
  }

  function buildPanelLoadingHtml() {
    return (
      '<div class="team-panel-body team-panel-body--loading">' +
        '<div class="player-stats-loading">' +
          '<div class="player-stats-loading__ball" aria-hidden="true"></div>' +
          '<p class="player-stats-loading__text">Loading…</p>' +
        '</div>' +
      '</div>'
    );
  }

  function buildTabHtml(panel, isActive) {
    return (
      '<button type="button" class="game-detail-tab' +
      (isActive ? ' is-active' : '') +
      '" data-panel="' + escapeHtml(panel.id) + '"' +
      ' aria-selected="' + (isActive ? 'true' : 'false') + '">' +
      escapeHtml(panel.label) +
      '</button>'
    );
  }

  function buildPanelSectionHtml(panel, isActive) {
    return (
      '<section class="game-detail-section game-detail-panel team-stats-panel"' +
      ' data-panel="' + escapeHtml(panel.id) + '"' +
      (isActive ? '' : ' hidden') + '>' +
      buildPanelInnerHtml(panel) +
      '</section>'
    );
  }

  function findPanelInsertBefore(panelId, container, selector) {
    var items = container.querySelectorAll(selector);
    for (var i = 0; i < items.length; i++) {
      if (panelSortIndex(items[i].getAttribute('data-panel')) > panelSortIndex(panelId)) {
        return items[i];
      }
    }
    return null;
  }

  function insertTab(panel, isActive) {
    var insertBefore = findPanelInsertBefore(panel.id, tabsEl, '.game-detail-tab');
    var tabHtml = buildTabHtml(panel, isActive);
    if (insertBefore) {
      insertBefore.insertAdjacentHTML('beforebegin', tabHtml);
    } else {
      tabsEl.insertAdjacentHTML('beforeend', tabHtml);
    }
  }

  function insertPanelSection(panel, isActive) {
    var insertBefore = findPanelInsertBefore(panel.id, panelsEl, '.team-stats-panel');
    var sectionHtml = buildPanelSectionHtml(panel, isActive);
    if (insertBefore) {
      insertBefore.insertAdjacentHTML('beforebegin', sectionHtml);
    } else {
      panelsEl.insertAdjacentHTML('beforeend', sectionHtml);
    }
    return panelsEl.querySelector('.team-stats-panel[data-panel="' + panel.id + '"]');
  }

  function wirePanelElement(panelEl) {
    if (!panelEl) return;
    initPanelToggles(panelEl);
    wireLeaderHeadshotFallbacks(panelEl);
    wireRosterHeadshotFallbacks(panelEl);
    initScheduleCalendars(panelEl);
    initRosterPanels(panelEl);
  }

  function setActivePanel(panelId) {
    activePanelId = panelId;
    if (!tabsEl || !panelsEl) return;

    tabsEl.querySelectorAll('.game-detail-tab').forEach(function (tab) {
      var isActive = tab.getAttribute('data-panel') === panelId;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    panelsEl.querySelectorAll('.team-stats-panel').forEach(function (panel) {
      panel.hidden = panel.getAttribute('data-panel') !== panelId;
    });
  }

  function bindTabNavigation() {
    if (tabNavigationBound || !tabsEl) return;
    tabNavigationBound = true;

    tabsEl.addEventListener('click', function (event) {
      var btn = event.target.closest('.game-detail-tab');
      if (!btn || !tabsEl.contains(btn)) return;
      var panelId = btn.getAttribute('data-panel');
      if (!panelId) return;

      setActivePanel(panelId);
      requestAnimationFrame(function () {
        var panel = panelsEl.querySelector('.team-stats-panel[data-panel="' + panelId + '"]');
        if (panel && !panel.hidden) {
          panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  function upsertPanel(panel) {
    if (!tabsEl || !panelsEl || !panel || !panel.id) return;

    var existingTab = tabsEl.querySelector('.game-detail-tab[data-panel="' + panel.id + '"]');
    var existingPanel = panelsEl.querySelector('.team-stats-panel[data-panel="' + panel.id + '"]');
    var shouldActivate = activePanelId === panel.id;

    if (!existingTab) {
      insertTab(panel, shouldActivate);
    } else {
      existingTab.textContent = panel.label;
    }

    if (existingPanel) {
      existingPanel.innerHTML = buildPanelInnerHtml(panel);
      wirePanelElement(existingPanel);
    } else {
      wirePanelElement(insertPanelSection(panel, shouldActivate));
    }

    tabsEl.hidden = false;
    bindTabNavigation();
  }

  function initCorePanels(statPanels) {
    if (!tabsEl || !panelsEl) return;

    var panels = (statPanels || []).slice().sort(function (a, b) {
      return panelSortIndex(a.id) - panelSortIndex(b.id);
    });

    tabsEl.innerHTML = '';
    panelsEl.innerHTML = '';
    activePanelId = panels[0] ? panels[0].id : null;

    panels.forEach(function (panel, index) {
      insertTab(panel, index === 0);
      wirePanelElement(insertPanelSection(panel, index === 0));
    });

    upsertPanel({ id: 'leaders', label: 'Team Leaders', panel_kind: 'loading' });
    upsertPanel({ id: 'roster', label: 'Roster', panel_kind: 'loading' });

    if (activePanelId) {
      setActivePanel(activePanelId);
    }

    tabsEl.hidden = false;
    bindTabNavigation();
  }

  function fulfillStagedPanel(panelId, panel) {
    if (panel) {
      upsertPanel(panel);
      return;
    }

    var existingPanel = panelsEl.querySelector('.team-stats-panel[data-panel="' + panelId + '"]');
    if (existingPanel) {
      existingPanel.innerHTML =
        '<div class="team-panel-body"><p class="player-splits-empty">Unavailable right now.</p></div>';
    }
  }

  function fetchTeamStats(path) {
    return fetch('/api/mlb/team/' + encodeURIComponent(teamId) + path).then(function (response) {
      if (!response.ok) throw new Error('Stats unavailable');
      return response.json();
    });
  }

  function loadStagedPanels() {
    fetchTeamStats('/stats/roster')
      .then(function (payload) {
        fulfillStagedPanel('roster', payload.stat_panel);
      })
      .catch(function () {
        fulfillStagedPanel('roster', null);
      });

    fetchTeamStats('/stats/leaders')
      .then(function (payload) {
        fulfillStagedPanel('leaders', payload.stat_panel);
      })
      .catch(function () {
        fulfillStagedPanel('leaders', null);
      });
  }

  function initPanelToggles(root) {
    root.querySelectorAll('.player-panel-toggle__btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var viewId = btn.getAttribute('data-view');
        var panel = btn.closest('.team-stats-panel');
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

  function showCoreStats(payload) {
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
      initCorePanels(payload.stat_panels);
    }

    finishLoading();
    loadStagedPanels();
  }

  fetchTeamStats('/stats')
    .then(showCoreStats)
    .catch(showError);
})();

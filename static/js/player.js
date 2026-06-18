(function () {
  var rootEl = document.querySelector('.player-page .game-detail-main');
  if (!rootEl) return;

  var playerId = rootEl.getAttribute('data-player-id');
  var isPitcher = rootEl.getAttribute('data-is-pitcher') === 'true';
  var visualPanelId = isPitcher ? 'pitch_profile' : 'hit_profile';
  var visualPanelLabel = 'Advanced Stats';
  var tabsEl = document.getElementById('player-stats-tabs');
  var panelsEl = document.getElementById('player-stats-panels');

  if (!playerId || !panelsEl) return;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function careerLogColumnLabel(log, column) {
    var labels = log.header_labels || {};
    return labels[column] || column;
  }

  function buildSeasonLogTableHtml(statsTable) {
    var log = statsTable.career_log;
    if (!log || !(log.seasons || []).length) {
      return buildSeasonCareerTableHtml(statsTable);
    }

    var columns = log.table_columns || [];
    var headerCells =
      '<th scope="col">Year</th>' +
      '<th scope="col">Team</th>' +
      columns.map(function (column) {
        return '<th scope="col">' + escapeHtml(careerLogColumnLabel(log, column)) + '</th>';
      }).join('');

    var seasonRows = (log.seasons || []).map(function (season) {
      var rowClass = 'player-stats-table__season';
      if (String(season.year) === String(log.season_year || statsTable.season_year)) {
        rowClass += ' player-stats-table__season--current';
      }
      var cells = columns.map(function (column) {
        var value = (season.cells || {})[column];
        return '<td>' + escapeHtml(value != null && value !== '' ? value : '—') + '</td>';
      }).join('');
      return (
        '<tr class="' + rowClass + '">' +
          '<th scope="row">' + escapeHtml(String(season.year)) + '</th>' +
          '<td>' + escapeHtml(season.team || '—') + '</td>' +
          cells +
        '</tr>'
      );
    }).join('');

    var careerCells = columns.map(function (column) {
      var value = (log.career && log.career.cells || {})[column];
      return '<td>' + escapeHtml(value != null && value !== '' ? value : '—') + '</td>';
    }).join('');

    return (
      '<div class="player-stats-table-wrap">' +
        '<table class="player-stats-table player-stats-table--season-log">' +
          '<thead><tr>' + headerCells + '</tr></thead>' +
          '<tbody>' +
            seasonRows +
            '<tr class="player-stats-table__career">' +
              '<th scope="row">Career</th>' +
              '<td>—</td>' +
              careerCells +
            '</tr>' +
          '</tbody>' +
        '</table>' +
      '</div>'
    );
  }

  var TIMELINE_META_COLUMNS = { Season: true, Tm: true, LG: true, Age: true };
  var TIMELINE_STAT_LABELS = {
    BF: 'Batters Faced',
    W: 'Wins',
    L: 'Losses',
    ERA: 'Earned Run Average',
    G: 'Games',
    GS: 'Games Started',
    SV: 'Saves',
    IP: 'Innings Pitched',
    H: 'Hits',
    R: 'Runs',
    ER: 'Earned Runs',
    HR: 'Home Runs',
    BB: 'Walks',
    SO: 'Strikeouts',
    WHIP: 'Walks + Hits per Inning',
    PA: 'Plate Appearances',
    AB: 'At Bats',
    '2B': 'Doubles',
    '3B': 'Triples',
    RBI: 'Runs Batted In',
    SB: 'Stolen Bases',
    CS: 'Caught Stealing',
    HBP: 'Hit By Pitch',
    AVG: 'Batting Average',
    OBP: 'On-Base Percentage',
    SLG: 'Slugging Percentage',
    OPS: 'On-Base Plus Slugging',
    Age: 'Age',
    Pitches: 'Pitches',
    BattedBalls: 'Batted Balls',
    Barrels: 'Barrels',
    'Barrel %': 'Barrel %',
    'Barrel/PA': 'Barrel per PA',
    ExitVelocity: 'Avg Exit Velocity',
    'Max EV': 'Max Exit Velocity',
    LaunchAngle: 'Launch Angle',
    'LA Sweet-Spot %': 'LA Sweet-Spot %',
    xBA: 'xBA',
    xSLG: 'xSLG',
    wOBA: 'wOBA',
    xwOBA: 'xwOBA',
    xwOBAcon: 'xwOBAcon',
    'HardHit%': 'Hard Hit %',
    'K%': 'K %',
    'BB%': 'BB %',
    xERA: 'xERA',
    TB: 'Total Bases',
    LOB: 'Left on Base',
    SAC: 'Sacrifices',
    SF: 'Sacrifice Flies',
    BABIP: 'BABIP',
    XBH: 'Extra-Base Hits',
    GIDP: 'Grounded Into DP',
    GIDPO: 'GIDP Opportunities',
    NP: 'Pitches Seen',
    'P/PA': 'Pitches per PA',
    'K/PA': 'K per PA',
    'HR/PA': 'HR per PA',
    'BB/K': 'BB per K',
    ISO: 'Isolated Power',
    ROE: 'Reached on Error',
    WO: 'Waste Opportunities',
  };
  var TIMELINE_ADVANCED_TICK_LABELS = {
    Pitches: 'Pit',
    BattedBalls: 'BBE',
    Barrels: 'BR',
    'Barrel %': 'BR%',
    'Barrel/PA': 'BR/PA',
    ExitVelocity: 'EV',
    'Max EV': 'Max EV',
    LaunchAngle: 'LA',
    'LA Sweet-Spot %': 'LA SS%',
    xwOBAcon: 'xwOBACON',
    'HardHit%': 'HH%',
    GIDPO: 'GIDPO',
    'P/PA': 'P/PA',
    'K/PA': 'K/PA',
    'HR/PA': 'HR/PA',
    'BB/K': 'BB/K',
  };

  function timelineTickLabel(column, abbreviate) {
    if (abbreviate && TIMELINE_ADVANCED_TICK_LABELS[column]) {
      return TIMELINE_ADVANCED_TICK_LABELS[column];
    }
    return column;
  }

  function parseSavantTimelineValue(value, column) {
    if (value == null || value === '' || value === '—') return null;
    var text = String(value).trim();
    if (text.indexOf('%') !== -1) {
      var pct = Number(text.replace('%', '').trim());
      return Number.isNaN(pct) ? null : pct;
    }
    if (text.startsWith('.')) text = '0' + text;
    if (column === 'IP' && text.indexOf('.') !== -1) {
      var parts = text.split('.');
      var whole = parseInt(parts[0], 10) || 0;
      var partial = parseInt(parts[1], 10) || 0;
      return whole + partial / 3;
    }
    var num = Number(text.replace(/[^\d.-]/g, ''));
    return Number.isNaN(num) ? null : num;
  }

  function formatSavantTimelineDisplay(value, column) {
    if (value == null || value === '' || value === '—') return '—';
    return String(value);
  }

  function timelineStatLabel(column) {
    return TIMELINE_STAT_LABELS[column] || column;
  }

  function buildSavantCareerTableHtml(statsTable) {
    var columns = statsTable.columns || [];
    var rows = statsTable.rows || [];
    if (!columns.length || !rows.length) {
      return '';
    }

    var headerCells = columns.map(function (column) {
      return '<th scope="col">' + escapeHtml(column) + '</th>';
    }).join('');

    var bodyRows = rows.map(function (row) {
      var rowClass = 'player-stats-table__season';
      var season = (row.cells || {}).Season || row.label;
      if (String(season) === String(statsTable.season_year)) {
        rowClass += ' player-stats-table__season--current';
      }
      var cells = columns.map(function (column) {
        var value = (row.cells || {})[column];
        return '<td>' + escapeHtml(value != null && value !== '' ? value : '—') + '</td>';
      }).join('');
      return '<tr class="' + rowClass + '">' + cells + '</tr>';
    }).join('');

    return (
      '<div class="player-stats-table-wrap player-stats-table-wrap--savant">' +
        '<table class="player-stats-table player-stats-table--savant">' +
          '<thead><tr>' + headerCells + '</tr></thead>' +
          '<tbody>' + bodyRows + '</tbody>' +
        '</table>' +
      '</div>'
    );
  }

  function isSavantTimelineCareerRow(row) {
    var season = String((row && row.season) || '');
    return season === 'Career' || !/^\d{4}$/.test(season);
  }

  function sortSavantTimelineRows(a, b) {
    var aSeason = String((a.cells || {}).Season || a.label || '');
    var bSeason = String((b.cells || {}).Season || b.label || '');
    var aCareer = isSavantTimelineCareerRow({ season: aSeason });
    var bCareer = isSavantTimelineCareerRow({ season: bSeason });
    if (aCareer && !bCareer) return 1;
    if (!aCareer && bCareer) return -1;
    return Number(bSeason) - Number(aSeason);
  }

  function buildSavantTimelineHtml(statsTable, options) {
    options = options || {};
    var abbreviateTicks = !!options.abbreviateTicks;
    var columns = (statsTable.columns || []).filter(function (column) {
      return !TIMELINE_META_COLUMNS[column];
    });
    var rows = (statsTable.rows || []).slice().sort(sortSavantTimelineRows);
    if (!columns.length || !rows.length) {
      return '';
    }

    var payload = {
      columns: columns,
      rows: rows.map(function (row) {
        return {
          season: (row.cells || {}).Season || row.label,
          team: (row.cells || {}).Tm || '—',
          league: (row.cells || {}).LG || '',
          cells: row.cells || {},
        };
      }),
      season_year: statsTable.season_year,
      league_bounds: statsTable.league_bounds || {},
      abbreviate_ticks: abbreviateTicks,
    };

    var statTicks = columns.map(function (column, index) {
      return (
        '<span class="season-timeline__tick' + (index === 0 ? ' is-active' : '') +
        '" data-index="' + index + '" style="left:' +
        ((index / Math.max(columns.length - 1, 1)) * 100).toFixed(1) + '%">' +
        '<span class="season-timeline__tick-dot"></span>' +
        '<span class="season-timeline__tick-label">' +
        escapeHtml(timelineTickLabel(column, abbreviateTicks)) +
        '</span>' +
        '</span>'
      );
    }).join('');

    return (
      '<div class="season-timeline">' +
        '<script type="application/json" class="season-timeline__data">' +
        JSON.stringify(payload).replace(/</g, '\\u003c') +
        '</script>' +
        '<div class="season-timeline__scrub">' +
          '<div class="season-timeline__scrub-head">' +
            '<span class="season-timeline__active-stat">' + escapeHtml(timelineStatLabel(columns[0])) + '</span>' +
            '<span class="season-timeline__scrub-hint">drag to scrub stats</span>' +
          '</div>' +
          '<input type="range" class="season-timeline__range" min="0" max="' +
          (columns.length - 1) + '" value="0" step="1" aria-label="Scrub through season stats" />' +
          '<div class="season-timeline__ticks" aria-hidden="true">' + statTicks + '</div>' +
        '</div>' +
        '<div class="season-timeline__lanes" aria-live="polite"></div>' +
      '</div>'
    );
  }

  function renderSeasonTimelineLanes(timelineEl, statIndex) {
    var dataEl = timelineEl.querySelector('.season-timeline__data');
    if (!dataEl) return;

    var payload;
    try {
      payload = JSON.parse(dataEl.textContent || '{}');
    } catch (error) {
      return;
    }

    var columns = payload.columns || [];
    var rows = payload.rows || [];
    var column = columns[statIndex];
    if (!column) return;

    var values = rows.filter(function (row) {
      return !isSavantTimelineCareerRow(row);
    }).map(function (row) {
      return parseSavantTimelineValue(row.cells[column], column);
    }).filter(function (value) { return value != null; });

    var minValue = values.length ? Math.min.apply(null, values) : 0;
    var maxValue = values.length ? Math.max.apply(null, values) : 1;

    var lanesEl = timelineEl.querySelector('.season-timeline__lanes');
    if (!lanesEl) return;

    var lanesHtml = rows.map(function (row) {
      var rawValue = row.cells[column];
      var numeric = parseSavantTimelineValue(rawValue, column);
      var rowMin = minValue;
      var rowMax = maxValue;
      var seasonBounds = ((payload.league_bounds || {})[String(row.season)] || {})[column];
      if (
        seasonBounds &&
        seasonBounds.min != null &&
        seasonBounds.max != null &&
        seasonBounds.max > seasonBounds.min
      ) {
        rowMin = seasonBounds.min;
        rowMax = seasonBounds.max;
      } else if (rowMin === rowMax) {
        rowMin -= 1;
        rowMax += 1;
      }

      var ratio = 0.12;
      if (numeric != null) {
        ratio = (numeric - rowMin) / (rowMax - rowMin);
        ratio = Math.max(0.08, Math.min(0.96, ratio));
      }
      var widthPct = (ratio * 100).toFixed(1);
      var laneClass = 'season-timeline__lane';
      if (String(row.season) === String(payload.season_year)) {
        laneClass += ' season-timeline__lane--current';
      }
      var teamLabel = row.team || '';
      if (isSavantTimelineCareerRow(row)) {
        teamLabel = teamLabel && teamLabel !== '—' ? teamLabel : '';
      } else {
        teamLabel = teamLabel || '—';
      }
      var teamHtml = teamLabel
        ? '<span class="season-timeline__team">' + escapeHtml(teamLabel) + '</span>'
        : '';
      var ageHtml = row.cells && row.cells.Age && row.cells.Age !== '—'
        ? '<span class="season-timeline__age">Age ' + escapeHtml(String(row.cells.Age)) + '</span>'
        : '';
      return (
        '<div class="' + laneClass + '">' +
          '<div class="season-timeline__meta">' +
            '<span class="season-timeline__year">' + escapeHtml(String(row.season)) + '</span>' +
            teamHtml +
            ageHtml +
            (row.league
              ? '<span class="season-timeline__lg">' + escapeHtml(row.league) + '</span>'
              : '') +
          '</div>' +
          '<div class="season-timeline__track" aria-hidden="true">' +
            '<span class="season-timeline__bar" style="width:' + widthPct + '%;background:#22a06b"></span>' +
            '<span class="season-timeline__dot" style="left:' + widthPct + '%"></span>' +
          '</div>' +
          '<div class="season-timeline__value">' +
            escapeHtml(formatSavantTimelineDisplay(rawValue, column)) +
          '</div>' +
        '</div>'
      );
    }).join('');

    lanesEl.innerHTML = lanesHtml;

    var activeStatEl = timelineEl.querySelector('.season-timeline__active-stat');
    if (activeStatEl) activeStatEl.textContent = timelineStatLabel(column);

    timelineEl.querySelectorAll('.season-timeline__tick').forEach(function (tick) {
      var isActive = Number(tick.getAttribute('data-index')) === statIndex;
      tick.classList.toggle('is-active', isActive);
    });
  }

  function initSeasonTimelines(root) {
    if (!root) return;
    root.querySelectorAll('.season-timeline').forEach(function (timelineEl) {
      if (timelineEl.dataset.bound === 'true') return;
      timelineEl.dataset.bound = 'true';

      var rangeEl = timelineEl.querySelector('.season-timeline__range');
      renderSeasonTimelineLanes(timelineEl, 0);

      if (!rangeEl) return;

      rangeEl.addEventListener('input', function () {
        renderSeasonTimelineLanes(timelineEl, Number(rangeEl.value) || 0);
      });

      timelineEl.querySelectorAll('.season-timeline__tick').forEach(function (tick) {
        tick.addEventListener('click', function () {
          var index = Number(tick.getAttribute('data-index'));
          if (Number.isNaN(index)) return;
          rangeEl.value = String(index);
          renderSeasonTimelineLanes(timelineEl, index);
        });
      });
    });
  }

  function initSeasonStatsPanels(root) {
    if (!root) return;
    root.querySelectorAll('.player-season-stats').forEach(function (container) {
      if (container.dataset.bound === 'true') return;
      container.dataset.bound = 'true';

      var select = container.querySelector('.player-season-stats__view-select');
      if (!select) return;

      select.addEventListener('change', function () {
        var viewId = select.value;
        container.querySelectorAll('.player-season-stats__panel').forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-view') !== viewId;
        });
      });
    });
    initSeasonTimelines(root);
  }

  function buildStatsTableHtml(statsTable) {
    if (!statsTable) return '';
    if (statsTable.layout === 'savant_career') {
      return buildSavantCareerTableHtml(statsTable);
    }
    if (statsTable.career_log && (statsTable.career_log.seasons || []).length) {
      return buildSeasonLogTableHtml(statsTable);
    }
    return buildSeasonCareerTableHtml(statsTable);
  }

  function buildSeasonStatsComingSoonHtml() {
    var metrics = ['Exit Velo', 'Barrel%', 'xBA', 'xwOBA', 'Chase%', 'Whiff%'];
    var chips = metrics.map(function (metric) {
      return '<span class="player-season-stats__coming-soon-chip">' + escapeHtml(metric) + '</span>';
    }).join('');

    return (
      '<div class="player-season-stats__coming-soon" role="status">' +
        '<div class="player-season-stats__coming-soon-icon" aria-hidden="true">' +
          '<span class="player-season-stats__coming-soon-radar"></span>' +
        '</div>' +
        '<p class="player-season-stats__coming-soon-title">Advanced stats coming soon</p>' +
        '<p class="player-season-stats__coming-soon-copy">' +
          'Season-by-season Statcast metrics and league context are on the way.' +
        '</p>' +
        '<div class="player-season-stats__coming-soon-chips" aria-hidden="true">' + chips + '</div>' +
      '</div>'
    );
  }

  function buildPercentileComingSoonHtml() {
    var metrics = ['Exit Velo', 'Barrel%', 'Hard Hit%', 'xBA', 'xwOBA', 'Sprint Speed'];
    var chips = metrics.map(function (metric) {
      return '<span class="player-season-stats__coming-soon-chip">' + escapeHtml(metric) + '</span>';
    }).join('');

    return (
      '<div class="player-season-stats__coming-soon" role="status">' +
        '<div class="player-season-stats__coming-soon-icon" aria-hidden="true">' +
          '<span class="player-season-stats__coming-soon-radar"></span>' +
        '</div>' +
        '<p class="player-season-stats__coming-soon-title">Percentile Rankings coming soon</p>' +
        '<p class="player-season-stats__coming-soon-copy">' +
          'Statcast percentile ranks compared to qualified MLB players are on the way.' +
        '</p>' +
        '<div class="player-season-stats__coming-soon-chips" aria-hidden="true">' + chips + '</div>' +
      '</div>'
    );
  }

  function buildSeasonStatsNestedHtml(nestedPanel) {
    var views = nestedPanel.views || [];
    var defaultView = nestedPanel.default_view || (views[0] && views[0].id) || 'standard';
    var optionsHtml = views.map(function (view) {
      return (
        '<option value="' + escapeHtml(view.id) + '"' +
        (view.id === defaultView ? ' selected' : '') + '>' +
        escapeHtml(view.label || '') +
        '</option>'
      );
    }).join('');

    var panelsHtml = views.map(function (view) {
      var content = '';
      if (view.coming_soon) {
        content = buildSeasonStatsComingSoonHtml();
      } else if (view.stats_table && view.stats_table.layout === 'savant_career') {
        content = buildSavantTimelineHtml(view.stats_table, {
          abbreviateTicks: view.id === 'advanced',
        });
      }
      if (!content) {
        content = buildStatsTableHtml(view.stats_table);
      }
      if (!content) {
        content = '<p class="player-splits-empty">Season stats unavailable.</p>';
      }
      return (
        '<div class="player-season-stats__panel" data-view="' + escapeHtml(view.id) + '"' +
        (view.id === defaultView ? '' : ' hidden') + '>' +
        content +
        '</div>'
      );
    }).join('');

    return (
      '<div class="player-season-stats">' +
        '<div class="player-season-stats__header">' +
          '<select class="player-season-stats__view-select" aria-label="Season stats view">' +
          optionsHtml +
          '</select>' +
        '</div>' +
        panelsHtml +
      '</div>'
    );
  }

  function buildSeasonCareerTableHtml(statsTable) {
    var columns = statsTable.columns || [];
    var rows = statsTable.rows || [];
    if (!columns.length && !rows.length) return '';

    var labels = columns.map(function (col) {
      return col.label;
    });
    if (!labels.length && rows[0] && rows[0].cells) {
      labels = Object.keys(rows[0].cells);
    }

    var headerCells = '<th scope="col" class="player-stats-table__corner"></th>' +
      labels.map(function (col) {
        return '<th scope="col">' + escapeHtml(col) + '</th>';
      }).join('');

    if (rows.length) {
      var bodyRows = rows.map(function (row) {
        var rowClass = row.row_kind === 'career'
          ? 'player-stats-table__career'
          : 'player-stats-table__season';
        var cells = labels.map(function (label) {
          var value = (row.cells || {})[label];
          return '<td>' + escapeHtml(value != null && value !== '' ? value : '—') + '</td>';
        }).join('');
        return (
          '<tr class="' + rowClass + '">' +
            '<th scope="row">' + escapeHtml(row.label) + '</th>' +
            cells +
          '</tr>'
        );
      }).join('');

      return (
        '<div class="player-stats-table-wrap">' +
          '<table class="player-stats-table">' +
            '<thead><tr>' + headerCells + '</tr></thead>' +
            '<tbody>' + bodyRows + '</tbody>' +
          '</table>' +
        '</div>'
      );
    }

    var seasonLabel = statsTable.season_year || 'Season';
    var seasonCells = '<th scope="row">' + escapeHtml(seasonLabel) + '</th>' +
      columns.map(function (col) {
        return '<td>' + escapeHtml(col.season) + '</td>';
      }).join('');

    var careerCells = '<th scope="row">Career</th>' +
      columns.map(function (col) {
        return '<td>' + escapeHtml(col.career) + '</td>';
      }).join('');

    return (
      '<div class="player-stats-table-wrap">' +
        '<table class="player-stats-table">' +
          '<thead><tr>' + headerCells + '</tr></thead>' +
          '<tbody>' +
            '<tr class="player-stats-table__season">' + seasonCells + '</tr>' +
            '<tr class="player-stats-table__career">' + careerCells + '</tr>' +
          '</tbody>' +
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

  function playerStatBarColor(metric) {
    if (metric.better !== false) return '#22a06b';
    return '#d4183d';
  }

  function buildPlayerStatValueHtml(metric) {
    var playerValue =
      '<span class="team-stat-bar-row__value pitch-mix-bar-row__value">' +
        escapeHtml(metric.display) +
      '</span>';

    if (!metric.league_display) {
      return playerValue + '<span class="team-stat-bar-row__league-compare" aria-hidden="true"></span>';
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

    return playerValue + compareHtml;
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
            '%;background:' + playerStatBarColor(metric) + '"></span>' +
            leagueMarker +
          '</div>' +
          buildPlayerStatValueHtml(metric) +
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
            'Bar length ranks this player among qualified MLB players for that stat.' +
          '</p>' +
          '<div class="team-stat-bars__legend">' +
            '<span class="team-stat-bars__legend-mark" aria-hidden="true"></span>' +
            '<span>League median</span>' +
          '</div>' +
        '</div>' +
      '</div>'
    );
  }

  function splitCellValue(row, label) {
    var cells = row.cells || [];
    for (var i = 0; i < cells.length; i++) {
      if (cells[i].label === label) return cells[i].value;
    }
    return '—';
  }

  function splitParseNumber(value) {
    if (value === null || value === undefined || value === '' || value === '—') return null;
    var num = Number(String(value).replace(/[^\d.-]/g, ''));
    return Number.isNaN(num) ? null : num;
  }

  function splitPickMiniStats(columns, preferred) {
    return preferred.filter(function (label) {
      return columns.indexOf(label) !== -1;
    }).slice(0, 6);
  }

  function splitIsOpsAgainst(columns) {
    return columns.indexOf('OPS') !== -1 && columns.indexOf('AB') === -1;
  }

  function splitIsHittingOps(columns) {
    return columns.indexOf('OPS') !== -1 && columns.indexOf('AB') !== -1;
  }

  function splitKindMeta(kind) {
    if (kind === 'cards-era' || kind === 'months-era') {
      return {
        metric: 'ERA',
        higherBetter: false,
        diffDigits: 2,
        scaleWord: 'best',
        detailLabels: ['IP', 'WHIP', 'SO'],
        detailSuffix: 'IP / WHIP / SO',
        volumeLabel: 'IP',
        legendLow: 'Rough',
        legendHigh: 'Strong'
      };
    }
    if (kind === 'cards-ops-against' || kind === 'months-ops-against') {
      return {
        metric: 'OPS',
        higherBetter: false,
        diffDigits: 3,
        scaleWord: 'best',
        detailLabels: ['BA', 'OBP', 'SLG'],
        detailSuffix: 'BA / OBP / SLG allowed',
        volumeLabel: 'PA',
        legendLow: 'Rough',
        legendHigh: 'Strong'
      };
    }
    return {
      metric: 'OPS',
      higherBetter: true,
      diffDigits: 3,
      scaleWord: 'max',
      detailLabels: ['BA', 'OBP', 'SLG'],
      detailSuffix: 'BA / OBP / SLG',
      volumeLabel: 'PA',
      legendLow: 'Slower',
      legendHigh: 'Hot'
    };
  }

  function splitGroupKind(group) {
    var title = String(group.title || '').toLowerCase();
    var rows = group.rows || [];
    var columns = group.columns || [];
    if (!rows.length) return 'empty';

    if (title.indexOf('month') !== -1) {
      return columns.indexOf('ERA') !== -1 ? 'months-era' : 'months-ops';
    }

    if (rows.length === 2) {
      if (columns.indexOf('ERA') !== -1) return 'cards-era';
      if (columns.indexOf('OPS') !== -1) {
        return splitIsOpsAgainst(columns) ? 'cards-ops-against' : 'cards-ops';
      }
    }

    if (columns.indexOf('ERA') !== -1 && columns.indexOf('OPS') === -1 && rows.length >= 2) {
      return 'months-era';
    }

    if (splitIsOpsAgainst(columns) && rows.length >= 2) {
      return 'months-ops-against';
    }

    if (splitIsHittingOps(columns) && rows.length >= 2) {
      return 'months-ops';
    }

    return 'table';
  }

  function splitFormatRate(value, digits) {
    if (value === null || value === undefined || Number.isNaN(value)) return '';
    var precision = digits === undefined ? 3 : digits;
    var text = Math.abs(value).toFixed(precision);
    if (precision === 3 && text.startsWith('0.')) text = text.slice(1);
    return (value < 0 ? '-' : '') + text;
  }

  function splitHeroMeta(group, kind) {
    var meta = splitKindMeta(kind);
    var rows = group.rows || [];
    var metric = meta.metric;
    var higherBetter = meta.higherBetter;
    var values = rows.map(function (row, rowIndex) {
      return {
        rowIndex: rowIndex,
        value: splitParseNumber(splitCellValue(row, metric))
      };
    }).filter(function (entry) {
      return entry.value !== null;
    });

    if (!values.length) {
      return {
        metric: metric,
        higherBetter: higherBetter,
        diffDigits: meta.diffDigits,
        scaleWord: meta.scaleWord,
        leaderIndex: -1,
        scaleBest: null,
        scaleWorst: null,
        diff: null
      };
    }

    var bestEntryIndex = 0;
    values.forEach(function (entry, index) {
      var current = values[bestEntryIndex].value;
      if (higherBetter ? entry.value > current : entry.value < current) {
        bestEntryIndex = index;
      }
    });

    var leaderEntry = values[bestEntryIndex];
    var otherEntry = values.length > 1 ? values[1 - bestEntryIndex] : null;
    var diff = otherEntry === null ? null : (
      higherBetter
        ? leaderEntry.value - otherEntry.value
        : otherEntry.value - leaderEntry.value
    );

    var scaleBest = higherBetter
      ? Math.max.apply(null, values.map(function (entry) { return entry.value; }))
      : Math.min.apply(null, values.map(function (entry) { return entry.value; }));
    var scaleWorst = higherBetter
      ? Math.min.apply(null, values.map(function (entry) { return entry.value; }))
      : Math.max.apply(null, values.map(function (entry) { return entry.value; }));

    return {
      metric: metric,
      higherBetter: higherBetter,
      diffDigits: meta.diffDigits,
      scaleWord: meta.scaleWord,
      leaderIndex: leaderEntry.rowIndex,
      scaleBest: scaleBest,
      scaleWorst: scaleWorst,
      diff: diff
    };
  }

  function splitMetricRange(rows, metric, higherBetter) {
    var values = rows.map(function (row) {
      return splitParseNumber(splitCellValue(row, metric));
    }).filter(function (value) {
      return value !== null;
    });
    if (!values.length) return { best: null, worst: null };
    return higherBetter
      ? { best: Math.max.apply(null, values), worst: Math.min.apply(null, values) }
      : { best: Math.min.apply(null, values), worst: Math.max.apply(null, values) };
  }

  function splitMetricBarWidth(value, best, worst, higherBetter) {
    if (value === null || best === null) return 0;
    if (higherBetter) return Math.min(100, (value / best) * 100);
    if (worst === null || worst === 0) return 0;
    return Math.min(100, (value / worst) * 100);
  }

  function splitMetricTier(value, best, worst, higherBetter) {
    if (value === null || best === null || worst === null) return 'amber';
    if (worst === best) return 'green';
    var ratio = higherBetter
      ? (value - worst) / (best - worst)
      : (worst - value) / (worst - best);
    if (ratio >= 0.9) return 'green';
    if (ratio >= 0.75) return 'green-light';
    return 'amber';
  }

  function splitCardBarWidth(value, scaleBest, scaleWorst, higherBetter) {
    if (value === null) return 0;
    if (higherBetter) {
      if (scaleBest === null || scaleBest === 0) return 0;
      return Math.min(100, (value / scaleBest) * 100);
    }
    if (scaleWorst === null || scaleWorst === 0) return 0;
    return Math.min(100, (value / scaleWorst) * 100);
  }

  function splitVolumeLabel(row, preferredLabel) {
    var labels = preferredLabel ? [preferredLabel, 'PA', 'IP', 'BF'] : ['PA', 'IP', 'BF'];
    for (var i = 0; i < labels.length; i++) {
      var value = splitCellValue(row, labels[i]);
      if (value !== '—') return value + ' ' + labels[i];
    }
    return '';
  }

  function splitDetailText(row, labels) {
    var values = labels.map(function (label) {
      return splitCellValue(row, label);
    });
    if (!values.every(function (value) { return value !== '—'; })) return '';
    return values.join(' / ');
  }

  function buildSplitMiniStatsHtml(row, labels) {
    return labels.map(function (label) {
      return (
        '<div class="player-splits-mini-stat">' +
          '<div class="player-splits-mini-stat__label">' + escapeHtml(label) + '</div>' +
          '<div class="player-splits-mini-stat__value">' + escapeHtml(splitCellValue(row, label)) + '</div>' +
        '</div>'
      );
    }).join('');
  }

  function buildSplitCardHtml(row, options) {
    var heroMetric = options.heroMetric;
    var heroDisplay = splitCellValue(row, heroMetric);
    var volumeLabel = splitVolumeLabel(row, options.volumeLabel);
    var accent = options.accent || 'blue';
    var cardClass = 'player-splits-card' + (options.isLeader ? ' is-leader is-leader--' + accent : '');
    var heroClass = 'player-splits-ops' + (options.isLeader ? ' player-splits-ops--' + accent : '');
    var diffHtml = '';

    if (options.isLeader && options.diffText) {
      var diffClass = options.diffPositive ? 'player-splits-diff is-up' : 'player-splits-diff is-down';
      diffHtml = '<span class="' + diffClass + '">' + escapeHtml(options.diffText) + '</span>';
    }

    return (
      '<div class="' + cardClass + '">' +
        '<div class="player-splits-card__header">' +
          '<span class="player-splits-card__title">' + escapeHtml(row.label) + '</span>' +
          (volumeLabel ? '<span class="player-splits-card__pa">' + escapeHtml(volumeLabel) + '</span>' : '') +
        '</div>' +
        '<div class="player-splits-ops-row">' +
          '<span class="' + heroClass + '">' + escapeHtml(heroDisplay) + '</span>' +
          '<span class="player-splits-ops-label">' + escapeHtml(options.heroLabel || heroMetric) + '</span>' +
          diffHtml +
        '</div>' +
        '<div class="player-splits-ops-bar">' +
          '<span class="player-splits-ops-bar__fill is-' + accent +
          (options.isLeader ? '' : '-muted') + '" style="width:' + options.barWidth.toFixed(1) + '%"></span>' +
        '</div>' +
        '<div class="player-splits-mini-stats">' + buildSplitMiniStatsHtml(row, options.miniStats) + '</div>' +
      '</div>'
    );
  }

  function buildSplitCardsGroupHtml(group, kind) {
    var rows = group.rows || [];
    var meta = splitKindMeta(kind);
    var hero = splitHeroMeta(group, kind);
    var miniStats = kind === 'cards-era'
      ? splitPickMiniStats(group.columns || [], ['IP', 'WHIP', 'SO', 'BB', 'H', 'HR', 'SO9'])
      : kind === 'cards-ops-against'
        ? splitPickMiniStats(group.columns || [], ['BA', 'OBP', 'SLG', 'H', 'HR', 'SO', 'BB'])
        : splitPickMiniStats(group.columns || [], ['BA', 'OBP', 'SLG', 'HR', 'RBI', 'SO', 'BB']);

    var cardsHtml = rows.map(function (row, index) {
      var value = splitParseNumber(splitCellValue(row, hero.metric));
      var isLeader = index === hero.leaderIndex;
      var accent = isLeader ? 'green' : 'blue';
      var diffText = '';
      var diffPositive = true;
      if (isLeader && hero.diff !== null) {
        diffText = (hero.diff >= 0 ? '+' : '') + splitFormatRate(hero.diff, hero.diffDigits);
        diffPositive = hero.diff >= 0;
      }

      return buildSplitCardHtml(row, {
        heroMetric: hero.metric,
        heroLabel: kind === 'cards-ops-against' ? 'OPS Allowed' : hero.metric,
        volumeLabel: meta.volumeLabel,
        isLeader: isLeader,
        accent: accent,
        barWidth: splitCardBarWidth(value, hero.scaleBest, hero.scaleWorst, hero.higherBetter),
        diffText: diffText,
        diffPositive: diffPositive,
        miniStats: miniStats
      });
    }).join('');

    var scaleRef = hero.higherBetter ? hero.scaleBest : hero.scaleWorst;
    var scaleDisplay = scaleRef === null
      ? ''
      : hero.metric === 'ERA'
        ? scaleRef.toFixed(2)
        : splitFormatRate(scaleRef, 3);
    var scaleNote = scaleDisplay
      ? (hero.higherBetter
        ? hero.metric + (kind === 'cards-ops-against' ? ' allowed' : '') +
          ' bar scaled to ' + scaleDisplay + ' max'
        : 'Longer bar = higher ' + hero.metric +
          (kind === 'cards-ops-against' ? ' allowed' : '') +
          ' · scaled to ' + scaleDisplay + ' worst')
      : '';

    return (
      '<section class="player-splits-section">' +
        '<p class="player-splits-section__label">' + escapeHtml(group.title) + '</p>' +
        '<div class="player-splits-grid">' + cardsHtml + '</div>' +
        (scaleNote ? '<p class="player-splits-scale-note">' + escapeHtml(scaleNote) + '</p>' : '') +
      '</section>'
    );
  }

  function buildSplitMetricBarsGroupHtml(group, kind) {
    var rows = group.rows || [];
    var meta = splitKindMeta(kind);
    var metric = meta.metric;
    var range = splitMetricRange(rows, metric, meta.higherBetter);
    var isMonthGroup = String(group.title || '').toLowerCase().indexOf('month') !== -1;
    var detailLabels = (group.columns || []).indexOf('tOPS+') !== -1
      ? ['BA', 'OBP', 'SLG']
      : meta.detailLabels;
    var detailSuffix = (group.columns || []).indexOf('tOPS+') !== -1
      ? 'BA / OBP / SLG'
      : meta.detailSuffix;

    var rowsHtml = rows.map(function (row) {
      var metricDisplay = splitCellValue(row, metric);
      var metricValue = splitParseNumber(metricDisplay);
      var tier = splitMetricTier(metricValue, range.best, range.worst, meta.higherBetter);
      var barWidth = splitMetricBarWidth(metricValue, range.best, range.worst, meta.higherBetter);
      var volumeLabel = splitVolumeLabel(row, meta.volumeLabel);
      var detail = splitDetailText(row, detailLabels);

      return (
        '<div class="player-splits-month-row">' +
          '<div class="player-splits-month-row__name' +
          (isMonthGroup ? '' : ' player-splits-month-row__name--wide') + '">' +
          escapeHtml(row.label) + '</div>' +
          '<div class="player-splits-month-row__track">' +
            '<div class="player-splits-month-row__fill is-' + tier + '" style="width:' + barWidth.toFixed(1) + '%">' +
              '<span class="player-splits-month-row__ops is-' + tier + '">' + escapeHtml(metricDisplay) + '</span>' +
            '</div>' +
          '</div>' +
          (detail ? '<div class="player-splits-month-row__detail">' + escapeHtml(detail) + '</div>' : '') +
          (volumeLabel ? '<div class="player-splits-month-row__pa">' + escapeHtml(volumeLabel) + '</div>' : '') +
        '</div>'
      );
    }).join('');

    var scaleRef = meta.higherBetter ? range.best : range.worst;
    var scaleDisplay = scaleRef === null
      ? ''
      : metric === 'ERA'
        ? scaleRef.toFixed(2)
        : splitFormatRate(scaleRef, 3);
    var legendMetric = kind === 'months-ops-against' ? 'OPS allowed' : metric;
    var legendNote = meta.higherBetter
      ? (scaleDisplay
        ? 'Bars scaled to ' + scaleDisplay + ' ' + legendMetric + ' max · detail: ' + detailSuffix
        : 'detail: ' + detailSuffix)
      : (scaleDisplay
        ? 'Longer bar = higher ' + legendMetric + ' · scaled to ' + scaleDisplay +
          ' worst · detail: ' + detailSuffix
        : 'detail: ' + detailSuffix);

    return (
      '<section class="player-splits-section player-splits-section--bars">' +
        '<p class="player-splits-section__label">' + escapeHtml(group.title) + '</p>' +
        '<div class="player-splits-month-bars">' + rowsHtml + '</div>' +
        '<div class="player-splits-month-legend">' +
          '<span class="player-splits-month-legend__note">' + escapeHtml(legendNote) + '</span>' +
          '<div class="player-splits-month-legend__swatches">' +
            '<span class="player-splits-swatch"><span class="player-splits-swatch__dot is-amber"></span>' +
            escapeHtml(meta.legendLow) + '</span>' +
            '<span class="player-splits-swatch"><span class="player-splits-swatch__dot is-green"></span>' +
            escapeHtml(meta.legendHigh) + '</span>' +
          '</div>' +
        '</div>' +
      '</section>'
    );
  }

  function buildSplitTableGroupHtml(group) {
    var headerCells = '<th scope="col">Split</th>' +
      (group.columns || []).map(function (col) {
        return '<th scope="col">' + escapeHtml(col) + '</th>';
      }).join('');

    var bodyRows = (group.rows || []).map(function (row) {
      var cells = '<th scope="row">' + escapeHtml(row.label) + '</th>' +
        (row.cells || []).map(function (cell) {
          return '<td>' + escapeHtml(cell.value) + '</td>';
        }).join('');
      return '<tr>' + cells + '</tr>';
    }).join('');

    if (!bodyRows) return '';

    return (
      '<section class="player-splits-section player-splits-section--table">' +
        '<p class="player-splits-section__label">' + escapeHtml(group.title) + '</p>' +
        '<div class="player-stats-table-wrap player-splits-table-wrap">' +
          '<table class="player-stats-table player-splits-table">' +
            '<thead><tr>' + headerCells + '</tr></thead>' +
            '<tbody>' + bodyRows + '</tbody>' +
          '</table>' +
        '</div>' +
      '</section>'
    );
  }

  function buildSplitGroupHtml(group) {
    var rows = group.rows || [];
    if (!rows.length) return '';

    var kind = splitGroupKind(group);
    if (kind === 'months-ops' || kind === 'months-era' || kind === 'months-ops-against') {
      return buildSplitMetricBarsGroupHtml(group, kind);
    }
    if (kind.indexOf('cards-') === 0) return buildSplitCardsGroupHtml(group, kind);
    return buildSplitTableGroupHtml(group);
  }

  function buildSplitViewHtml(view) {
    var groups = (view.groups || []).map(buildSplitGroupHtml).filter(Boolean);
    if (!groups.length) {
      return '<p class="player-splits-empty">No split data for this view.</p>';
    }
    return '<div class="player-splits-groups">' + groups.join('') + '</div>';
  }

  function buildHitProfileHtml(panel) {
    var pillars = panel.pillars || [];
    var groups = panel.groups || [];
    var tendency = panel.contact_tendency;
    var profileType = panel.profile_type || 'batter';
    var profileKicker = profileType === 'pitcher' ? 'Pitcher profile' : 'Hitter profile';
    var archetype = panel.archetype;
    var archetypeLabel = archetype
      ? (typeof archetype === 'string' ? archetype : archetype.label)
      : null;
    var archetypeTheme = archetype && archetype.theme ? archetype.theme : 'balanced';
    var archetypeDrivers = archetype && archetype.drivers ? archetype.drivers : [];
    var archetypeSignals = archetype && archetype.signals ? archetype.signals : [];

    if (!archetypeLabel && !pillars.length && !groups.length) {
      return '<p class="player-splits-empty">Advanced stats unavailable.</p>';
    }

    var archetypeHtml = archetypeLabel
      ? (
        '<section class="hit-profile__hero hit-profile__hero--' + escapeHtml(archetypeTheme) + '">' +
          '<span class="hit-profile__hero-kicker">' + escapeHtml(profileKicker) + '</span>' +
          '<h3 class="hit-profile__hero-title">' + escapeHtml(archetypeLabel) + '</h3>' +
          (archetypeDrivers.length
            ? '<p class="hit-profile__hero-copy">' + escapeHtml(archetypeDrivers[0]) + '</p>'
            : '') +
          (archetypeSignals.length
            ? (
              '<ul class="hit-profile__signals" aria-label="Profile inputs">' +
                archetypeSignals.map(function (signal) {
                  var kind = signal.kind || 'default';
                  var detailHtml = signal.detail
                    ? '<span class="hit-profile__signal-detail">' + escapeHtml(signal.detail) + '</span>'
                    : '';
                  return (
                    '<li class="hit-profile__signal hit-profile__signal--' + escapeHtml(kind) + '">' +
                      '<span class="hit-profile__signal-label">' + escapeHtml(signal.label) + '</span>' +
                      '<span class="hit-profile__signal-value">' + escapeHtml(signal.value || '—') + '</span>' +
                      detailHtml +
                    '</li>'
                  );
                }).join('') +
              '</ul>'
            )
            : '') +
        '</section>'
      )
      : '';

    var pillarsHtml = pillars.map(function (pillar) {
      var pillarId = pillar.id || 'default';
      var tier = pillar.tier || 'average';
      var tierLabel = pillar.tier_label || '';
      var noteHtml = pillar.note
        ? '<span class="hit-profile__pillar-note">' + escapeHtml(pillar.note) + '</span>'
        : '';
      var indicatorHtml = tierLabel
        ? '<span class="hit-profile__pillar-indicator hit-profile__pillar-indicator--' + escapeHtml(tier) + '">' + escapeHtml(tierLabel) + '</span>'
        : '';
      return (
        '<article class="hit-profile__pillar hit-profile__pillar--' + escapeHtml(tier) + '">' +
          indicatorHtml +
          '<span class="hit-profile__pillar-value hit-profile__pillar-value--' + escapeHtml(tier) + '">' + escapeHtml(pillar.value || '—') + '</span>' +
          '<span class="hit-profile__pillar-label">' + escapeHtml(pillar.label) + '</span>' +
          noteHtml +
        '</article>'
      );
    }).join('');

    var tendencyHtml = '';
    if (tendency && tendency.ground_pct != null) {
      var groundPct = Number(tendency.ground_pct);
      var flyPct = Number(tendency.fly_pct);
      var groundLabel = tendency.ground_label || 'Ground outs';
      var flyLabel = tendency.fly_label || 'Fly outs';
      var goFoText = tendency.go_fo != null ? Number(tendency.go_fo).toFixed(2) : '';
      var spectrumLabel = groundLabel + ' ' + groundPct.toFixed(1) + '%, ' + flyLabel + ' ' + flyPct.toFixed(1) + '%';
      var ratioLabel = tendency.ratio_label || 'GO/FO';
      var tendencyCaption = tendency.caption || '';
      var groundWidth = Math.max(0, Math.min(100, groundPct));
      var flyWidth = Math.max(0, Math.min(100, flyPct));
      var markerLeft = Math.max(4, Math.min(96, groundWidth));
      tendencyHtml =
        '<section class="hit-profile__tendency">' +
          '<div class="hit-profile__tendency-head">' +
            '<div class="hit-profile__tendency-title-wrap">' +
              '<span class="hit-profile__section-icon" aria-hidden="true">◐</span>' +
              '<h4 class="hit-profile__section-title">Batted-ball tendency</h4>' +
            '</div>' +
            (goFoText ? '<span class="hit-profile__tendency-ratio">' + escapeHtml(ratioLabel) + ' ' + escapeHtml(goFoText) + '</span>' : '') +
          '</div>' +
          '<div class="hit-profile__tendency-spectrum" role="img" aria-label="' + escapeHtml(spectrumLabel) + '">' +
            '<div class="hit-profile__tendency-axis">' +
              '<span class="hit-profile__tendency-axis-label hit-profile__tendency-axis-label--ground">' +
                escapeHtml(groundLabel) + ' <strong>' + escapeHtml(String(tendency.ground_pct)) + '%</strong>' +
              '</span>' +
              '<span class="hit-profile__tendency-axis-label hit-profile__tendency-axis-label--fly">' +
                escapeHtml(flyLabel) + ' <strong>' + escapeHtml(String(tendency.fly_pct)) + '%</strong>' +
              '</span>' +
            '</div>' +
            '<div class="hit-profile__tendency-track">' +
              '<span class="hit-profile__tendency-segment hit-profile__tendency-segment--ground" style="width:' + groundWidth.toFixed(1) + '%"></span>' +
              '<span class="hit-profile__tendency-segment hit-profile__tendency-segment--fly" style="width:' + flyWidth.toFixed(1) + '%"></span>' +
              '<span class="hit-profile__tendency-marker" style="left:' + markerLeft.toFixed(1) + '%" title="' + escapeHtml(spectrumLabel) + '"></span>' +
            '</div>' +
            (tendencyCaption
              ? '<p class="hit-profile__tendency-caption">' + escapeHtml(tendencyCaption) + '</p>'
              : '') +
          '</div>' +
        '</section>';
    }

    var groupsHtml = groups.map(function (group) {
      var groupId = group.id || group.label.toLowerCase();
      var statsHtml = (group.stats || []).map(function (stat) {
        var noteHtml = stat.note
          ? '<span class="hit-profile__stat-note">' + escapeHtml(stat.note) + '</span>'
          : '';
        return (
          '<div class="hit-profile__stat">' +
            '<span class="hit-profile__stat-label">' + escapeHtml(stat.label) + '</span>' +
            '<div class="hit-profile__stat-value-wrap">' +
              '<span class="hit-profile__stat-value">' + escapeHtml(stat.value || '—') + '</span>' +
              noteHtml +
            '</div>' +
          '</div>'
        );
      }).join('');
      return (
        '<section class="hit-profile__group hit-profile__group--' + escapeHtml(groupId) + '">' +
          '<h4 class="hit-profile__section-title">' + escapeHtml(group.label) + '</h4>' +
          '<div class="hit-profile__stats">' + statsHtml + '</div>' +
        '</section>'
      );
    }).join('');

    var bodyHtml = '';
    if (pillarsHtml || tendencyHtml) {
      bodyHtml +=
        '<div class="hit-profile__body">' +
          (pillarsHtml ? '<div class="hit-profile__pillars">' + pillarsHtml + '</div>' : '') +
          tendencyHtml +
        '</div>';
    }

    return (
      '<div class="hit-profile">' +
        archetypeHtml +
        bodyHtml +
        (groupsHtml ? '<div class="hit-profile__groups">' + groupsHtml + '</div>' : '') +
      '</div>'
    );
  }

  /*
  function percentileFillColor(pct) {
    var p = Math.max(0, Math.min(100, Number(pct) || 0));
    if (p >= 90) return '#d4183d';
    if (p >= 75) return '#e67e22';
    if (p >= 50) return '#c9a227';
    if (p >= 25) return '#5b9bd5';
    return '#2e6db4';
  }

  function buildPercentileRowHtml(metric, panel) {
    if (panel && panel.qualified === false && metric.display) {
      return (
        '<div class="percentile-rank-row percentile-rank-row--raw">' +
          '<span class="percentile-rank-row__label">' + escapeHtml(metric.label) + '</span>' +
          '<span class="percentile-rank-row__stat">' + escapeHtml(metric.display) + '</span>' +
        '</div>'
      );
    }

    var pct = Math.max(0, Math.min(100, Number(metric.value) || 0));
    var color = percentileFillColor(pct);
    return (
      '<div class="percentile-rank-row">' +
        '<span class="percentile-rank-row__label">' + escapeHtml(metric.label) + '</span>' +
        '<div class="percentile-rank-row__track" aria-hidden="true">' +
          '<span class="percentile-rank-row__fill" style="width:' + pct.toFixed(1) +
          '%;background:' + color + '"></span>' +
        '</div>' +
        '<span class="percentile-rank-row__value">' + escapeHtml(String(Math.round(pct))) + '</span>' +
      '</div>'
    );
  }

  function buildPercentileGroupHtml(group, panel) {
    var rows = (group.metrics || []).map(function (metric) {
      return buildPercentileRowHtml(metric, panel);
    }).join('');
    if (!rows) return '';
    return (
      '<section class="percentile-ranks__group">' +
        '<h4 class="percentile-ranks__group-title">' + escapeHtml(group.title) + '</h4>' +
        '<div class="percentile-ranks__rows">' + rows + '</div>' +
      '</section>'
    );
  }

  function percentileYearOptions(panel) {
    if (panel.available_years && panel.available_years.length) {
      return panel.available_years.slice();
    }
    var years = [];
    var end = new Date().getFullYear();
    for (var y = end; y >= 2015; y--) {
      years.push(String(y));
    }
    return years;
  }

  function buildPercentileHeadingHtml(panel) {
    var seasonYear = String(panel.season_year || new Date().getFullYear());
    var years = percentileYearOptions(panel);
    if (years.indexOf(seasonYear) === -1) {
      years.unshift(seasonYear);
    }
    var optionsHtml = years.map(function (year) {
      return (
        '<option value="' + escapeHtml(year) + '"' +
        (year === seasonYear ? ' selected' : '') + '>' +
        escapeHtml(year) + '</option>'
      );
    }).join('');

    return (
      '<h2 class="percentile-ranks__heading">' +
        '<select class="percentile-ranks__year-select" aria-label="Season year">' +
        optionsHtml +
        '</select>' +
        ' Statcast Percentiles' +
      '</h2>'
    );
  }

  function buildPercentileLegendHtml() {
    return (
      '<div class="percentile-ranks__legend">' +
        '<span class="percentile-ranks__legend-item"><span class="percentile-ranks__swatch" style="background:#2e6db4"></span>0–25</span>' +
        '<span class="percentile-ranks__legend-item"><span class="percentile-ranks__swatch" style="background:#5b9bd5"></span>25–50</span>' +
        '<span class="percentile-ranks__legend-item"><span class="percentile-ranks__swatch" style="background:#c9a227"></span>50–75</span>' +
        '<span class="percentile-ranks__legend-item"><span class="percentile-ranks__swatch" style="background:#e67e22"></span>75–90</span>' +
        '<span class="percentile-ranks__legend-item"><span class="percentile-ranks__swatch" style="background:#d4183d"></span>90+</span>' +
      '</div>'
    );
  }

  function buildPercentileNoticeHtml(panel) {
    if (panel.qualified !== false) return '';
    var seasonYear = String(panel.season_year || '');
    return (
      '<div class="percentile-ranks__notice" role="status">' +
        'Not Qualified' +
        (seasonYear ? ' for ' + escapeHtml(seasonYear) : '') +
        '<span class="percentile-ranks__notice-detail">Season Statcast stats shown below. Percentile ranks unavailable.</span>' +
      '</div>'
    );
  }

  function buildPercentileRankingsHtml(panel) {
    var seasonYear = String(panel.season_year || '');
    var headingHtml = buildPercentileHeadingHtml(panel);
    var noticeHtml = buildPercentileNoticeHtml(panel);
    var groups = (panel.groups || []).map(function (group) {
      return buildPercentileGroupHtml(group, panel);
    }).filter(Boolean);

    if (!groups.length) {
      return (
        '<div class="percentile-ranks">' +
          headingHtml +
          noticeHtml +
          '<p class="player-splits-empty">No Statcast data' +
          (seasonYear ? ' for ' + escapeHtml(seasonYear) : '') + '.</p>' +
        '</div>'
      );
    }

    return (
      '<div class="percentile-ranks">' +
        headingHtml +
        noticeHtml +
        '<div class="percentile-ranks__grid">' + groups.join('') + '</div>' +
        (panel.qualified === false ? '' : buildPercentileLegendHtml()) +
      '</div>'
    );
  }

  function loadPercentilePanel(panelEl, seasonYear) {
    panelEl.setAttribute('aria-busy', 'true');
    fetch(
      '/api/mlb/player/' + encodeURIComponent(playerId) +
      '/percentile-ranks?season_year=' + encodeURIComponent(seasonYear)
    )
      .then(function (response) {
        if (!response.ok) throw new Error('Percentiles unavailable');
        return response.json();
      })
      .then(function (panel) {
        panelEl.innerHTML = buildPercentileRankingsHtml(panel);
        panelEl.removeAttribute('aria-busy');
        initPercentileYearSelects();
      })
      .catch(function () {
        panelEl.removeAttribute('aria-busy');
      });
  }

  function initPercentileYearSelects() {
    if (!panelsEl) return;
    panelsEl.querySelectorAll('.player-stats-panel--percentile').forEach(function (panelEl) {
      var select = panelEl.querySelector('.percentile-ranks__year-select');
      if (!select || select.dataset.bound === 'true') return;
      select.dataset.bound = 'true';
      select.addEventListener('change', function () {
        loadPercentilePanel(panelEl, select.value);
      });
    });
  }
  */

  function buildPanelInnerHtml(panel) {
    if (panel.panel_kind === 'toggle_stat_bars') {
      var statDefaultView = panel.default_view || (panel.views[0] && panel.views[0].id);
      var statViews = panel.views || [];
      var statToggleHtml = statViews.length > 1
        ? buildToggleHtml(panel.id, statViews, statDefaultView)
        : '';
      var statViewsHtml = statViews.map(function (view) {
        var viewContent;
        if (view.loading) {
          viewContent = buildPanelLoadingHtml();
        } else if (view.nested_panel) {
          viewContent = buildSeasonStatsNestedHtml(view.nested_panel);
        } else if (view.stats_table) {
          viewContent = buildStatsTableHtml(view.stats_table);
          if (!viewContent) {
            viewContent = '<p class="player-splits-empty">Season summary unavailable.</p>';
          }
        } else {
          viewContent = buildStatBarsHtml(view);
        }
        return (
          '<div class="player-panel-view" data-panel="' + escapeHtml(panel.id) +
          '" data-view="' + escapeHtml(view.id) + '"' +
          (view.id === statDefaultView ? '' : ' hidden') + '>' +
          viewContent +
          '</div>'
        );
      }).join('');
      return (
        (statToggleHtml ? '<div class="player-panel-header">' + statToggleHtml + '</div>' : '') +
        '<div class="team-panel-body">' + statViewsHtml + '</div>'
      );
    }

    if (panel.panel_kind === 'toggle_table') {
      var defaultView = panel.default_view || (panel.views[0] && panel.views[0].id);
      var toggleHtml = buildToggleHtml(panel.id, panel.views, defaultView);
      var viewsHtml = panel.views.map(function (view) {
        return (
          '<div class="player-panel-view" data-panel="' + escapeHtml(panel.id) +
          '" data-view="' + escapeHtml(view.id) + '"' +
          (view.id === defaultView ? '' : ' hidden') + '>' +
          buildSeasonCareerTableHtml(view.stats_table) +
          '</div>'
        );
      }).join('');
      return (
        '<div class="player-panel-header">' + toggleHtml + '</div>' +
        '<div class="player-panel-body">' + viewsHtml + '</div>'
      );
    }

    if (panel.panel_kind === 'hit_profile') {
      return '<div class="player-panel-body">' + buildHitProfileHtml(panel) + '</div>';
    }

    /*
    if (panel.panel_kind === 'percentile_ranks') {
      return buildPercentileRankingsHtml(panel);
    }
    */

    if (panel.panel_kind === 'percentile_coming_soon') {
      return '<div class="player-panel-body">' + buildPercentileComingSoonHtml() + '</div>';
    }

    if (panel.panel_kind === 'split_groups') {
      return (
        '<div class="player-panel-body">' +
        buildSplitViewHtml({ groups: panel.groups || [] }) +
        '</div>'
      );
    }

    if (panel.panel_kind === 'season_table') {
      return '<div class="player-panel-body">' + buildSeasonCareerTableHtml(panel.stats_table) + '</div>';
    }

    if (panel.panel_kind === 'toggle_splits') {
      var splitDefault = panel.default_view || (panel.views[0] && panel.views[0].id);
      var splitToggle = buildToggleHtml(panel.id, panel.views, splitDefault);
      var splitViews = panel.views.map(function (view) {
        return (
          '<div class="player-panel-view" data-panel="' + escapeHtml(panel.id) +
          '" data-view="' + escapeHtml(view.id) + '"' +
          (view.id === splitDefault ? '' : ' hidden') + '>' +
          buildSplitViewHtml(view) +
          '</div>'
        );
      }).join('');
      return (
        '<div class="player-panel-header">' + splitToggle + '</div>' +
        '<div class="player-panel-body">' + splitViews + '</div>'
      );
    }

    if (panel.panel_kind === 'loading') {
      return buildPanelLoadingHtml();
    }

    if (panel.panel_kind === 'lazy') {
      return '<div class="team-panel-body team-panel-body--lazy"></div>';
    }

    if (panel.stats_table) {
      return '<div class="player-panel-body">' + buildSeasonCareerTableHtml(panel.stats_table) + '</div>';
    }

    return '';
  }

  function initPanelToggles(root) {
    root.querySelectorAll('.player-panel-toggle__btn[data-view]').forEach(function (btn) {
      if (btn.dataset.toggleBound === 'true') return;
      btn.dataset.toggleBound = 'true';
      btn.addEventListener('click', function () {
        var panelId = btn.getAttribute('data-panel');
        var viewId = btn.getAttribute('data-view');
        if (!viewId) return;

        var panel = btn.closest('.player-stats-panel');
        if (!panel || !panelId) return;

        var toggleGroup = btn.closest('.player-panel-toggle');
        if (toggleGroup) {
          toggleGroup.querySelectorAll('.player-panel-toggle__btn').forEach(function (toggleBtn) {
            var isActive = toggleBtn.getAttribute('data-view') === viewId;
            toggleBtn.classList.toggle('is-active', isActive);
            toggleBtn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
          });
        }

        panel.querySelectorAll('.player-panel-view[data-panel="' + panelId + '"]').forEach(function (viewEl) {
          viewEl.hidden = viewEl.getAttribute('data-view') !== viewId;
        });
      });
    });
  }

  function panelClassFor(panel) {
    var panelClass = 'game-detail-section game-detail-panel player-stats-panel';
    /*
    if (panel.panel_kind === 'percentile_ranks') {
      panelClass += ' player-stats-panel--percentile';
    }
    */
    if (panel.panel_kind === 'toggle_stat_bars') {
      panelClass += ' team-stats-panel';
    }
    return panelClass;
  }

  var PANEL_ORDER = ['player_stats', visualPanelId, 'splits', 'percentile_ranks'];
  var activePanelId = null;
  var tabNavigationBound = false;
  var LAZY_PANEL_CONFIG = {
    /*
    percentile_ranks: {
      label: 'Percentile Rankings',
      path: '/stats/percentiles',
      payloadKey: 'stat_panel',
    },
    */
    splits: {
      label: 'Splits',
      path: '/stats/splits',
      payloadKey: 'stat_panel',
    },
  };
  var lazyPanelState = {};

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
      '<section class="' + panelClassFor(panel) + '"' +
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
    var insertBefore = findPanelInsertBefore(panel.id, panelsEl, '.player-stats-panel');
    var sectionHtml = buildPanelSectionHtml(panel, isActive);
    if (insertBefore) {
      insertBefore.insertAdjacentHTML('beforebegin', sectionHtml);
    } else {
      panelsEl.insertAdjacentHTML('beforeend', sectionHtml);
    }
    return panelsEl.querySelector('.player-stats-panel[data-panel="' + panel.id + '"]');
  }

  function wirePanelElement(panelEl) {
    if (!panelEl) return;
    initPanelToggles(panelEl);
    // initPercentileYearSelects();
    initSeasonStatsPanels(panelEl);
  }

  function setActivePanel(panelId) {
    activePanelId = panelId;
    if (!tabsEl || !panelsEl) return;

    tabsEl.querySelectorAll('.game-detail-tab').forEach(function (tab) {
      var isActive = tab.getAttribute('data-panel') === panelId;
      tab.classList.toggle('is-active', isActive);
      tab.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
    panelsEl.querySelectorAll('.player-stats-panel').forEach(function (panel) {
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
      ensureLazyPanelLoaded(panelId);
      requestAnimationFrame(function () {
        var panel = panelsEl.querySelector('.player-stats-panel[data-panel="' + panelId + '"]');
        if (panel && !panel.hidden) {
          panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
      });
    });
  }

  function upsertPanel(panel) {
    if (!tabsEl || !panelsEl || !panel || !panel.id) return;

    var existingTab = tabsEl.querySelector('.game-detail-tab[data-panel="' + panel.id + '"]');
    var existingPanel = panelsEl.querySelector('.player-stats-panel[data-panel="' + panel.id + '"]');
    var shouldActivate = activePanelId === panel.id;

    if (!existingTab) {
      insertTab(panel, shouldActivate);
    } else {
      existingTab.textContent = panel.label;
    }

    if (existingPanel) {
      existingPanel.className = panelClassFor(panel);
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

    var profileLoaded = panels.some(function (panel) {
      return panel.id === 'hit_profile' || panel.id === 'pitch_profile';
    });
    if (!profileLoaded) {
      upsertPanel({ id: visualPanelId, label: visualPanelLabel, panel_kind: 'loading' });
    }
    registerLazyPanelTab('splits');
    registerPercentileComingSoonTab();

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

    var existingPanel = panelsEl.querySelector('.player-stats-panel[data-panel="' + panelId + '"]');
    if (existingPanel) {
      existingPanel.innerHTML =
        '<div class="team-panel-body"><p class="player-splits-empty">Unavailable right now.</p></div>';
    }
  }

  function fetchPlayerStats(path) {
    return fetch('/api/mlb/player/' + encodeURIComponent(playerId) + path).then(function (response) {
      if (!response.ok) throw new Error('Stats unavailable');
      return response.json();
    });
  }

  function registerLazyPanelTab(panelId) {
    var config = LAZY_PANEL_CONFIG[panelId];
    if (!config) return;
    lazyPanelState[panelId] = 'idle';
    upsertPanel({
      id: panelId,
      label: config.label,
      panel_kind: 'lazy',
    });
  }

  function registerPercentileComingSoonTab() {
    upsertPanel({
      id: 'percentile_ranks',
      label: 'Percentile Rankings',
      panel_kind: 'percentile_coming_soon',
    });
  }

  function ensureLazyPanelLoaded(panelId) {
    var config = LAZY_PANEL_CONFIG[panelId];
    if (!config) return;

    var state = lazyPanelState[panelId];
    if (state === 'loading' || state === 'loaded') return;

    lazyPanelState[panelId] = 'loading';
    var existingPanel = panelsEl.querySelector('.player-stats-panel[data-panel="' + panelId + '"]');
    if (existingPanel) {
      existingPanel.innerHTML = buildPanelLoadingHtml();
    }

    fetchPlayerStats(config.path)
      .then(function (payload) {
        var panel = payload[config.payloadKey];
        if (panel) {
          lazyPanelState[panelId] = 'loaded';
          upsertPanel(panel);
          if (activePanelId === panelId) {
            setActivePanel(panelId);
          }
          return;
        }
        lazyPanelState[panelId] = 'error';
        fulfillStagedPanel(panelId, null);
      })
      .catch(function () {
        lazyPanelState[panelId] = 'error';
        fulfillStagedPanel(panelId, null);
      });
  }

  function finishLoading() {
    rootEl.setAttribute('aria-busy', 'false');
  }

  function showError() {
    if (tabsEl) tabsEl.hidden = true;
    panelsEl.innerHTML = '<p class="player-stats-error">Stats unavailable right now.</p>';
    finishLoading();
  }

  function showLeagueStats(payload) {
    if (!payload.stat_panel) {
      showError();
      return;
    }

    var panels = [payload.stat_panel];
    if (payload.profile_panel) {
      panels.push(payload.profile_panel);
    }
    initCorePanels(panels);
    finishLoading();
  }

  panelsEl.innerHTML = buildPanelLoadingHtml();

  fetchPlayerStats('/stats/league')
    .then(showLeagueStats)
    .catch(showError);
})();

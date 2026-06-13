(function () {
  var section = document.getElementById('player-stats-section');
  if (!section) return;

  var playerId = section.getAttribute('data-player-id');
  var loadingEl = document.getElementById('player-stats-loading');
  var errorEl = document.getElementById('player-stats-error');
  var summaryEl = document.getElementById('player-stats-summary');
  var tabsEl = document.getElementById('player-stats-tabs');
  var panelsEl = document.getElementById('player-stats-panels');

  if (!playerId || !loadingEl || !summaryEl) return;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildSeasonCareerTableHtml(statsTable) {
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

  function buildSplitGroupHtml(group) {
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
      '<div class="player-splits-group">' +
        '<h4 class="player-splits-group__title">' + escapeHtml(group.title) + '</h4>' +
        '<div class="player-stats-table-wrap">' +
          '<table class="player-stats-table player-splits-table">' +
            '<thead><tr>' + headerCells + '</tr></thead>' +
            '<tbody>' + bodyRows + '</tbody>' +
          '</table>' +
        '</div>' +
      '</div>'
    );
  }

  function buildSplitViewHtml(view) {
    var groups = (view.groups || []).map(buildSplitGroupHtml).filter(Boolean).join('');
    if (!groups) {
      return '<p class="player-splits-empty">No split data for this view.</p>';
    }
    return '<div class="player-splits-groups">' + groups + '</div>';
  }

  var PITCH_COLORS = {
    FF: '#e74c3c',
    SI: '#e67e22',
    FC: '#f1c40f',
    SL: '#3498db',
    CU: '#9b59b6',
    CH: '#2ecc71',
    FS: '#1abc9c',
    ST: '#e91e63',
    KN: '#95a5a6',
    SV: '#16a085',
    EP: '#8e44ad',
    SC: '#34495e'
  };
  var PITCH_PALETTE = [
    '#e74c3c', '#3498db', '#2ecc71', '#9b59b6', '#e67e22',
    '#1abc9c', '#e91e63', '#f1c40f', '#16a085', '#34495e'
  ];

  function pitchColor(pitch, index) {
    var code = (pitch.pitch_type || '').toUpperCase();
    if (PITCH_COLORS[code]) return PITCH_COLORS[code];
    return PITCH_PALETTE[index % PITCH_PALETTE.length];
  }

  function buildDonutGradient(pitches) {
    var total = 0;
    pitches.forEach(function (p) {
      total += Number(p.usage) || 0;
    });
    if (total <= 0) return '#eef1f5';

    var cursor = 0;
    var stops = [];
    pitches.forEach(function (pitch, index) {
      var usage = Number(pitch.usage) || 0;
      if (usage <= 0) return;
      var start = (cursor / total) * 100;
      cursor += usage;
      var end = (cursor / total) * 100;
      stops.push(pitchColor(pitch, index) + ' ' + start.toFixed(2) + '% ' + end.toFixed(2) + '%');
    });
    return 'conic-gradient(' + stops.join(', ') + ')';
  }

  function formatPitchMetricValue(metric, value) {
    if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
      return '—';
    }
    var num = Number(value);
    if (metric.id === 'velo') return num.toFixed(1);
    if (metric.id === 'spin') return String(Math.round(num));
    if (metric.unit === '%') return num.toFixed(1);
    if (metric.id === 'xwoba' || metric.id === 'ba' || metric.id === 'slg') {
      var rateText = num.toFixed(3);
      return rateText.startsWith('0.') ? rateText.slice(1) : rateText;
    }
    return String(num);
  }

  function metricBarWidth(metric, value, pitches) {
    var num = Number(value);
    if (!num && num !== 0) return 0;
    var max = Number(metric.max) || 100;
    var dataMax = 0;
    pitches.forEach(function (pitch) {
      var v = Number(pitch[metric.id]);
      if (!Number.isNaN(v) && v > dataMax) dataMax = v;
    });
    var scaleMax = Math.max(max, dataMax * 1.05);
    return Math.min(100, (num / scaleMax) * 100);
  }

  function buildPitchMixHtml(panel) {
    var pitches = panel.pitches || [];
    var metrics = panel.metrics || [];
    if (!pitches.length) {
      return '<p class="player-splits-empty">No pitch mix data available.</p>';
    }

    var donutStyle = 'background:' + buildDonutGradient(pitches);
    var legendHtml = pitches.map(function (pitch, index) {
      var usage = Number(pitch.usage);
      var usageText = Number.isNaN(usage) ? '—' : usage.toFixed(1) + '%';
      return (
        '<li class="pitch-mix-legend__item">' +
          '<span class="pitch-mix-legend__swatch" style="background:' + pitchColor(pitch, index) + '"></span>' +
          '<span class="pitch-mix-legend__label">' + escapeHtml(pitch.label) + '</span>' +
          '<span class="pitch-mix-legend__value">' + escapeHtml(usageText) + '</span>' +
        '</li>'
      );
    }).join('');

    var metricsHtml = metrics.map(function (metric) {
      var barsHtml = pitches.map(function (pitch, index) {
        var value = pitch[metric.id];
        var display = formatPitchMetricValue(metric, value);
        var width = metricBarWidth(metric, value, pitches);
        var suffix = '';
        if (display !== '—') {
          if (metric.unit === '%') suffix = '%';
          else if (metric.unit) suffix = ' ' + metric.unit;
        }
        return (
          '<div class="pitch-mix-bar-row">' +
            '<span class="pitch-mix-bar-row__label" title="' + escapeHtml(pitch.label) + '">' +
              escapeHtml(pitch.label) +
            '</span>' +
            '<div class="pitch-mix-bar-row__track" aria-hidden="true">' +
              '<span class="pitch-mix-bar-row__fill" style="width:' + width.toFixed(1) + '%;background:' +
              pitchColor(pitch, index) + '"></span>' +
            '</div>' +
            '<span class="pitch-mix-bar-row__value">' + escapeHtml(display + suffix) + '</span>' +
          '</div>'
        );
      }).join('');

      return (
        '<section class="pitch-mix-metric">' +
          '<h4 class="pitch-mix-metric__title">' + escapeHtml(metric.label) + '</h4>' +
          '<div class="pitch-mix-metric__bars">' + barsHtml + '</div>' +
        '</section>'
      );
    }).join('');

    return (
      '<div class="pitch-mix">' +
        '<div class="pitch-mix__top">' +
          '<div class="pitch-mix-donut-wrap">' +
            '<div class="pitch-mix-donut" style="' + donutStyle + '" role="img" aria-label="Pitch usage breakdown">' +
              '<div class="pitch-mix-donut__hole"></div>' +
            '</div>' +
            '<p class="pitch-mix-donut__caption">' + escapeHtml(panel.season_year || 'Season') + ' Usage</p>' +
          '</div>' +
          '<ul class="pitch-mix-legend">' + legendHtml + '</ul>' +
        '</div>' +
        '<div class="pitch-mix__metrics">' + metricsHtml + '</div>' +
      '</div>'
    );
  }

  function buildPanelInnerHtml(panel) {
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

    if (panel.panel_kind === 'pitch_mix') {
      return '<div class="player-panel-body">' + buildPitchMixHtml(panel) + '</div>';
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

    if (panel.stats_table) {
      return '<div class="player-panel-body">' + buildSeasonCareerTableHtml(panel.stats_table) + '</div>';
    }

    return '';
  }

  function initPanelToggles(root) {
    root.querySelectorAll('.player-panel-toggle__btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var panelId = btn.getAttribute('data-panel');
        var viewId = btn.getAttribute('data-view');
        var panel = root.querySelector('.player-stats-panel[data-panel="' + panelId + '"]');
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

  function renderSummary(statsTable) {
    var html = buildSeasonCareerTableHtml(statsTable);
    if (!html) return false;
    summaryEl.innerHTML = html;
    return true;
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
        '<section class="game-detail-section game-detail-panel player-stats-panel" data-panel="' +
        escapeHtml(panel.id) + '"' +
        (index === 0 ? '' : ' hidden') + '>' +
        buildPanelInnerHtml(panel) +
        '</section>'
      );
    }).join('');

    tabsEl.hidden = false;
    initPanelToggles(panelsEl);

    var buttons = tabsEl.querySelectorAll('.game-detail-tab');
    var panels = panelsEl.querySelectorAll('.player-stats-panel');

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

    buttons.forEach(function (btn) {
      btn.addEventListener('click', function () {
        showPanel(btn.getAttribute('data-panel'));
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

  function showSummaryUnavailable() {
    summaryEl.innerHTML = '<p class="player-stats-error player-stats-error--inline">Season summary unavailable right now.</p>';
    summaryEl.hidden = false;
  }

  function showStats(payload) {
    var hasSummary = payload.stats_table && renderSummary(payload.stats_table);
    var hasPanels = payload.stat_panels && payload.stat_panels.length;

    if (!hasSummary && !hasPanels) {
      showError();
      return;
    }

    loadingEl.hidden = true;
    if (errorEl) errorEl.hidden = true;

    if (hasSummary) {
      summaryEl.hidden = false;
    } else {
      showSummaryUnavailable();
    }

    initStatPanels(payload.stat_panels || []);
    finishLoading();
  }

  fetch('/api/mlb/player/' + encodeURIComponent(playerId) + '/stats')
    .then(function (response) {
      if (!response.ok) throw new Error('Stats unavailable');
      return response.json();
    })
    .then(showStats)
    .catch(showError);
})();

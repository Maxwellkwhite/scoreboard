(function () {
  var section = document.getElementById('player-stats-section');
  if (!section) return;

  var playerId = section.getAttribute('data-player-id');
  var isPitcher = section.getAttribute('data-is-pitcher') === 'true';
  var visualPanelId = isPitcher ? 'pitch_mix' : 'spray_chart';
  var visualPanelLabel = isPitcher ? 'Pitch Mix' : 'Batting Metrics';
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

  var BB_TYPE_COLORS = {
    ground_ball: '#c9956a',
    line_drive: '#e74c3c',
    fly_ball: '#3498db',
    popup: '#95a5a6'
  };
  var BB_TYPE_PALETTE = ['#c9956a', '#e74c3c', '#3498db', '#95a5a6', '#2ecc71', '#9b59b6'];

  function bbTypeColor(bbType, index) {
    if (BB_TYPE_COLORS[bbType]) return BB_TYPE_COLORS[bbType];
    return BB_TYPE_PALETTE[index % BB_TYPE_PALETTE.length];
  }

  function buildUsageDonutGradient(items, colorFn) {
    var total = 0;
    items.forEach(function (item) {
      total += Number(item.usage) || 0;
    });
    if (total <= 0) return '#eef1f5';

    var cursor = 0;
    var stops = [];
    items.forEach(function (item, index) {
      var usage = Number(item.usage) || 0;
      if (usage <= 0) return;
      var start = (cursor / total) * 100;
      cursor += usage;
      var end = (cursor / total) * 100;
      stops.push(colorFn(item, index) + ' ' + start.toFixed(2) + '% ' + end.toFixed(2) + '%');
    });
    return 'conic-gradient(' + stops.join(', ') + ')';
  }

  function formatSprayMetricValue(metric, value) {
    if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
      return '—';
    }
    var num = Number(value);
    if (metric.id === 'ev' || metric.id === 'launch_angle' || metric.id === 'distance') {
      return num.toFixed(1);
    }
    if (metric.unit === '%') return num.toFixed(1);
    if (metric.id === 'xwoba') {
      var rateText = num.toFixed(3);
      return rateText.startsWith('0.') ? rateText.slice(1) : rateText;
    }
    return String(num);
  }

  function formatSpraySummaryRate(value) {
    if (value === null || value === undefined || value === '' || Number.isNaN(Number(value))) {
      return '—';
    }
    var rateText = Number(value).toFixed(3);
    return rateText.startsWith('0.') ? rateText.slice(1) : rateText;
  }

  function sprayMetricBarWidth(metric, value, types) {
    var num = Number(value);
    if (!num && num !== 0) return 0;
    var max = Number(metric.max) || 100;
    var dataMax = 0;
    types.forEach(function (item) {
      var v = Number(item[metric.id]);
      if (!Number.isNaN(v) && v > dataMax) dataMax = v;
    });
    var scaleMax = Math.max(max, dataMax * 1.05);
    return Math.min(100, (num / scaleMax) * 100);
  }

  function buildSprayChartHtml(panel) {
    var types = panel.types || [];
    var metrics = panel.metrics || [];
    var summary = panel.summary || {};
    if (!summary.total && !types.length) {
      return '<p class="player-splits-empty">No batted-ball data available.</p>';
    }

    var summaryItems = [
      { label: 'Batted Balls', value: summary.total },
      { label: 'Avg EV', value: summary.avg_ev !== null && summary.avg_ev !== undefined ? summary.avg_ev + ' mph' : null },
      { label: 'Avg LA', value: summary.avg_launch_angle !== null && summary.avg_launch_angle !== undefined ? summary.avg_launch_angle + '°' : null },
      { label: 'Avg Dist', value: summary.avg_distance !== null && summary.avg_distance !== undefined ? summary.avg_distance + ' ft' : null },
      { label: 'xwOBA', value: summary.avg_xwoba !== null && summary.avg_xwoba !== undefined ? formatSpraySummaryRate(summary.avg_xwoba) : null },
      { label: 'Hard Hit%', value: summary.hard_hit_pct !== null && summary.hard_hit_pct !== undefined ? summary.hard_hit_pct + '%' : null },
      { label: 'Barrel%', value: summary.barrel_pct !== null && summary.barrel_pct !== undefined ? summary.barrel_pct + '%' : null },
      { label: 'BABIP', value: summary.babip !== null && summary.babip !== undefined ? formatSpraySummaryRate(summary.babip) : null }
    ];

    var summaryHtml = summaryItems.map(function (item) {
      var value = item.value === null || item.value === undefined ? '—' : String(item.value);
      return (
        '<div class="spray-chart-stat">' +
          '<span class="spray-chart-stat__value">' + escapeHtml(value) + '</span>' +
          '<span class="spray-chart-stat__label">' + escapeHtml(item.label) + '</span>' +
        '</div>'
      );
    }).join('');

    var donutHtml = '';
    var typeLegendHtml = '';
    if (types.length) {
      var donutStyle = 'background:' + buildUsageDonutGradient(types, function (item, index) {
        return bbTypeColor(item.bb_type, index);
      });
      typeLegendHtml = types.map(function (item, index) {
        var usage = Number(item.usage);
        var usageText = Number.isNaN(usage) ? '—' : usage.toFixed(1) + '%';
        return (
          '<li class="pitch-mix-legend__item">' +
            '<span class="pitch-mix-legend__swatch" style="background:' + bbTypeColor(item.bb_type, index) + '"></span>' +
            '<span class="pitch-mix-legend__label">' + escapeHtml(item.label) + '</span>' +
            '<span class="pitch-mix-legend__value">' + escapeHtml(usageText) + '</span>' +
          '</li>'
        );
      }).join('');
      donutHtml =
        '<div class="pitch-mix-donut-wrap">' +
          '<div class="pitch-mix-donut" style="' + donutStyle + '" role="img" aria-label="Batted ball type breakdown">' +
            '<div class="pitch-mix-donut__hole"></div>' +
          '</div>' +
          '<p class="pitch-mix-donut__caption">' + escapeHtml(panel.season_year || 'Season') + ' Batted Ball Types</p>' +
        '</div>';
    }

    var metricsHtml = metrics.length && types.length ? metrics.map(function (metric) {
      var barsHtml = types.map(function (item, index) {
        var value = item[metric.id];
        var display = formatSprayMetricValue(metric, value);
        var width = sprayMetricBarWidth(metric, value, types);
        var suffix = '';
        if (display !== '—') {
          if (metric.unit === '%') suffix = '%';
          else if (metric.unit) suffix = ' ' + metric.unit;
        }
        return (
          '<div class="pitch-mix-bar-row">' +
            '<span class="pitch-mix-bar-row__label" title="' + escapeHtml(item.label) + '">' +
              escapeHtml(item.label) +
            '</span>' +
            '<div class="pitch-mix-bar-row__track" aria-hidden="true">' +
              '<span class="pitch-mix-bar-row__fill" style="width:' + width.toFixed(1) + '%;background:' +
              bbTypeColor(item.bb_type, index) + '"></span>' +
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
    }).join('') : '';

    return (
      '<div class="spray-chart">' +
        (types.length ?
          '<div class="pitch-mix__top">' +
            donutHtml +
            '<ul class="pitch-mix-legend">' + typeLegendHtml + '</ul>' +
          '</div>' : '') +
        '<div class="spray-chart__summary">' + summaryHtml + '</div>' +
        (metricsHtml ? '<div class="pitch-mix__metrics">' + metricsHtml + '</div>' : '') +
      '</div>'
    );
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

  function buildPanelInnerHtml(panel) {
    if (panel.panel_kind === 'toggle_stat_bars') {
      var statDefaultView = panel.default_view || (panel.views[0] && panel.views[0].id);
      var statViews = panel.views || [];
      var statToggleHtml = statViews.length > 1
        ? buildToggleHtml(panel.id, statViews, statDefaultView)
        : '';
      var statViewsHtml = statViews.map(function (view) {
        return (
          '<div class="player-panel-view" data-panel="' + escapeHtml(panel.id) +
          '" data-view="' + escapeHtml(view.id) + '"' +
          (view.id === statDefaultView ? '' : ' hidden') + '>' +
          buildStatBarsHtml(view) +
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

    if (panel.panel_kind === 'pitch_mix') {
      return '<div class="player-panel-body">' + buildPitchMixHtml(panel) + '</div>';
    }

    if (panel.panel_kind === 'spray_chart') {
      return '<div class="player-panel-body">' + buildSprayChartHtml(panel) + '</div>';
    }

    if (panel.panel_kind === 'percentile_ranks') {
      return buildPercentileRankingsHtml(panel);
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
        var panel = btn.closest('.player-stats-panel');
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

  function panelClassFor(panel) {
    var panelClass = 'game-detail-section game-detail-panel player-stats-panel';
    if (panel.panel_kind === 'percentile_ranks') {
      panelClass += ' player-stats-panel--percentile';
    }
    if (panel.panel_kind === 'toggle_stat_bars') {
      panelClass += ' team-stats-panel';
    }
    return panelClass;
  }

  var PANEL_ORDER = ['player_stats', visualPanelId, 'percentile_ranks', 'splits'];
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
    initPercentileYearSelects();
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

    upsertPanel({ id: visualPanelId, label: visualPanelLabel, panel_kind: 'loading' });
    upsertPanel({ id: 'percentile_ranks', label: 'Percentile Rankings', panel_kind: 'loading' });
    upsertPanel({ id: 'splits', label: 'Splits', panel_kind: 'loading' });

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

  function loadStagedPanels() {
    fetchPlayerStats('/stats/visual')
      .then(function (payload) {
        fulfillStagedPanel(visualPanelId, payload.stat_panel);
      })
      .catch(function () {
        fulfillStagedPanel(visualPanelId, null);
      });

    fetchPlayerStats('/stats/percentiles')
      .then(function (payload) {
        fulfillStagedPanel('percentile_ranks', payload.stat_panel);
      })
      .catch(function () {
        fulfillStagedPanel('percentile_ranks', null);
      });

    fetchPlayerStats('/stats/splits')
      .then(function (payload) {
        fulfillStagedPanel('splits', payload.stat_panel);
      })
      .catch(function () {
        fulfillStagedPanel('splits', null);
      });
  }

  function renderSummary(statsTable) {
    var html = buildSeasonCareerTableHtml(statsTable);
    if (!html) return false;
    summaryEl.innerHTML = html;
    return true;
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

  function loadSummary() {
    summaryEl.hidden = false;
    summaryEl.innerHTML = buildPanelLoadingHtml();

    fetchPlayerStats('/stats/summary')
      .then(function (payload) {
        if (payload.stats_table && renderSummary(payload.stats_table)) {
          summaryEl.hidden = false;
          return;
        }
        showSummaryUnavailable();
      })
      .catch(function () {
        showSummaryUnavailable();
      });
  }

  function showCoreStats(payload) {
    var hasPanels = payload.stat_panels && payload.stat_panels.length;

    if (!hasPanels) {
      showError();
      return;
    }

    loadingEl.hidden = true;
    if (errorEl) errorEl.hidden = true;

    initCorePanels(payload.stat_panels);
    finishLoading();
    loadSummary();
    loadStagedPanels();
  }

  fetchPlayerStats('/stats')
    .then(showCoreStats)
    .catch(showError);
})();

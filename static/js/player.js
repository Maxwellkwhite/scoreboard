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
      var panelClass = 'game-detail-section game-detail-panel player-stats-panel';
      if (panel.panel_kind === 'percentile_ranks') {
        panelClass += ' player-stats-panel--percentile';
      }
      return (
        '<section class="' + panelClass + '"' +
        ' data-panel="' + escapeHtml(panel.id) + '"' +
        (index === 0 ? '' : ' hidden') + '>' +
        buildPanelInnerHtml(panel) +
        '</section>'
      );
    }).join('');

    tabsEl.hidden = false;
    initPanelToggles(panelsEl);
    initPercentileYearSelects();

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

    function scrollToPanel(panelId) {
      var panel = panelsEl.querySelector('.player-stats-panel[data-panel="' + panelId + '"]');
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

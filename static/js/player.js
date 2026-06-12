(function () {
  var section = document.getElementById('player-stats-section');
  if (!section) return;

  var playerId = section.getAttribute('data-player-id');
  var loadingEl = document.getElementById('player-stats-loading');
  var errorEl = document.getElementById('player-stats-error');
  var tableWrap = document.getElementById('player-stats-table-wrap');

  if (!playerId || !loadingEl || !tableWrap) return;

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function renderTable(statsTable) {
    var columns = statsTable.columns || [];
    if (!columns.length) return false;

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

    tableWrap.innerHTML =
      '<table class="player-stats-table">' +
        '<thead><tr>' + headerCells + '</tr></thead>' +
        '<tbody>' +
          '<tr class="player-stats-table__season">' + seasonCells + '</tr>' +
          '<tr class="player-stats-table__career">' + careerCells + '</tr>' +
        '</tbody>' +
      '</table>';

    return true;
  }

  function finishLoading() {
    section.setAttribute('aria-busy', 'false');
  }

  function showError() {
    loadingEl.hidden = true;
    tableWrap.hidden = true;
    if (errorEl) errorEl.hidden = false;
    finishLoading();
  }

  function showTable() {
    loadingEl.hidden = true;
    if (errorEl) errorEl.hidden = true;
    tableWrap.hidden = false;
    finishLoading();
  }

  fetch('/api/mlb/player/' + encodeURIComponent(playerId) + '/stats')
    .then(function (response) {
      if (!response.ok) throw new Error('Stats unavailable');
      return response.json();
    })
    .then(function (payload) {
      if (!renderTable(payload.stats_table)) throw new Error('Stats unavailable');
      showTable();
    })
    .catch(function () {
      showError();
    });
})();

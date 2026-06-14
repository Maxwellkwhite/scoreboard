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

  function escapeHtml(value) {
    if (value == null || value === '') return '';
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function playerLink(id, name, className) {
    className = className || 'player-link';
    if (!name) return '';
    if (!id) return escapeHtml(name);
    return '<a href="/player/' + encodeURIComponent(id) + '" class="' + className + '">' +
      escapeHtml(name) + '</a>';
  }

  function teamLink(id, label, className) {
    className = className || 'team-link';
    if (!label) return '';
    if (!id) return escapeHtml(label);
    return '<a href="/team/' + encodeURIComponent(id) + '" class="' + className + '">' +
      escapeHtml(label) + '</a>';
  }

  function playerNameVariants(name) {
    var variants = [];
    function add(value) {
      var text = String(value || '').trim();
      if (!text || variants.indexOf(text) !== -1) return;
      variants.push(text);
    }
    add(name);
    variants.slice().forEach(function (source) {
      if (source.indexOf('.') !== -1) {
        add(source.split('.').pop().trim());
      }
      var parts = source.split(/\s+/);
      if (parts.length >= 2) {
        add(parts[parts.length - 1]);
      }
    });
    return variants;
  }

  function playerLinkEntries(playerMap, linkEntries) {
    if (linkEntries && linkEntries.length) {
      return linkEntries.slice().sort(function (a, b) {
        return b.name.length - a.name.length;
      });
    }
    if (!playerMap) return [];
    var entries = [];
    Object.keys(playerMap).forEach(function (id) {
      playerNameVariants(playerMap[id]).forEach(function (name) {
        entries.push({ id: id, name: name });
      });
    });
    entries.sort(function (a, b) {
      return b.name.length - a.name.length;
    });
    return entries;
  }

  function foldForMatch(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  }

  function linkifyPlayerNames(text, playerMap, linkEntries) {
    if (!text) return '';
    var entries = playerLinkEntries(playerMap, linkEntries);
    if (!entries.length) return escapeHtml(text);

    var entryByFolded = {};
    entries.forEach(function (entry) {
      var folded = foldForMatch(entry.name);
      if (!entryByFolded[folded] || entry.name.length > entryByFolded[folded].name.length) {
        entryByFolded[folded] = entry;
      }
    });

    return String(text).split(/(\W+)/).map(function (part) {
      if (!part || !part.trim() || !/\w/.test(part)) {
        return escapeHtml(part);
      }
      var match = entryByFolded[foldForMatch(part)];
      if (match) {
        return playerLink(match.id, part);
      }
      return escapeHtml(part);
    }).join('');
  }

  function setPlayerNameHtml(el, name, id, playerMap) {
    if (!el) return;
    if (!name) {
      el.hidden = true;
      el.innerHTML = '';
      return;
    }
    el.hidden = false;
    if (id) {
      el.innerHTML = playerLink(id, name);
      return;
    }
    if (playerMap) {
      el.innerHTML = linkifyPlayerNames(name, playerMap);
      return;
    }
    el.textContent = name;
  }

  function scoringPlayStyle(play, awayTeam, homeTeam) {
    if (!play.scoring || !play.scoring_side) return '';
    var team = play.scoring_side === 'home' ? homeTeam : awayTeam;
    var color = linescoreTeamColor(team) || '#1a2332';
    return ' style="--scoring-team-color:' + color + ';"';
  }

  function scoringPlayTeamBadge(team) {
    if (!team) {
      return '<span class="play-feed-team play-feed-team--empty" aria-hidden="true"></span>';
    }
    var color = linescoreTeamColor(team) || '#1a2332';
    var logo = team.logo
      ? '<img class="play-feed-team__logo" src="' + team.logo + '" alt="" width="20" height="20" loading="lazy">'
      : '<span class="play-feed-team__logo play-feed-team__logo--placeholder">' + (team.abbr || '') + '</span>';
    return '<span class="play-feed-team" style="--team-color:' + color + ';">' +
      logo +
      '<span class="play-feed-team__abbr">' + teamLink(team.id, team.abbr || '') + '</span>' +
      '</span>';
  }

  function scoringPlaySummaryHtml(play, awayTeam, homeTeam, playerMap, linkEntries) {
    var team = play.scoring_side === 'home'
      ? homeTeam
      : (play.scoring_side === 'away' ? awayTeam : null);
    var score = '';
    if (play.away_score !== null && play.away_score !== undefined &&
        play.home_score !== null && play.home_score !== undefined) {
      score = '<span class="play-feed-score">' + play.away_score + '-' + play.home_score + '</span>';
    }
    var period = play.period
      ? '<span class="play-feed-period">' + play.period + '</span>'
      : '<span class="play-feed-period"></span>';
    return '<li class="play-feed-item play-feed-item--scoring-summary">' +
      scoringPlayTeamBadge(team) +
      period +
      '<span class="play-feed-text">' + linkifyPlayerNames(play.text, playerMap, linkEntries) + '</span>' +
      score +
      '</li>';
  }

  function playFeedItemHtml(play, compact, awayTeam, homeTeam, highlightScoring, playerMap, linkEntries) {
    var score = '';
    if (play.away_score !== null && play.away_score !== undefined &&
        play.home_score !== null && play.home_score !== undefined) {
      score = '<span class="play-feed-score">' + play.away_score + '-' + play.home_score + '</span>';
    }
    var useHighlight = highlightScoring !== false && play.scoring;
    var scoringClass = useHighlight ? ' play-feed-item--scoring' : '';
    var itemClass = 'play-feed-item' + (compact ? ' play-feed-item--compact' : '') + scoringClass;
    var itemStyle = useHighlight ? scoringPlayStyle(play, awayTeam, homeTeam) : '';
    if (compact) {
      return '<li class="' + itemClass + '"' + itemStyle + '>' +
        '<span class="play-feed-text">' + linkifyPlayerNames(play.text, playerMap, linkEntries) + '</span>' +
        score +
        '</li>';
    }
    var period = play.period
      ? '<span class="play-feed-period">' + play.period + '</span>'
      : '<span></span>';
    return '<li class="' + itemClass + '"' + itemStyle + '>' +
      period +
      '<span class="play-feed-text">' + linkifyPlayerNames(play.text, playerMap, linkEntries) + '</span>' +
      score +
      '</li>';
  }

  function renderPlayList(containerId, plays, scoringOnly, awayTeam, homeTeam, highlightScoring, playerMap, linkEntries) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var isScoringList = containerId === 'game-scoring-plays';
    var section = isScoringList ? document.getElementById('game-scoring-plays-section') : null;

    var items = (plays || []).filter(function (play) {
      return !scoringOnly || play.scoring;
    });

    if (!items.length) {
      if (section) section.hidden = true;
      container.innerHTML = isScoringList
        ? ''
        : '<li class="play-feed-empty">No plays yet.</li>';
      return;
    }

    if (section) section.hidden = false;
    container.innerHTML = items.map(function (play) {
      if (isScoringList) {
        return scoringPlaySummaryHtml(play, awayTeam, homeTeam, playerMap, linkEntries);
      }
      return playFeedItemHtml(play, false, awayTeam, homeTeam, highlightScoring, playerMap, linkEntries);
    }).join('');
  }

  function renderPlaysByInning(playsByInning, awayTeam, homeTeam, playerMap, linkEntries) {
    var mount = document.getElementById('game-recent-plays-mount');
    if (!mount) return;

    if (!playsByInning || !playsByInning.length) {
      mount.innerHTML = '<p class="play-feed-empty">No plays yet.</p>';
      return;
    }

    var openInnings = {};
    mount.querySelectorAll('.play-inning-collapse[open]').forEach(function (el) {
      var key = el.getAttribute('data-inning-key');
      if (key) openInnings[key] = true;
    });
    var hasOpenState = Object.keys(openInnings).length > 0;

    mount.innerHTML = playsByInning.map(function (group, index) {
      var inningKey = group.inning || String(index);
      var isOpen = hasOpenState ? Boolean(openInnings[inningKey]) : index === 0;
      var playsHtml = (group.plays || []).map(function (play) {
        return playFeedItemHtml(play, true, awayTeam, homeTeam, true, playerMap, linkEntries);
      }).join('');
      return '<details class="play-inning-collapse" data-inning-key="' + inningKey + '"' +
        (isOpen ? ' open' : '') + '>' +
        '<summary class="play-inning-heading">' + group.inning + '</summary>' +
        '<div class="play-inning-body"><ul class="play-feed">' + playsHtml + '</ul></div>' +
        '</details>';
    }).join('');
  }

  function renderRecentPlaysPanel(live, statusState, awayTeam, homeTeam) {
    var tab = document.getElementById('game-recent-plays-tab');
    var heading = document.getElementById('game-recent-plays-heading');
    var allPlaysHeading = document.getElementById('game-all-plays-heading');
    var isFinal = statusState === 'post';
    var hasAllPlays = Boolean(
      (isFinal && live.plays_by_inning && live.plays_by_inning.length) ||
      (live.recent_plays && live.recent_plays.length)
    );

    if (tab) tab.textContent = 'Plays';
    if (heading) heading.textContent = 'Plays';
    if (allPlaysHeading) {
      allPlaysHeading.hidden = !hasAllPlays;
      allPlaysHeading.textContent = isFinal ? 'Play-by-Play' : 'Recent';
    }

    var playerMap = live.player_map || null;
    var linkEntries = live.player_link_entries || null;

    if (isFinal && live.plays_by_inning) {
      renderPlaysByInning(live.plays_by_inning, awayTeam, homeTeam, playerMap, linkEntries);
      return;
    }

    var mount = document.getElementById('game-recent-plays-mount');
    if (!mount) return;
    mount.innerHTML = '<ul class="play-feed" id="game-recent-plays"></ul>';
    renderPlayList('game-recent-plays', live.recent_plays, false, awayTeam, homeTeam, true, playerMap, linkEntries);
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

  var PITCHING_DECISION_ROLES = [
    ['win', 'Win'],
    ['loss', 'Loss'],
    ['save', 'Save']
  ];

  function pitchingDecisionRecord(role, record) {
    if (!record) return '';
    if (role !== 'save') return record;
    var n = parseInt(record, 10);
    if (isNaN(n)) return record + ' Save';
    var mod100 = n % 100;
    var suffix = 'th';
    if (mod100 < 11 || mod100 > 13) {
      suffix = { 1: 'st', 2: 'nd', 3: 'rd' }[n % 10] || 'th';
    }
    return n + suffix + ' Save';
  }

  function pitchingDecisionTeamColor(pitcher, awayTeam, homeTeam) {
    var team = pitcher.side === 'home' ? homeTeam : awayTeam;
    return linescoreTeamColor(team) || '#1a2332';
  }

  function pitchingDecisionStatsLine(pitcher) {
    return lineupStat(pitcher.ip) + ' IP · ' +
      lineupStat(pitcher.hits) + ' H · ' +
      lineupStat(pitcher.er) + ' ER · ' +
      lineupStat(pitcher.bb) + ' BB · ' +
      lineupStat(pitcher.k) + ' K · ' +
      lineupStat(pitcher.season_era) + ' ERA';
  }

  function renderPitchingDecisionCard(role, label, pitcher, awayTeam, homeTeam) {
    if (!pitcher) return '';

    var teamColor = pitchingDecisionTeamColor(pitcher, awayTeam, homeTeam);
    var teamHtml = pitcher.team_abbr
      ? '<span class="pitching-decision__team">' + pitcher.team_abbr + '</span>'
      : '';
    var recordText = pitchingDecisionRecord(role, pitcher.record);
    var recordHtml = recordText
      ? '<span class="pitching-decision__record"> · ' + recordText + '</span>'
      : '';

    return '<article class="pitching-decision pitching-decision--' + role + '" style="--pitching-team-color:' + teamColor + ';">' +
      '<p class="pitching-decision__label-line">' +
      '<span class="pitching-decision__label">' + label + '</span>' +
      '</p>' +
      '<p class="pitching-decision__player-line">' +
      '<span class="pitching-decision__name">' + playerLink(pitcher.id, pitcher.name) + '</span>' +
      teamHtml +
      recordHtml +
      '</p>' +
      '<p class="pitching-decision__stats">' + pitchingDecisionStatsLine(pitcher) + '</p>' +
      '</article>';
  }

  function renderPitchingDecisions(decisions, awayTeam, homeTeam) {
    var section = document.getElementById('game-pitching-decisions');
    if (!section) return;

    if (!decisions || (!decisions.win && !decisions.loss && !decisions.save)) {
      section.hidden = true;
      section.innerHTML = '';
      return;
    }

    var cards = PITCHING_DECISION_ROLES.map(function (entry) {
      return renderPitchingDecisionCard(entry[0], entry[1], decisions[entry[0]], awayTeam, homeTeam);
    }).join('');

    section.hidden = false;
    section.innerHTML =
      '<div class="pitching-decisions__grid" id="game-pitching-decisions-grid">' +
      cards +
      '</div>';
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
      teamStatsLogo(awayTeam) + '<span class="team-stats__abbr">' + teamLink(awayTeam && awayTeam.id, awayAbbr) + '</span></div>' +
      '<div class="team-stats__team team-stats__team--home">' +
      teamStatsLogo(homeTeam) + '<span class="team-stats__abbr">' + teamLink(homeTeam && homeTeam.id, homeAbbr) + '</span></div>' +
      '</div>' +
      '<div class="team-stats__rows">' + rows + '</div>';
  }

  function lineupTeamLogo(team) {
    if (!team) return '';
    if (team.logo) {
      return '<img class="lineup-team__logo" src="' + team.logo + '" alt="" width="28" height="28" loading="lazy">';
    }
    return '<span class="lineup-team__logo-fallback">' + (team.abbr || '') + '</span>';
  }

  function lineupStat(value) {
    return value != null && value !== '' ? value : '—';
  }

  function renderLineupBattingTable(batters) {
    if (!batters || !batters.length) return '';

    var rows = batters.map(function (batter) {
      var subClass = batter.starter ? '' : ' lineup-table__row--sub';
      var posHtml = batter.position
        ? ' <span class="lineup-table__pos">' + batter.position + '</span>'
        : '';
      return '<tr class="lineup-table__row' + subClass + '">' +
        '<th scope="row" class="lineup-table__player">' + playerLink(batter.id, batter.name) + posHtml + '</th>' +
        '<td class="lineup-stat--game">' + lineupStat(batter.ab) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(batter.hits) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(batter.runs) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(batter.rbi) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(batter.hr) + '</td>' +
        '<td class="lineup-table__group--season lineup-stat--season">' + lineupStat(batter.season_avg) + '</td>' +
        '<td class="lineup-stat--season">' + lineupStat(batter.season_obp) + '</td>' +
        '<td class="lineup-stat--season">' + lineupStat(batter.season_slg) + '</td>' +
        '</tr>';
    }).join('');

    return '<h4 class="lineup-section-title">Batting</h4>' +
      '<div class="lineup-table-wrap"><table class="lineup-table lineup-table--batting">' +
      '<colgroup>' +
      '<col class="lineup-col lineup-col--player">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--season">' +
      '<col class="lineup-col lineup-stat--season">' +
      '<col class="lineup-col lineup-stat--season">' +
      '</colgroup>' +
      '<thead><tr>' +
      '<th scope="col" class="lineup-table__player-col">Player</th>' +
      '<th scope="col" colspan="5" class="lineup-table__group lineup-stat--game">Game</th>' +
      '<th scope="col" colspan="3" class="lineup-table__group lineup-table__group--season lineup-stat--season">Season</th>' +
      '</tr><tr class="lineup-table__subhead">' +
      '<th scope="col"></th>' +
      '<th scope="col" class="lineup-stat--game">AB</th><th scope="col" class="lineup-stat--game">H</th>' +
      '<th scope="col" class="lineup-stat--game">R</th>' +
      '<th scope="col" class="lineup-stat--game">RBI</th><th scope="col" class="lineup-stat--game">HR</th>' +
      '<th scope="col" class="lineup-table__group--season lineup-stat--season">AVG</th>' +
      '<th scope="col" class="lineup-stat--season">OBP</th><th scope="col" class="lineup-stat--season">SLG</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function renderLineupPitchingTable(pitchers) {
    if (!pitchers || !pitchers.length) return '';

    var rows = pitchers.map(function (pitcher) {
      return '<tr class="lineup-table__row">' +
        '<th scope="row" class="lineup-table__player">' + playerLink(pitcher.id, pitcher.name) + '</th>' +
        '<td class="lineup-stat--game">' + lineupStat(pitcher.ip) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(pitcher.hits) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(pitcher.er) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(pitcher.bb) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(pitcher.k) + '</td>' +
        '<td class="lineup-table__group--season lineup-stat--season">' + lineupStat(pitcher.season_era) + '</td>' +
        '<td class="lineup-stat--game">' + lineupStat(pitcher.decision) + '</td>' +
        '</tr>';
    }).join('');

    return '<h4 class="lineup-section-title">Pitching</h4>' +
      '<div class="lineup-table-wrap"><table class="lineup-table lineup-table--pitching">' +
      '<colgroup>' +
      '<col class="lineup-col lineup-col--player">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--game">' +
      '<col class="lineup-col lineup-stat--season">' +
      '<col class="lineup-col lineup-stat--game">' +
      '</colgroup>' +
      '<thead><tr>' +
      '<th scope="col" class="lineup-table__player-col">Player</th>' +
      '<th scope="col" colspan="5" class="lineup-table__group lineup-stat--game">Game</th>' +
      '<th scope="col" class="lineup-table__group lineup-table__group--season lineup-stat--season">Season</th>' +
      '<th scope="col" class="lineup-stat--game"></th>' +
      '</tr><tr class="lineup-table__subhead">' +
      '<th scope="col"></th>' +
      '<th scope="col" class="lineup-stat--game">IP</th><th scope="col" class="lineup-stat--game">H</th>' +
      '<th scope="col" class="lineup-stat--game">ER</th>' +
      '<th scope="col" class="lineup-stat--game">BB</th><th scope="col" class="lineup-stat--game">K</th>' +
      '<th scope="col" class="lineup-table__group--season lineup-stat--season">ERA</th>' +
      '<th scope="col" class="lineup-stat--game">Dec</th>' +
      '</tr></thead><tbody>' + rows + '</tbody></table></div>';
  }

  function renderLineupTeamHtml(side, team, lineupTeam) {
    if (!lineupTeam) return '';

    return '<div class="lineup-team lineup-team--' + side + '">' +
      '<header class="lineup-team__head">' + lineupTeamLogo(team) +
      '<span class="lineup-team__abbr">' + teamLink(team && team.id, lineupTeam.abbr || (team && team.abbr) || '') + '</span></header>' +
      renderLineupBattingTable(lineupTeam.batters) +
      renderLineupPitchingTable(lineupTeam.pitchers) +
      '</div>';
  }

  function renderLineups(lineups, awayTeam, homeTeam) {
    var board = document.getElementById('game-lineup-board');
    if (!board) return;

    if (!lineups || (!lineups.away && !lineups.home)) {
      board.innerHTML = '<p class="play-feed-empty">No lineup yet.</p>';
      return;
    }

    var awayColor = linescoreTeamColor(awayTeam) || '#1a2332';
    var homeColor = linescoreTeamColor(homeTeam) || '#1a2332';
    board.style.setProperty('--away-team-color', awayColor);
    board.style.setProperty('--home-team-color', homeColor);
    board.innerHTML =
      renderLineupTeamHtml('away', awayTeam, lineups.away) +
      renderLineupTeamHtml('home', homeTeam, lineups.home);
  }

  function formatDueUpStats(batter) {
    var line = batter.line || '0-0';
    var runs = batter.runs != null ? batter.runs : '0';
    var rbi = batter.rbi != null ? batter.rbi : '0';
    return line + ', ' + runs + ' R, ' + rbi + ' RBI';
  }

  function renderSituation(live, statusState, playerMap, linkEntries) {
    var section = document.getElementById('game-situation-section');
    if (!live || !live.situation || statusState !== 'in') {
      if (section) section.hidden = true;
      return;
    }

    if (section) section.hidden = false;
    var situation = live.situation;
    playerMap = playerMap || live.player_map || null;
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
          nameEl.innerHTML = playerLink(batter.id, batter.name) ||
            linkifyPlayerNames(batter.name, playerMap, linkEntries);

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
      { base: '1st', occupiedKey: 'on_first', runnerKey: 'first_runner', runnerIdKey: 'first_runner_id', runnerId: 'game-runner-first' },
      { base: '2nd', occupiedKey: 'on_second', runnerKey: 'second_runner', runnerIdKey: 'second_runner_id', runnerId: 'game-runner-second' },
      { base: '3rd', occupiedKey: 'on_third', runnerKey: 'third_runner', runnerIdKey: 'third_runner_id', runnerId: 'game-runner-third' }
    ];

    baseConfig.forEach(function (item) {
      var el = document.querySelector('.base--' + item.base);
      if (el) el.classList.toggle('base--occupied', !!situation[item.occupiedKey]);

      var runnerEl = document.getElementById(item.runnerId);
      setPlayerNameHtml(
        runnerEl,
        situation[item.runnerKey],
        situation[item.runnerIdKey],
        playerMap
      );
    });

    var pitcherEl = document.getElementById('game-pitcher-name');
    if (pitcherEl) {
      var pitcherName = situation.pitcher_name;
      pitcherEl.hidden = !pitcherName;
      setPlayerNameHtml(
        pitcherEl.querySelector('.bases-player-name'),
        pitcherName,
        situation.pitcher_id,
        playerMap
      );
    }

    var batterEl = document.getElementById('game-batter-name');
    if (batterEl) {
      var batterName = situation.batter_name;
      batterEl.hidden = !batterName;
      setPlayerNameHtml(
        batterEl.querySelector('.bases-player-name'),
        batterName,
        situation.batter_id,
        playerMap
      );
    }
  }

  function battingTeam(game) {
    var side = game.batting_side;
    if (!side || !game[side]) return null;
    return game[side];
  }

  function battingTeamColor(game) {
    var team = battingTeam(game);
    if (!team) return null;
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
    var team = battingTeam(game);
    var borderColor = battingTeamColor(game);

    if (matchup) {
      matchup.className = 'game-card game-card--' + game.status_state + ' game-detail-hero';
    }

    if (game.status_state === 'in' && team && matchup) {
      if (window.teamBattingPill) {
        window.teamBattingPill.apply(matchup, team, borderColor);
      } else if (borderColor) {
        matchup.style.setProperty('--batting-team-color', borderColor);
      }
      if (pill) pill.classList.add('status-pill--batting-team');
    } else {
      if (matchup) {
        if (window.teamBattingPill) {
          window.teamBattingPill.clear(matchup);
        } else {
          matchup.style.removeProperty('--batting-team-color');
          matchup.style.removeProperty('--batting-team-bg');
          matchup.style.removeProperty('--batting-team-text');
        }
      }
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
    var team = battingTeam(game);
    var borderColor = battingTeamColor(game);

    if (game.status_state === 'in' && team) {
      if (window.teamBattingPill) {
        window.teamBattingPill.apply(card, team, borderColor);
      } else if (borderColor) {
        card.style.setProperty('--batting-team-color', borderColor);
      }
    } else if (window.teamBattingPill) {
      window.teamBattingPill.clear(card);
    } else {
      card.style.removeProperty('--batting-team-color');
      card.style.removeProperty('--batting-team-bg');
      card.style.removeProperty('--batting-team-text');
    }

    card.className = 'game-mini-card game-mini-card--' + game.status_state +
      (isLink ? ' game-mini-card--link' : ' game-mini-card--active');

    var pill = card.querySelector('.status-pill');
    if (pill) {
      pill.className = 'status-pill status-pill--' + game.status_state;
      if (game.status_state === 'in' && team) {
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

      var hasWinner = Boolean(game.away && game.away.winner) ||
        Boolean(game.home && game.home.winner);
      row.classList.toggle('game-card-team--winner', !!team.winner);
      row.classList.toggle(
        'game-card-team--loser',
        game.status_state === 'post' && hasWinner && !team.winner
      );
      row.style.setProperty(
        '--team-color',
        team.win_color || team.color || '#1a2332'
      );

      var scoreEl = document.getElementById('game-' + side + '-score');
      if (scoreEl) {
        scoreEl.textContent = team.score != null ? team.score : '0';
        var scoreWrap = scoreEl.closest('.game-detail-matchup-score');
        if (scoreWrap) {
          scoreWrap.style.setProperty(
            '--team-color',
            team.win_color || team.color || '#1a2332'
          );
        }
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

    if (awayWin == null && homeWin != null) {
      awayWin = Math.round((100 - homeWin) * 10) / 10;
    } else if (homeWin == null && awayWin != null) {
      homeWin = Math.round((100 - awayWin) * 10) / 10;
    }

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
      if (awayFill && awayWin != null) {
        awayFill.style.width = awayWin + '%';
      }
    } else if (winBar) {
      winBar.hidden = true;
    }

    var live = game.live || {};
    if (live.linescore) renderLinescore(live.linescore, game.away, game.home);
    renderPitchingDecisions(live.pitching_decisions, game.away, game.home);
    renderTeamBox(live.team_box, game.away, game.home);
    renderLineups(live.lineups, game.away, game.home);
    var playerMap = live.player_map || null;
    var linkEntries = live.player_link_entries || null;
    renderSituation(live, game.status_state, playerMap, linkEntries);
    renderPlayList('game-scoring-plays', live.scoring_plays, false, game.away, game.home, false, playerMap, linkEntries);
    renderRecentPlaysPanel(live, game.status_state, game.away, game.home);

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

  function applyLineupStatMode(mode) {
    var section = document.getElementById('game-lineup-section');
    var toggle = document.getElementById('lineup-stat-toggle');
    if (!section) return;

    section.classList.toggle('lineup-show-season', mode === 'season');
    if (!toggle) return;

    toggle.querySelectorAll('.lineup-stat-toggle__btn').forEach(function (btn) {
      var isActive = btn.getAttribute('data-lineup-stat') === mode;
      btn.classList.toggle('is-active', isActive);
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }

  function initLineupStatToggle() {
    var toggle = document.getElementById('lineup-stat-toggle');
    if (!toggle) return;

    toggle.addEventListener('click', function (event) {
      var btn = event.target.closest('.lineup-stat-toggle__btn');
      if (!btn) return;
      applyLineupStatMode(btn.getAttribute('data-lineup-stat'));
    });
  }

  initDetailTabs();
  initLineupStatToggle();
  refreshGame();
})();

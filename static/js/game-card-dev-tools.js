(function () {
  var root = document.getElementById('game-card-dev-tools');
  if (!root) return;

  var card = document.getElementById('game-card-dev-sample');
  var pill = document.getElementById('game-card-dev-pill');
  var situationEl = document.getElementById('game-card-dev-situation');
  var countEl = document.getElementById('game-card-dev-count');
  var awayTeam = document.getElementById('game-card-dev-away');
  var homeTeam = document.getElementById('game-card-dev-home');
  var awayScoreEl = document.getElementById('game-card-dev-away-score');
  var homeScoreEl = document.getElementById('game-card-dev-home-score');

  if (!card || !pill || !situationEl || !countEl || !awayTeam || !homeTeam || !awayScoreEl || !homeScoreEl) {
    return;
  }

  var WIN_COLOR_MIN_DISTANCE = 72;

  function normalizeHex(value) {
    if (!value) return null;
    var color = String(value).trim();
    if (!color) return null;
    return color.charAt(0) === '#' ? color : '#' + color;
  }

  function colorDistance(left, right) {
    var leftRgb = [
      parseInt(left.slice(1, 3), 16),
      parseInt(left.slice(3, 5), 16),
      parseInt(left.slice(5, 7), 16)
    ];
    var rightRgb = [
      parseInt(right.slice(1, 3), 16),
      parseInt(right.slice(3, 5), 16),
      parseInt(right.slice(5, 7), 16)
    ];
    return Math.sqrt(
      leftRgb.reduce(function (sum, channel, index) {
        var delta = channel - rightRgb[index];
        return sum + delta * delta;
      }, 0)
    );
  }

  function colorsTooSimilar(left, right) {
    if (!left || !right) return false;
    if (left.toLowerCase() === right.toLowerCase()) return true;
    return colorDistance(left, right) < WIN_COLOR_MIN_DISTANCE;
  }

  function teamColorCandidates(team) {
    var candidates = [];
    [team.color, team.alternate_color].forEach(function (value) {
      var normalized = normalizeHex(value);
      if (normalized && candidates.indexOf(normalized) === -1) {
        candidates.push(normalized);
      }
    });
    return candidates;
  }

  function resolveWinColors(away, home) {
    var awayCandidates = teamColorCandidates(away);
    var homeCandidates = teamColorCandidates(home);
    var awayWin = normalizeHex(away.color) || awayCandidates[0] || '#56b6c6';
    var homeWin = normalizeHex(home.color) || homeCandidates[0] || '#22a06b';

    if (!colorsTooSimilar(awayWin, homeWin)) {
      away.win_color = awayWin;
      home.win_color = homeWin;
      return;
    }

    var homeAlternate = normalizeHex(home.alternate_color);
    if (homeAlternate && !colorsTooSimilar(awayWin, homeAlternate)) {
      home.win_color = homeAlternate;
      away.win_color = awayWin;
      return;
    }

    var awayAlternate = normalizeHex(away.alternate_color);
    if (awayAlternate && !colorsTooSimilar(awayAlternate, homeWin)) {
      away.win_color = awayAlternate;
      home.win_color = homeWin;
      return;
    }

    var bestDistance = -1;
    (awayCandidates.length ? awayCandidates : [awayWin]).forEach(function (awayOption) {
      (homeCandidates.length ? homeCandidates : [homeWin]).forEach(function (homeOption) {
        var distance = colorDistance(awayOption, homeOption);
        if (distance > bestDistance) {
          bestDistance = distance;
          awayWin = awayOption;
          homeWin = homeOption;
        }
      });
    });

    away.win_color = awayWin;
    home.win_color = homeWin;
  }

  var teams = {
    away: {
      color: '#002D72',
      alternate_color: '#FF5910',
      abbr: 'NYM',
      short_name: 'Mets',
      logo: 'https://a.espncdn.com/i/teamlogos/mlb/500/21.png'
    },
    home: {
      color: '#E81828',
      alternate_color: '#002D72',
      abbr: 'PHI',
      short_name: 'Phillies',
      logo: 'https://a.espncdn.com/i/teamlogos/mlb/500/22.png'
    }
  };

  resolveWinColors(teams.away, teams.home);

  var state = {
    status: 'in',
    battingSide: 'away',
    awayScore: 4,
    homeScore: 3
  };

  function flashScoreOnCard(side) {
    if (!window.gameCardScoreFlash) {
      return;
    }
    window.gameCardScoreFlash.flash(card, side, teams[side]);
  }

  function battingBorderColor(side) {
    var team = teams[side];
    return team.win_color || team.color || null;
  }

  function applyTeamColors() {
    awayTeam.style.setProperty(
      '--team-color',
      teams.away.win_color || teams.away.color || '#1a2332'
    );
    homeTeam.style.setProperty(
      '--team-color',
      teams.home.win_color || teams.home.color || '#1a2332'
    );
  }

  function applyBattingTheme() {
    var battingTeam = teams[state.battingSide];
    var borderColor = battingBorderColor(state.battingSide);
    if (state.status === 'in' && battingTeam) {
      if (window.teamBattingPill) {
        window.teamBattingPill.apply(card, battingTeam, borderColor);
      } else if (borderColor) {
        card.style.setProperty('--batting-team-color', borderColor);
        card.style.setProperty('--batting-team-bg', battingTeam.color || borderColor);
        if (battingTeam.alternate_color) {
          card.style.setProperty('--batting-team-text', battingTeam.alternate_color);
        }
      }
      pill.classList.add('status-pill--batting-team');
    } else {
      if (window.teamBattingPill) {
        window.teamBattingPill.clear(card);
      } else {
        card.style.removeProperty('--batting-team-color');
        card.style.removeProperty('--batting-team-bg');
        card.style.removeProperty('--batting-team-text');
      }
      pill.classList.remove('status-pill--batting-team');
    }
  }

  function renderScores() {
    if (state.status === 'pre') {
      awayScoreEl.textContent = '—';
      homeScoreEl.textContent = '—';
      return;
    }
    awayScoreEl.textContent = String(state.awayScore);
    homeScoreEl.textContent = String(state.homeScore);
  }

  function clearWinnerClasses() {
    awayTeam.classList.remove('game-card-team--winner', 'game-card-team--loser');
    homeTeam.classList.remove('game-card-team--winner', 'game-card-team--loser');
  }

  function applyWinnerClasses() {
    clearWinnerClasses();
    if (state.status !== 'post') return;
    if (state.awayScore > state.homeScore) {
      awayTeam.classList.add('game-card-team--winner');
      homeTeam.classList.add('game-card-team--loser');
    } else if (state.homeScore > state.awayScore) {
      homeTeam.classList.add('game-card-team--winner');
      awayTeam.classList.add('game-card-team--loser');
    }
  }

  function setCardState(status, options) {
    options = options || {};
    state.status = status;
    if (options.battingSide) {
      state.battingSide = options.battingSide;
    }

    var packActive = window.gameCardPackOpen && window.gameCardPackOpen.isActive(card);
    var gameEndActive = window.gameCardGameEnd && window.gameCardGameEnd.isActive(card);
    card.className = 'game-card game-card--' + status + ' game-card--link game-card-dev-tools__sample';
    if (packActive) {
      card.classList.add('game-card--pack-open');
    }
    if (gameEndActive) {
      card.classList.add('game-card--game-end');
    }
    pill.className = 'status-pill status-pill--' + status;

    if (status === 'pre') {
      pill.textContent = '7:10 PM';
      situationEl.hidden = true;
    } else if (status === 'in') {
      pill.textContent = state.battingSide === 'away' ? 'Top 7th' : 'Bot 7th';
      situationEl.hidden = false;
      countEl.textContent = '1-2, 1 out';
    } else {
      pill.textContent = 'Final';
      situationEl.hidden = true;
    }

    clearWinnerClasses();
    renderScores();
    applyWinnerClasses();
    applyTeamColors();
    applyBattingTheme();
  }

  function bumpScore(side, delta) {
    if (state.status === 'pre') {
      setCardState('in', { battingSide: side });
    }
    if (side === 'away') {
      state.awayScore = Math.max(0, state.awayScore + delta);
      renderScores();
      if (delta > 0) {
        flashScoreOnCard('away');
      }
      applyWinnerClasses();
      return;
    }
    state.homeScore = Math.max(0, state.homeScore + delta);
    renderScores();
    if (delta > 0) {
      flashScoreOnCard('home');
    }
    applyWinnerClasses();
  }

  function playGameStartAnimation() {
    state.awayScore = 0;
    state.homeScore = 0;
    state.battingSide = 'away';
    setCardState('pre');
    window.setTimeout(function () {
      setCardState('in', { battingSide: 'away' });
      if (window.gameCardPackOpen) {
        window.gameCardPackOpen.play(card, {
          away: {
            abbr: teams.away.abbr,
            short_name: teams.away.short_name,
            name: 'New York Mets',
            color: teams.away.color,
            logo: teams.away.logo,
            record: '24-31',
            probable_pitcher: {
              name: 'K. Senga',
              throws: 'Right',
              stats: { W: '3', L: '2', ERA: '2.45' }
            }
          },
          home: {
            abbr: teams.home.abbr,
            short_name: teams.home.short_name,
            name: 'Philadelphia Phillies',
            color: teams.home.color,
            logo: teams.home.logo,
            record: '32-23',
            probable_pitcher: {
              name: 'Z. Wheeler',
              throws: 'Right',
              headshot: 'https://a.espncdn.com/i/headshots/mlb/players/full/30957.png',
              stats: { W: '6', L: '1', ERA: '1.89' }
            }
          }
        });
      }
    }, 500);
  }

  function playGameEndAnimation() {
    state.awayScore = 5;
    state.homeScore = 3;
    setCardState('post');
    if (window.gameCardGameEnd) {
      window.gameCardGameEnd.play(card, {
        away: {
          abbr: teams.away.abbr,
          short_name: teams.away.short_name,
          color: teams.away.color,
          alternate_color: teams.away.alternate_color,
          logo: teams.away.logo,
          score: state.awayScore,
          winner: true
        },
        home: {
          abbr: teams.home.abbr,
          short_name: teams.home.short_name,
          color: teams.home.color,
          alternate_color: teams.home.alternate_color,
          logo: teams.home.logo,
          score: state.homeScore
        }
      });
    }
  }

  function handleAction(action) {
    switch (action) {
      case 'pulse-away':
        flashScoreOnCard('away');
        break;
      case 'pulse-home':
        flashScoreOnCard('home');
        break;
      case 'pulse-card':
        flashScoreOnCard(state.battingSide);
        break;
      case 'pulse-full':
        bumpScore('away', 1);
        break;
      case 'game-start':
        playGameStartAnimation();
        break;
      case 'game-end':
        playGameEndAnimation();
        break;
      case 'state-pre':
        setCardState('pre');
        break;
      case 'state-live-away':
        setCardState('in', { battingSide: 'away' });
        break;
      case 'state-live-home':
        setCardState('in', { battingSide: 'home' });
        break;
      case 'state-final':
        setCardState('post');
        break;
      case 'away-dec':
        bumpScore('away', -1);
        break;
      case 'away-inc':
        bumpScore('away', 1);
        break;
      case 'home-dec':
        bumpScore('home', -1);
        break;
      case 'home-inc':
        bumpScore('home', 1);
        break;
      default:
        break;
    }
  }

  root.addEventListener('click', function (event) {
    var button = event.target.closest('[data-dev-action]');
    if (!button) return;
    event.preventDefault();
    handleAction(button.getAttribute('data-dev-action'));
  });

  setCardState('in', { battingSide: 'away' });
})();

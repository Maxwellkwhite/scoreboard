(function () {
  var root = document.getElementById('game-card-dev-tools');
  if (!root) return;

  var card = document.getElementById('game-card-dev-sample');
  var pill = document.getElementById('game-card-dev-pill');
  var countEl = document.getElementById('game-card-dev-count');
  var awayTeam = document.getElementById('game-card-dev-away');
  var homeTeam = document.getElementById('game-card-dev-home');
  var awayScoreEl = document.getElementById('game-card-dev-away-score');
  var homeScoreEl = document.getElementById('game-card-dev-home-score');

  if (!card || !pill || !countEl || !awayTeam || !homeTeam || !awayScoreEl || !homeScoreEl) {
    return;
  }

  var teams = {
    away: { color: '#002D72', abbr: 'NYM' },
    home: { color: '#E81828', abbr: 'PHI' }
  };

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

  function applyBattingTheme() {
    var battingTeam = teams[state.battingSide];
    if (state.status === 'in' && battingTeam) {
      card.style.setProperty('--batting-team-color', battingTeam.color);
      pill.classList.add('status-pill--batting-team');
    } else {
      card.style.removeProperty('--batting-team-color');
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
    card.className = 'game-card game-card--' + status + ' game-card-dev-tools__sample';
    if (packActive) {
      card.classList.add('game-card--pack-open');
    }
    pill.className = 'status-pill status-pill--' + status;

    if (status === 'pre') {
      pill.textContent = '7:10 PM';
      countEl.hidden = true;
    } else if (status === 'in') {
      pill.textContent = state.battingSide === 'away' ? 'Top 7th' : 'Bot 7th';
      countEl.hidden = false;
      countEl.textContent = '1-2, 1 out';
    } else {
      pill.textContent = 'Final';
      countEl.hidden = true;
    }

    clearWinnerClasses();
    renderScores();
    applyWinnerClasses();
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
            short_name: 'Mets',
            name: 'New York Mets',
            color: teams.away.color,
            logo: 'https://a.espncdn.com/i/teamlogos/mlb/500/21.png',
            record: '24-31',
            probable_pitcher: { name: 'S. Senga', throws: 'Right' }
          },
          home: {
            abbr: teams.home.abbr,
            short_name: 'Phillies',
            name: 'Philadelphia Phillies',
            color: teams.home.color,
            logo: 'https://a.espncdn.com/i/teamlogos/mlb/500/22.png',
            record: '32-23',
            probable_pitcher: { name: 'Z. Wheeler', throws: 'Right' }
          }
        });
      }
    }, 500);
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

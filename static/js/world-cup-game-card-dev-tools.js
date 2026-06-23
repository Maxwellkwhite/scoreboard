(function () {
  var root = document.getElementById('wc-game-card-dev-tools');
  if (!root) return;

  var card = document.getElementById('wc-game-card-dev-sample');
  var pill = document.getElementById('wc-game-card-dev-pill');
  var awayTeam = document.getElementById('wc-game-card-dev-away');
  var homeTeam = document.getElementById('wc-game-card-dev-home');
  var awayScoreEl = document.getElementById('wc-game-card-dev-away-score');
  var homeScoreEl = document.getElementById('wc-game-card-dev-home-score');

  if (!card || !pill || !awayTeam || !homeTeam || !awayScoreEl || !homeScoreEl) {
    return;
  }

  var teams = {
    away: {
      color: '#74acdf',
      alternate_color: '#ffffff',
      abbr: 'ARG',
      short_name: 'Argentina',
      name: 'Argentina',
      logo: 'https://a.espncdn.com/i/teamlogos/countries/500/arg.png',
      win_color: '#74acdf'
    },
    home: {
      color: '#21304e',
      alternate_color: '#ed2939',
      abbr: 'FRA',
      short_name: 'France',
      name: 'France',
      logo: 'https://a.espncdn.com/i/teamlogos/countries/500/fra.png',
      win_color: '#21304e'
    }
  };

  var state = {
    status: 'in',
    awayScore: 2,
    homeScore: 1
  };

  function flashScoreOnCard(side) {
    if (!window.gameCardScoreFlash) return;
    window.gameCardScoreFlash.flash(card, side, teams[side]);
  }

  function applyTeamColors() {
    awayTeam.style.setProperty('--team-color', teams.away.win_color || teams.away.color || '#1a2332');
    homeTeam.style.setProperty('--team-color', teams.home.win_color || teams.home.color || '#1a2332');
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

  function setCardState(status) {
    state.status = status;

    var matchStartActive = window.gameCardMatchStart && window.gameCardMatchStart.isActive(card);
    var redCardActive = window.gameCardRedCard && window.gameCardRedCard.isActive(card);
    var yellowCardActive = window.gameCardYellowCard && window.gameCardYellowCard.isActive(card);
    var gameEndActive = window.gameCardGameEnd && window.gameCardGameEnd.isActive(card);
    card.className = 'game-card game-card--' + status + ' game-card--link game-card-dev-tools__sample';
    if (matchStartActive) card.classList.add('game-card--match-start');
    if (redCardActive) card.classList.add('game-card--red-card');
    if (yellowCardActive) card.classList.add('game-card--yellow-card');
    if (gameEndActive) card.classList.add('game-card--game-end');

    pill.className = 'status-pill status-pill--' + status;
    if (status === 'pre') {
      pill.textContent = '3:00 PM';
    } else if (status === 'in') {
      pill.textContent = "65'";
    } else {
      pill.textContent = 'FT';
    }

    clearWinnerClasses();
    renderScores();
    applyWinnerClasses();
    applyTeamColors();
  }

  function bumpScore(side, delta) {
    if (state.status === 'pre') {
      setCardState('in');
    }
    if (side === 'away') {
      state.awayScore = Math.max(0, state.awayScore + delta);
      renderScores();
      if (delta > 0) flashScoreOnCard('away');
    } else {
      state.homeScore = Math.max(0, state.homeScore + delta);
      renderScores();
      if (delta > 0) flashScoreOnCard('home');
    }
    applyWinnerClasses();
  }

  function playGameStartAnimation() {
    state.awayScore = 0;
    state.homeScore = 0;
    setCardState('pre');
    window.setTimeout(function () {
      setCardState('in');
      if (window.gameCardMatchStart) {
        window.gameCardMatchStart.play(card, {
          away: teams.away,
          home: teams.home
        });
      }
    }, 500);
  }

  function playRedCardAnimation() {
    if (state.status === 'pre') {
      setCardState('in');
    }
    if (window.gameCardRedCard) {
      window.gameCardRedCard.play(card, {
        playerName: 'K. Mbappé',
        teamAbbr: teams.home.abbr,
        side: 'home'
      });
    }
  }

  function playYellowCardAnimation() {
    if (state.status === 'pre') {
      setCardState('in');
    }
    if (window.gameCardYellowCard) {
      window.gameCardYellowCard.play(card, {
        playerName: 'L. Messi',
        teamAbbr: teams.away.abbr,
        side: 'away'
      });
    }
  }

  function playGameEndAnimation() {
    state.awayScore = 3;
    state.homeScore = 1;
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
      case 'pulse-full':
        bumpScore('away', 1);
        break;
      case 'game-start':
        playGameStartAnimation();
        break;
      case 'red-card':
        playRedCardAnimation();
        break;
      case 'yellow-card':
        playYellowCardAnimation();
        break;
      case 'game-end':
        playGameEndAnimation();
        break;
      case 'state-pre':
        setCardState('pre');
        break;
      case 'state-live':
        setCardState('in');
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

  setCardState('in');
})();

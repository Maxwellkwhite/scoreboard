(function () {
  'use strict';

  var overlay = document.getElementById('desktop-only-overlay');
  if (!overlay || !overlay.classList.contains('mobile-preview')) return;

  var wcTeams = {
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

  var mlbTeams = {
    away: {
      color: '#002d72',
      alternate_color: '#ff5910',
      abbr: 'NYM',
      short_name: 'Mets',
      name: 'Mets',
      logo: 'https://a.espncdn.com/i/teamlogos/mlb/500/21.png',
      win_color: '#ff5910'
    },
    home: {
      color: '#e81828',
      alternate_color: '#003278',
      abbr: 'PHI',
      short_name: 'Phillies',
      name: 'Phillies',
      logo: 'https://a.espncdn.com/i/teamlogos/mlb/500/22.png',
      win_color: '#e81828'
    }
  };

  function initAccordions() {
    overlay.querySelectorAll('[data-preview-card]').forEach(function (card) {
      var toggle = card.querySelector('.mobile-preview__card-toggle');
      var body = card.querySelector('.mobile-preview__card-body');
      if (!toggle || !body) return;

      toggle.addEventListener('click', function () {
        var isOpen = card.classList.toggle('mobile-preview__card--open');
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        body.hidden = !isOpen;
      });
    });
  }

  function initSportToggle() {
    var buttons = overlay.querySelectorAll('[data-preview-sport]');
    var panels = overlay.querySelectorAll('[data-preview-sport-panel]');
    if (!buttons.length) return;

    buttons.forEach(function (button) {
      button.addEventListener('click', function () {
        var sport = button.getAttribute('data-preview-sport');
        buttons.forEach(function (btn) {
          var active = btn === button;
          btn.classList.toggle('is-active', active);
          btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        panels.forEach(function (panel) {
          panel.hidden = panel.getAttribute('data-preview-sport-panel') !== sport;
        });
      });
    });
  }

  function createWcDemo() {
    var card = document.getElementById('mobile-preview-wc-card');
    var pill = document.getElementById('mobile-preview-wc-pill');
    var awayTeam = document.getElementById('mobile-preview-wc-away');
    var homeTeam = document.getElementById('mobile-preview-wc-home');
    var awayScoreEl = document.getElementById('mobile-preview-wc-away-score');
    var homeScoreEl = document.getElementById('mobile-preview-wc-home-score');
    var root = overlay.querySelector('[data-demo-root="wc"]');

    if (!card || !pill || !awayTeam || !homeTeam || !awayScoreEl || !homeScoreEl || !root) {
      return null;
    }

    var state = { status: 'in', awayScore: 2, homeScore: 1 };

    function flashScore(side) {
      if (window.gameCardScoreFlash) {
        window.gameCardScoreFlash.flash(card, side, wcTeams[side]);
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

    function clearWinners() {
      awayTeam.classList.remove('game-card-team--winner', 'game-card-team--loser');
      homeTeam.classList.remove('game-card-team--winner', 'game-card-team--loser');
    }

    function setCardState(status) {
      state.status = status;
      var matchStartActive = window.gameCardMatchStart && window.gameCardMatchStart.isActive(card);
      var redCardActive = window.gameCardRedCard && window.gameCardRedCard.isActive(card);
      var yellowCardActive = window.gameCardYellowCard && window.gameCardYellowCard.isActive(card);
      var gameEndActive = window.gameCardGameEnd && window.gameCardGameEnd.isActive(card);

      card.className =
        'game-card game-card--' + status + ' game-card-dev-tools__sample mobile-preview__game-card';
      if (matchStartActive) card.classList.add('game-card--match-start');
      if (redCardActive) card.classList.add('game-card--red-card');
      if (yellowCardActive) card.classList.add('game-card--yellow-card');
      if (gameEndActive) card.classList.add('game-card--game-end');

      pill.className = 'status-pill status-pill--' + status;
      pill.textContent = status === 'pre' ? '3:00 PM' : (status === 'in' ? "65'" : 'FT');

      clearWinners();
      renderScores();
      if (status === 'post' && state.awayScore !== state.homeScore) {
        if (state.awayScore > state.homeScore) {
          awayTeam.classList.add('game-card-team--winner');
          homeTeam.classList.add('game-card-team--loser');
        } else {
          homeTeam.classList.add('game-card-team--winner');
          awayTeam.classList.add('game-card-team--loser');
        }
      }
    }

    function bumpScore(side, delta) {
      if (state.status === 'pre') setCardState('in');
      if (side === 'away') {
        state.awayScore = Math.max(0, state.awayScore + delta);
        renderScores();
        if (delta > 0) flashScore('away');
      } else {
        state.homeScore = Math.max(0, state.homeScore + delta);
        renderScores();
        if (delta > 0) flashScore('home');
      }
    }

    function handleAction(action) {
      switch (action) {
        case 'pulse-away':
          flashScore('away');
          break;
        case 'pulse-home':
          flashScore('home');
          break;
        case 'pulse-full':
          bumpScore('away', 1);
          break;
        case 'game-start':
          state.awayScore = 0;
          state.homeScore = 0;
          setCardState('pre');
          window.setTimeout(function () {
            setCardState('in');
            if (window.gameCardMatchStart) {
              window.gameCardMatchStart.play(card, { away: wcTeams.away, home: wcTeams.home });
            }
          }, 400);
          break;
        case 'red-card':
          if (state.status === 'pre') setCardState('in');
          if (window.gameCardRedCard) {
            window.gameCardRedCard.play(card, {
              playerName: 'K. Mbappé',
              teamAbbr: wcTeams.home.abbr,
              side: 'home'
            });
          }
          break;
        case 'yellow-card':
          if (state.status === 'pre') setCardState('in');
          if (window.gameCardYellowCard) {
            window.gameCardYellowCard.play(card, {
              playerName: 'L. Messi',
              teamAbbr: wcTeams.away.abbr,
              side: 'away'
            });
          }
          break;
        case 'game-end':
          state.awayScore = 3;
          state.homeScore = 1;
          setCardState('post');
          if (window.gameCardGameEnd) {
            window.gameCardGameEnd.play(card, {
              away: {
                abbr: wcTeams.away.abbr,
                short_name: wcTeams.away.short_name,
                color: wcTeams.away.color,
                alternate_color: wcTeams.away.alternate_color,
                logo: wcTeams.away.logo,
                score: state.awayScore,
                winner: true
              },
              home: {
                abbr: wcTeams.home.abbr,
                short_name: wcTeams.home.short_name,
                color: wcTeams.home.color,
                alternate_color: wcTeams.home.alternate_color,
                logo: wcTeams.home.logo,
                score: state.homeScore
              }
            });
          }
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
    return handleAction;
  }

  function createMlbDemo() {
    var card = document.getElementById('mobile-preview-mlb-card');
    var pill = document.getElementById('mobile-preview-mlb-pill');
    var awayTeam = document.getElementById('mobile-preview-mlb-away');
    var homeTeam = document.getElementById('mobile-preview-mlb-home');
    var awayScoreEl = document.getElementById('mobile-preview-mlb-away-score');
    var homeScoreEl = document.getElementById('mobile-preview-mlb-home-score');
    var root = overlay.querySelector('[data-demo-root="mlb"]');

    if (!card || !pill || !awayTeam || !homeTeam || !awayScoreEl || !homeScoreEl || !root) {
      return null;
    }

    var state = { status: 'in', awayScore: 4, homeScore: 3, batting: 'away' };

    function flashScore(side) {
      if (window.gameCardScoreFlash) {
        window.gameCardScoreFlash.flash(card, side, mlbTeams[side]);
      }
    }

    function applyBattingStyle() {
      var battingTeam = state.batting === 'away' ? mlbTeams.away : mlbTeams.home;
      card.style.setProperty('--batting-team-color', battingTeam.win_color || battingTeam.color);
      card.style.setProperty('--batting-team-bg', battingTeam.color);
      card.style.setProperty('--batting-team-text', battingTeam.alternate_color || '#ffffff');
      pill.classList.toggle('status-pill--batting-team', state.status === 'in');
    }

    function setCardState(status, batting) {
      state.status = status;
      if (batting) state.batting = batting;

      var packActive = window.gameCardPackOpen && window.gameCardPackOpen.isActive(card);
      var strikeoutActive = window.gameCardStrikeout && window.gameCardStrikeout.isActive(card);
      var walkActive = window.gameCardWalk && window.gameCardWalk.isActive(card);
      var gameEndActive = window.gameCardGameEnd && window.gameCardGameEnd.isActive(card);

      card.className =
        'game-card game-card--' + status + ' game-card-dev-tools__sample mobile-preview__game-card';
      if (packActive) card.classList.add('game-card--pack-open');
      if (strikeoutActive) card.classList.add('game-card--strikeout');
      if (walkActive) card.classList.add('game-card--walk');
      if (gameEndActive) card.classList.add('game-card--game-end');

      pill.className = 'status-pill status-pill--' + status;
      if (status === 'pre') {
        pill.textContent = '7:10 PM';
      } else if (status === 'in') {
        pill.textContent = state.batting === 'away' ? 'Top 7th' : 'Bot 7th';
      } else {
        pill.textContent = 'Final';
      }

      if (status === 'pre') {
        awayScoreEl.textContent = '—';
        homeScoreEl.textContent = '—';
      } else {
        awayScoreEl.textContent = String(state.awayScore);
        homeScoreEl.textContent = String(state.homeScore);
      }

      applyBattingStyle();
    }

    function handleAction(action) {
      switch (action) {
        case 'pulse-full':
          if (state.status === 'pre') setCardState('in', 'away');
          state.awayScore += 1;
          awayScoreEl.textContent = String(state.awayScore);
          flashScore('away');
          break;
        case 'game-start':
          state.awayScore = 0;
          state.homeScore = 0;
          setCardState('pre', 'away');
          window.setTimeout(function () {
            setCardState('in', 'away');
            if (window.gameCardPackOpen) {
              window.gameCardPackOpen.play(card, { away: mlbTeams.away, home: mlbTeams.home });
            }
          }, 400);
          break;
        case 'strikeout-swinging':
          if (state.status === 'pre') setCardState('in', 'away');
          if (window.gameCardStrikeout) {
            window.gameCardStrikeout.play(card, {
              playerName: 'P. Alonso',
              teamAbbr: mlbTeams.away.abbr,
              side: 'away',
              looking: false
            });
          }
          break;
        case 'walk':
          if (state.status === 'pre') setCardState('in', 'home');
          if (window.gameCardWalk) {
            window.gameCardWalk.play(card, {
              playerName: 'B. Harper',
              teamAbbr: mlbTeams.home.abbr,
              side: 'home'
            });
          }
          break;
        case 'game-end':
          state.awayScore = 5;
          state.homeScore = 3;
          setCardState('post', 'away');
          if (window.gameCardGameEnd) {
            window.gameCardGameEnd.play(card, {
              away: {
                abbr: mlbTeams.away.abbr,
                short_name: mlbTeams.away.short_name,
                color: mlbTeams.away.color,
                alternate_color: mlbTeams.away.alternate_color,
                logo: mlbTeams.away.logo,
                score: state.awayScore,
                winner: true
              },
              home: {
                abbr: mlbTeams.home.abbr,
                short_name: mlbTeams.home.short_name,
                color: mlbTeams.home.color,
                alternate_color: mlbTeams.home.alternate_color,
                logo: mlbTeams.home.logo,
                score: state.homeScore
              }
            });
          }
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

    setCardState('in', 'away');
    return handleAction;
  }

  initAccordions();
  initSportToggle();
  createWcDemo();
  createMlbDemo();
})();

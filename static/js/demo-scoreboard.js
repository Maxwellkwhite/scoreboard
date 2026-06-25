(function () {
  'use strict';

  var WIN_COLOR_MIN_DISTANCE = 72;

  var configEl = document.getElementById('demo-game-configs');
  var GAME_CONFIGS = [];
  if (configEl && configEl.textContent) {
    try {
      GAME_CONFIGS = JSON.parse(configEl.textContent);
    } catch (error) {
      GAME_CONFIGS = [];
    }
  }

  var PITCHER_SAMPLES = {
    NYM: { name: 'K. Senga', throws: 'Right', stats: { W: '3', L: '2', ERA: '2.45' } },
    PHI: { name: 'Z. Wheeler', throws: 'Right', stats: { W: '6', L: '1', ERA: '1.89' } },
    NYY: { name: 'G. Cole', throws: 'Right', stats: { W: '5', L: '1', ERA: '2.62' } },
    BOS: { name: 'B. Bello', throws: 'Right', stats: { W: '4', L: '2', ERA: '3.12' } },
    LAD: { name: 'Y. Yamamoto', throws: 'Right', stats: { W: '7', L: '2', ERA: '2.71' } },
    SF: { name: 'L. Webb', throws: 'Right', stats: { W: '4', L: '3', ERA: '3.05' } },
    CHC: { name: 'S. Imanaga', throws: 'Left', stats: { W: '5', L: '1', ERA: '2.88' } },
    STL: { name: 'S. Gray', throws: 'Right', stats: { W: '4', L: '2', ERA: '3.44' } },
    HOU: { name: 'F. Valdez', throws: 'Left', stats: { W: '5', L: '3', ERA: '3.21' } },
    ATL: { name: 'C. Morton', throws: 'Right', stats: { W: '4', L: '2', ERA: '3.55' } },
    SEA: { name: 'L. Castillo', throws: 'Right', stats: { W: '6', L: '2', ERA: '2.98' } },
    TEX: { name: 'N. Eovaldi', throws: 'Right', stats: { W: '5', L: '2', ERA: '2.74' } }
  };

  var PLAYER_SAMPLES = {
    NYM: 'P. Alonso',
    PHI: 'B. Harper',
    NYY: 'A. Judge',
    BOS: 'R. Devers',
    LAD: 'S. Ohtani',
    SF: 'W. Flores',
    CHC: 'K. Tucker',
    STL: 'N. Gorman',
    HOU: 'J. Altuve',
    ATL: 'R. Acuña Jr.',
    SEA: 'C. Raleigh',
    TEX: 'C. Seager'
  };

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
    }
  }

  function delay(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  function randomBetween(min, max) {
    return Math.floor(Math.random() * (max - min + 1)) + min;
  }

  function randomDelay(min, max) {
    return delay(randomBetween(min, max));
  }

  function shuffle(items) {
    var copy = items.slice();
    for (var i = copy.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var temp = copy[i];
      copy[i] = copy[j];
      copy[j] = temp;
    }
    return copy;
  }

  function pickRandomCard(exclude) {
    var pool = cards.filter(function (card) {
      return !exclude || exclude.indexOf(card.index) === -1;
    });
    if (!pool.length) {
      pool = cards.slice();
    }
    return pool[randomBetween(0, pool.length - 1)];
  }

  function initialStateFromConfig(initial) {
    return {
      status: initial.status,
      battingSide: initial.battingSide,
      awayScore: initial.awayScore,
      homeScore: initial.homeScore,
      statusDetail: initial.statusDetail || (initial.battingSide === 'home' ? 'Bot 7th' : 'Top 7th'),
      balls: typeof initial.balls === 'number' ? initial.balls : 0,
      strikes: typeof initial.strikes === 'number' ? initial.strikes : 0,
      outs: typeof initial.outs === 'number' ? initial.outs : 0,
      onFirst: Boolean(initial.onFirst),
      onSecond: Boolean(initial.onSecond),
      onThird: Boolean(initial.onThird)
    };
  }

  function createDemoCard(index, config) {
    var card = document.getElementById('demo-card-' + index);
    var pill = document.getElementById('demo-card-' + index + '-pill');
    var situationEl = document.getElementById('demo-card-' + index + '-situation');
    var countEl = document.getElementById('demo-card-' + index + '-count');
    var awayTeam = document.getElementById('demo-card-' + index + '-away');
    var homeTeam = document.getElementById('demo-card-' + index + '-home');
    var awayScoreEl = document.getElementById('demo-card-' + index + '-away-score');
    var homeScoreEl = document.getElementById('demo-card-' + index + '-home-score');
    var baseFirst = card ? card.querySelector('.game-card-base--1st') : null;
    var baseSecond = card ? card.querySelector('.game-card-base--2nd') : null;
    var baseThird = card ? card.querySelector('.game-card-base--3rd') : null;

    if (!card || !pill || !situationEl || !countEl || !awayTeam || !homeTeam || !awayScoreEl || !homeScoreEl) {
      return null;
    }

    var teams = {
      away: Object.assign({}, config.away),
      home: Object.assign({}, config.home)
    };
    resolveWinColors(teams.away, teams.home);

    var state = initialStateFromConfig(config.initial);

    function formatCount() {
      return state.balls + '-' + state.strikes + ', ' + state.outs + ' out' + (state.outs === 1 ? '' : 's');
    }

    function renderSituation() {
      if (!countEl) return;
      countEl.textContent = formatCount();
      if (baseFirst) {
        baseFirst.classList.toggle('game-card-base--occupied', state.onFirst);
      }
      if (baseSecond) {
        baseSecond.classList.toggle('game-card-base--occupied', state.onSecond);
      }
      if (baseThird) {
        baseThird.classList.toggle('game-card-base--occupied', state.onThird);
      }
    }

    function flashScoreOnCard(side) {
      if (window.gameCardScoreFlash) {
        window.gameCardScoreFlash.flash(card, side, teams[side]);
      }
    }

    function battingBorderColor(side) {
      var team = teams[side];
      return team.win_color || team.color || null;
    }

    function applyTeamColors() {
      awayTeam.style.setProperty('--team-color', teams.away.win_color || teams.away.color || '#1a2332');
      homeTeam.style.setProperty('--team-color', teams.home.win_color || teams.home.color || '#1a2332');
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
        if (state.statusDetail) {
          if (options.battingSide === 'away') {
            state.statusDetail = state.statusDetail.replace(/^Bot/i, 'Top');
          } else {
            state.statusDetail = state.statusDetail.replace(/^Top/i, 'Bot');
          }
        }
      }

      var packActive = window.gameCardPackOpen && window.gameCardPackOpen.isActive(card);
      var strikeoutActive = window.gameCardStrikeout && window.gameCardStrikeout.isActive(card);
      var walkActive = window.gameCardWalk && window.gameCardWalk.isActive(card);
      var gameEndActive = window.gameCardGameEnd && window.gameCardGameEnd.isActive(card);

      card.className = 'game-card game-card--' + status + ' demo-game-card';
      if (packActive) card.classList.add('game-card--pack-open');
      if (strikeoutActive) card.classList.add('game-card--strikeout');
      if (walkActive) card.classList.add('game-card--walk');
      if (gameEndActive) card.classList.add('game-card--game-end');

      pill.className = 'status-pill status-pill--' + status;
      if (status === 'pre') {
        pill.textContent = '7:10 PM';
        situationEl.hidden = true;
      } else if (status === 'in') {
        pill.textContent = state.statusDetail;
        situationEl.hidden = false;
        renderSituation();
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
        if (delta > 0) flashScoreOnCard('away');
      } else {
        state.homeScore = Math.max(0, state.homeScore + delta);
        renderScores();
        if (delta > 0) flashScoreOnCard('home');
      }
      applyWinnerClasses();
    }

    function packOpenPayload() {
      return {
        away: {
          abbr: teams.away.abbr,
          short_name: teams.away.short_name,
          name: teams.away.name,
          color: teams.away.color,
          logo: teams.away.logo,
          record: '24-31',
          probable_pitcher: PITCHER_SAMPLES[teams.away.abbr] || { name: 'TBD' }
        },
        home: {
          abbr: teams.home.abbr,
          short_name: teams.home.short_name,
          name: teams.home.name,
          color: teams.home.color,
          logo: teams.home.logo,
          record: '32-23',
          probable_pitcher: PITCHER_SAMPLES[teams.home.abbr] || { name: 'TBD' }
        }
      };
    }

    function playGameStartAnimation() {
      state.awayScore = 0;
      state.homeScore = 0;
      state.battingSide = 'away';
      state.statusDetail = 'Top 1st';
      state.balls = 0;
      state.strikes = 0;
      state.outs = 0;
      state.onFirst = false;
      state.onSecond = false;
      state.onThird = false;
      setCardState('pre');
      return delay(500).then(function () {
        setCardState('in', { battingSide: 'away' });
        if (window.gameCardPackOpen) {
          window.gameCardPackOpen.play(card, packOpenPayload());
        }
      });
    }

    function playStrikeoutAnimation() {
      if (state.status === 'pre') {
        setCardState('in', { battingSide: state.battingSide });
      }
      var side = state.battingSide;
      var abbr = teams[side].abbr;
      if (window.gameCardStrikeout) {
        window.gameCardStrikeout.play(card, {
          playerName: PLAYER_SAMPLES[abbr] || 'Batter',
          teamAbbr: abbr,
          side: side,
          looking: false
        });
      }
    }

    function playWalkAnimation() {
      if (state.status === 'pre') {
        setCardState('in', { battingSide: state.battingSide });
      }
      var side = state.battingSide;
      var abbr = teams[side].abbr;
      if (window.gameCardWalk) {
        window.gameCardWalk.play(card, {
          playerName: PLAYER_SAMPLES[abbr] || 'Batter',
          teamAbbr: abbr,
          side: side
        });
      }
    }

    function playGameEndAnimation() {
      state.awayScore = state.awayScore + 1;
      state.homeScore = state.homeScore;
      if (state.awayScore <= state.homeScore) {
        state.homeScore += 1;
      }
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
            winner: state.awayScore > state.homeScore
          },
          home: {
            abbr: teams.home.abbr,
            short_name: teams.home.short_name,
            color: teams.home.color,
            alternate_color: teams.home.alternate_color,
            logo: teams.home.logo,
            score: state.homeScore,
            winner: state.homeScore > state.awayScore
          }
        });
      }
    }

    function reset() {
      Object.assign(state, initialStateFromConfig(config.initial));
      if (window.gameCardPackOpen && window.gameCardPackOpen.cancel) {
        window.gameCardPackOpen.cancel(card);
      }
      if (window.gameCardStrikeout && window.gameCardStrikeout.cancel) {
        window.gameCardStrikeout.cancel(card);
      }
      if (window.gameCardWalk && window.gameCardWalk.cancel) {
        window.gameCardWalk.cancel(card);
      }
      if (window.gameCardGameEnd && window.gameCardGameEnd.cancel) {
        window.gameCardGameEnd.cancel(card);
      }
      if (window.gameCardScoreFlash && window.gameCardScoreFlash.cancel) {
        window.gameCardScoreFlash.cancel(card);
      }
      setCardState(state.status, { battingSide: state.battingSide });
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
          bumpScore(state.battingSide, 1);
          break;
        case 'game-start':
          playGameStartAnimation();
          break;
        case 'strikeout-swinging':
          playStrikeoutAnimation();
          break;
        case 'walk':
          playWalkAnimation();
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
        default:
          break;
      }
    }

    reset();

    return {
      index: index,
      label: config.label,
      handleAction: handleAction,
      reset: reset,
      setCardState: setCardState,
      bumpScore: bumpScore,
      playGameStart: playGameStartAnimation,
      playStrikeout: playStrikeoutAnimation,
      playWalk: playWalkAnimation,
      playGameEnd: playGameEndAnimation,
      flashBatting: function () {
        handleAction('pulse-card');
      }
    };
  }

  var cards = GAME_CONFIGS.map(function (config, index) {
    return createDemoCard(index, config);
  }).filter(Boolean);

  var controls = document.getElementById('demo-controls');
  var targetSelect = document.getElementById('demo-target');
  var runFullBtn = document.getElementById('demo-run-full');
  var resetAllBtn = document.getElementById('demo-reset-all');
  var demoRunning = false;

  function setControlsDisabled(disabled) {
    if (runFullBtn) runFullBtn.disabled = disabled;
    controls.querySelectorAll('[data-demo-action]').forEach(function (btn) {
      btn.disabled = disabled;
    });
  }

  function selectedCards() {
    if (!targetSelect) return cards;
    var value = targetSelect.value;
    if (value === 'all') return cards;
    var index = parseInt(value, 10);
    var card = cards[index];
    return card ? [card] : cards;
  }

  function runOnSelected(action) {
    selectedCards().forEach(function (card) {
      card.handleAction(action);
    });
  }

  async function runFullDemo() {
    if (demoRunning || cards.length < 6) return;
    demoRunning = true;
    setControlsDisabled(true);

    cards.forEach(function (card) { card.reset(); });
    await delay(400);

    var packCard = pickRandomCard();
    await packCard.playGameStart();
    await randomDelay(8500, 11000);

    var events = shuffle([
      { type: 'score', side: 'home' },
      { type: 'score', side: 'away' },
      { type: 'score', side: 'home' },
      { type: 'batting' },
      { type: 'batting' },
      { type: 'strikeout' },
      { type: 'walk' },
      { type: 'score', side: 'away' },
      { type: 'batting' },
      { type: 'strikeout' }
    ]);

    var recentCards = [packCard.index];
    for (var i = 0; i < events.length; i++) {
      var evt = events[i];
      var card = pickRandomCard(recentCards.slice(-2));
      recentCards.push(card.index);
      var battingSide = Math.random() > 0.5 ? 'away' : 'home';

      if (evt.type === 'score') {
        card.setCardState('in', { battingSide: evt.side });
        card.bumpScore(evt.side, 1);
      } else if (evt.type === 'batting') {
        card.setCardState('in', { battingSide: battingSide });
        card.flashBatting();
      } else if (evt.type === 'strikeout') {
        card.setCardState('in', { battingSide: battingSide });
        card.playStrikeout();
      } else if (evt.type === 'walk') {
        card.setCardState('in', { battingSide: battingSide });
        card.playWalk();
      }

      await randomDelay(2800, 5500);
    }

    await randomDelay(5000, 8000);

    var endCard = pickRandomCard([packCard.index]);
    await endCard.playGameEnd();
    await randomDelay(10000, 13000);

    demoRunning = false;
    setControlsDisabled(false);
  }

  if (controls) {
    controls.addEventListener('click', function (event) {
      var button = event.target.closest('[data-demo-action]');
      if (!button || demoRunning) return;
      runOnSelected(button.getAttribute('data-demo-action'));
    });
  }

  if (runFullBtn) {
    runFullBtn.addEventListener('click', function () {
      runFullDemo();
    });
  }

  if (resetAllBtn) {
    resetAllBtn.addEventListener('click', function () {
      if (demoRunning) return;
      cards.forEach(function (card) { card.reset(); });
    });
  }
})();

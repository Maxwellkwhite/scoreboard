(function () {
  'use strict';

  var seeded = Object.create(null);
  var seen = Object.create(null);

  function playCard(card, anim) {
    if (!card || !anim || !anim.player_name) {
      return;
    }
    var opts = {
      playerName: anim.player_name,
      side: anim.side,
      teamAbbr: anim.team_abbr
    };
    if (anim.card_type === 'red' && window.gameCardRedCard) {
      window.gameCardRedCard.play(card, opts);
    } else if (anim.card_type === 'yellow' && window.gameCardYellowCard) {
      window.gameCardYellowCard.play(card, opts);
    }
  }

  function applyCardEvents(card, game, key) {
    if (!card || !game || game.sport !== 'world_cup' || game.status_state !== 'in') {
      return;
    }

    var events = game.card_events;
    if (!events || !events.length) {
      return;
    }

    if (!seen[key]) {
      seen[key] = Object.create(null);
    }

    if (!seeded[key]) {
      seeded[key] = true;
      events.forEach(function (event) {
        if (event.event_id) {
          seen[key][event.event_id] = true;
        }
      });
      return;
    }

    events.forEach(function (event) {
      if (!event.event_id || seen[key][event.event_id]) {
        return;
      }
      seen[key][event.event_id] = true;
      playCard(card, event);
    });
  }

  window.gameCardCardEvents = {
    apply: applyCardEvents
  };
})();

(function () {
  "use strict";

  var DEBOUNCE_MS = 250;
  var MIN_QUERY_LENGTH = 2;

  function debounce(fn, wait) {
    var timer;
    return function () {
      var args = arguments;
      var ctx = this;
      clearTimeout(timer);
      timer = setTimeout(function () {
        fn.apply(ctx, args);
      }, wait);
    };
  }

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function initSearch(root) {
    var apiUrl = root.getAttribute("data-search-api");
    var input = root.querySelector(".scoreboard-search__input");
    var resultsEl = root.querySelector(".scoreboard-search__results");
    if (!apiUrl || !input || !resultsEl) {
      return;
    }

    var activeIndex = -1;
    var items = [];
    var requestId = 0;
    var activeController = null;

    function closeResults() {
      resultsEl.hidden = true;
      resultsEl.innerHTML = "";
      input.setAttribute("aria-expanded", "false");
      activeIndex = -1;
      items = [];
    }

    function setActive(index) {
      var options = resultsEl.querySelectorAll(".scoreboard-search__option");
      options.forEach(function (el, i) {
        var isActive = i === index;
        el.classList.toggle("scoreboard-search__option--active", isActive);
        el.setAttribute("aria-selected", isActive ? "true" : "false");
      });
      activeIndex = index;
      if (index >= 0 && options[index]) {
        options[index].scrollIntoView({ block: "nearest" });
      }
    }

    function navigateTo(item) {
      if (!item || !item.href) {
        return;
      }
      window.location.href = item.href;
    }

    function renderResults(data) {
      var teams = (data && data.teams) || [];
      var players = (data && data.players) || [];
      items = [];

      if (!teams.length && !players.length) {
        resultsEl.innerHTML =
          '<div class="scoreboard-search__empty">No results</div>';
        resultsEl.hidden = false;
        input.setAttribute("aria-expanded", "true");
        return;
      }

      var html = "";

      if (teams.length) {
        html += '<div class="scoreboard-search__section">Teams</div>';
        teams.forEach(function (team) {
          var href = "/team/" + encodeURIComponent(team.id);
          items.push({ href: href });
          var logo = team.logo
            ? '<img class="scoreboard-search__logo" src="' +
              escapeHtml(team.logo) +
              '" alt="" loading="lazy">'
            : '<span class="scoreboard-search__logo scoreboard-search__logo--placeholder"></span>';
          html +=
            '<a class="scoreboard-search__option" role="option" href="' +
            escapeHtml(href) +
            '" data-index="' +
            (items.length - 1) +
            '">' +
            logo +
            '<span class="scoreboard-search__option-main">' +
            '<span class="scoreboard-search__option-title">' +
            escapeHtml(team.name) +
            "</span>" +
            '<span class="scoreboard-search__option-meta">' +
            escapeHtml(team.abbr) +
            "</span>" +
            "</span></a>";
        });
      }

      if (players.length) {
        html += '<div class="scoreboard-search__section">Players</div>';
        players.forEach(function (player) {
          var href = "/player/" + encodeURIComponent(player.id);
          items.push({ href: href });
          var color = player.team_color || "#1a2332";
          html +=
            '<a class="scoreboard-search__option" role="option" href="' +
            escapeHtml(href) +
            '" data-index="' +
            (items.length - 1) +
            '">' +
            '<span class="scoreboard-search__team-dot" style="background:' +
            escapeHtml(color) +
            '"></span>' +
            '<span class="scoreboard-search__option-main">' +
            '<span class="scoreboard-search__option-title">' +
            escapeHtml(player.name) +
            "</span>" +
            '<span class="scoreboard-search__option-meta">' +
            escapeHtml(player.position || "") +
            (player.team_abbr ? " · " + escapeHtml(player.team_abbr) : "") +
            "</span>" +
            "</span></a>";
        });
      }

      resultsEl.innerHTML = html;
      resultsEl.hidden = false;
      input.setAttribute("aria-expanded", "true");
      activeIndex = -1;
    }

    function runSearch() {
      var query = input.value.trim();
      if (query.length < MIN_QUERY_LENGTH) {
        if (activeController) {
          activeController.abort();
          activeController = null;
        }
        closeResults();
        return;
      }

      if (activeController) {
        activeController.abort();
      }
      activeController = typeof AbortController !== "undefined" ? new AbortController() : null;
      var signal = activeController ? activeController.signal : undefined;
      var currentRequest = ++requestId;

      fetch(apiUrl + "?q=" + encodeURIComponent(query), signal ? { signal: signal } : undefined)
        .then(function (response) {
          if (!response.ok) {
            throw new Error("search failed");
          }
          return response.json();
        })
        .then(function (data) {
          if (currentRequest !== requestId) {
            return;
          }
          renderResults(data);
        })
        .catch(function (error) {
          if (error && error.name === "AbortError") {
            return;
          }
          if (currentRequest !== requestId) {
            return;
          }
          resultsEl.innerHTML =
            '<div class="scoreboard-search__empty">Search unavailable</div>';
          resultsEl.hidden = false;
        });
    }

    var debouncedSearch = debounce(runSearch, DEBOUNCE_MS);

    input.addEventListener("input", debouncedSearch);

    input.addEventListener("focus", function () {
      if (input.value.trim().length >= MIN_QUERY_LENGTH) {
        runSearch();
      }
    });

    input.addEventListener("keydown", function (event) {
      var options = resultsEl.querySelectorAll(".scoreboard-search__option");
      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (resultsEl.hidden) {
          runSearch();
          return;
        }
        var next = activeIndex + 1;
        if (next >= options.length) {
          next = 0;
        }
        setActive(next);
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (resultsEl.hidden || !options.length) {
          return;
        }
        var prev = activeIndex - 1;
        if (prev < 0) {
          prev = options.length - 1;
        }
        setActive(prev);
      } else if (event.key === "Enter") {
        if (!resultsEl.hidden && activeIndex >= 0 && items[activeIndex]) {
          event.preventDefault();
          navigateTo(items[activeIndex]);
        }
      } else if (event.key === "Escape") {
        closeResults();
      }
    });

    resultsEl.addEventListener("mousemove", function (event) {
      var option = event.target.closest(".scoreboard-search__option");
      if (!option) {
        return;
      }
      var index = Number(option.getAttribute("data-index"));
      if (!Number.isNaN(index)) {
        setActive(index);
      }
    });

    document.addEventListener("click", function (event) {
      if (!root.contains(event.target)) {
        closeResults();
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll("[data-scoreboard-search]").forEach(initSearch);
  });
})();

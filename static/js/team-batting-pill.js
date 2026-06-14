(function () {
  function normalizeColor(value) {
    if (!value) {
      return null;
    }
    var color = String(value).trim();
    return color || null;
  }

  function applyBattingPillTheme(element, team, borderColor) {
    if (!element || !team) {
      return;
    }

    var bg = normalizeColor(team.color) || normalizeColor(borderColor);
    var text = normalizeColor(team.alternate_color);
    var resolvedBorder = normalizeColor(borderColor) || bg;

    if (resolvedBorder) {
      element.style.setProperty('--batting-team-color', resolvedBorder);
    }
    if (bg) {
      element.style.setProperty('--batting-team-bg', bg);
    }
    if (text && (!bg || text.toLowerCase() !== bg.toLowerCase())) {
      element.style.setProperty('--batting-team-text', text);
    } else {
      element.style.removeProperty('--batting-team-text');
    }
  }

  function clearBattingPillTheme(element) {
    if (!element) {
      return;
    }
    element.style.removeProperty('--batting-team-color');
    element.style.removeProperty('--batting-team-bg');
    element.style.removeProperty('--batting-team-text');
  }

  window.teamBattingPill = {
    apply: applyBattingPillTheme,
    clear: clearBattingPillTheme
  };
})();

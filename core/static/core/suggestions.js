// On the Search page, a suggested title that is added to To Watch leaves, and the next spare suggestion of the same
// kind takes its place, so the list stays full and I can keep adding. The spares are in a <template> at the end of
// each list (see _suggestions.html). With no spare left the tile just goes. Search results are not touched: their
// button simply turns into "Remove from To Watch".
document.addEventListener('htmx:afterSettle', function (event) {
  // The To Watch button has just been swapped for its new state, and it says the title is on the list.
  var button = event.target;
  if (!button.matches('.to-watch-action[data-on-list]')) return;
  var tile = button.closest('.suggestions li');
  if (!tile) return;

  var list = tile.parentElement;
  var spares = list.querySelector(':scope > template');
  var next = spares && spares.content.firstElementChild;
  if (next) {
    tile.replaceWith(next);
    htmx.process(next);
  } else {
    tile.remove();
  }

  // A list with nothing left shows no heading either, like one that never had suggestions.
  if (!list.querySelector(':scope > li')) {
    list.previousElementSibling.remove();
    list.remove();
  }
});

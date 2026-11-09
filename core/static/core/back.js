// A "← Back" link (marked data-back) goes back to the page I came from, using the browser's own history.
// The link's address (Search) is for a page opened directly, where there is nothing to go back to:
// no earlier page in this tab, or an earlier page that is not Couchlog (a bookmark, a typed address).
// Without JavaScript the link simply goes to Search.
document.addEventListener('click', function (event) {
  var link = event.target.closest('a[data-back]');
  // A click with Ctrl, Shift... opens the link in a new tab, so leave it alone.
  if (!link || event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;
  if (history.length > 1 && document.referrer.indexOf(location.origin + '/') === 0) {
    event.preventDefault();
    history.back();
  }
});

// A phone can freeze a whole page in memory when I leave it and show that frozen page again on Back, without asking
// Couchlog, whatever the never-cache headers say. It may be out of date by then, so load it again.
window.addEventListener('pageshow', function (event) {
  if (event.persisted) location.reload();
});

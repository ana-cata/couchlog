// When a button or a search gets no answer from Couchlog (the phone lost the Wi-Fi, the PC or Pi is off), or Couchlog
// answers with an error, htmx would do nothing at all. This says so in the line under the header bar instead.
// The line goes again as soon as a request works. TMDB problems are not handled here: Couchlog answers those itself.
(function () {
  function say(text) {
    var line = document.getElementById('problem');
    if (!line) return;
    line.textContent = text;
    line.hidden = false;
  }

  // No answer at all.
  document.addEventListener('htmx:sendError', function () {
    say('Couchlog did not answer. Check the Wi-Fi and try again.');
  });

  // An answer, but an error (for example a crash on the server).
  document.addEventListener('htmx:responseError', function () {
    say('Something went wrong. Try again.');
  });

  document.addEventListener('htmx:afterRequest', function (event) {
    var line = document.getElementById('problem');
    if (line && event.detail.successful) line.hidden = true;
  });
})();

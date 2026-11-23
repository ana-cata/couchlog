// The Share button on a title's page (a link marked data-share, see _share.html). Its address is the title's TMDB page.
// - On a phone or tablet (a touch screen) it opens the phone's own share menu with the title's name and the link.
// - On a computer (a mouse) it copies the link and says "Link copied" beside the button.
// Phones and browsers only allow both on a secure (https) page. Where neither is there, the click is left alone and the
// link opens the TMDB page in a new tab, as it does without JavaScript. Couchlog's server is never asked.
document.addEventListener('click', function (event) {
  var link = event.target.closest('a[data-share]');
  // A click with Ctrl, Shift... opens the link in a new tab, so leave it alone.
  if (!link || event.ctrlKey || event.shiftKey || event.metaKey || event.altKey) return;
  var said = link.parentElement.querySelector('.share-said');
  var touch = window.matchMedia('(pointer: coarse)').matches;

  if (touch && navigator.share) {
    event.preventDefault();
    // Closing the menu without picking anything also ends here: nothing to say.
    navigator.share({ text: link.dataset.shareText, url: link.href }).catch(function () {});
  } else if (navigator.clipboard && navigator.clipboard.writeText) {
    event.preventDefault();
    navigator.clipboard.writeText(link.href).then(
      function () { say(said, 'Link copied'); },
      function () { say(said, 'Could not copy the link'); }
    );
  }
});

// The words beside the button go away again after a few seconds.
function say(said, words) {
  said.textContent = words;
  clearTimeout(said.timer);
  said.timer = setTimeout(function () { said.textContent = ''; }, 3000);
}

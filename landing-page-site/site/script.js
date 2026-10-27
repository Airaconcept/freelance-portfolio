// Mobile menu, form validation (demo: nothing is sent), footer year. No dependencies.
(function () {
  var toggle = document.querySelector('.nav-toggle');
  var menu = document.getElementById('nav-menu');
  toggle.addEventListener('click', function () {
    var open = menu.classList.toggle('open');
    toggle.setAttribute('aria-expanded', String(open));
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  });
  menu.addEventListener('click', function (e) {
    if (e.target.tagName === 'A' && menu.classList.contains('open')) toggle.click();
  });

  document.getElementById('year').textContent = new Date().getFullYear();

  var form = document.getElementById('contact-form');
  var status = form.querySelector('.form-status');
  var EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;

  function setError(input, msg) {
    var p = input.parentElement.querySelector('.error');
    if (p) p.textContent = msg || '';
    input.setAttribute('aria-invalid', msg ? 'true' : 'false');
    return !msg;
  }

  function validate() {
    var name = form.elements.name, email = form.elements.email;
    var ok = setError(name, name.value.trim().length >= 2 ? '' : 'Please enter your name.');
    var v = email.value.trim();
    ok = setError(email, !v ? 'Please enter your email.' : EMAIL.test(v) ? '' : 'Please enter a valid email address.') && ok;
    return ok;
  }

  form.addEventListener('submit', function (e) {
    e.preventDefault();
    status.textContent = '';
    if (!validate()) {
      form.querySelector('[aria-invalid="true"]').focus();
      return;
    }
    // DEMO ONLY: replace this block with fetch() to your form endpoint (see README).
    var data = Object.fromEntries(new FormData(form).entries());
    console.log('demo form data (not sent):', data);
    status.textContent = 'Thanks, ' + data.name.trim().split(' ')[0] + '! (Demo: the form is not connected, nothing was sent.)';
    form.reset();
  });
})();

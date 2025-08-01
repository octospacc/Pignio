const API_BASE = '//' + document.documentElement.dataset.root.split('://').slice(1).join('://') + '/api';

registerHandler('form.Register', (form) => addSlugifyNoticeHandler(form.querySelector('input[name="username"]'), form.querySelector('span.notice'), 'username'));
registerHandler('form.add', addHandler);
registerHandler('div.item', itemHandler);
registerHandler('div.item div.clickable', lightboxHandler);

up.compiler('.notifications.placeholder', target => {
  target.classList.toggle('content');
  up.request('/notifications').then(response => {
    up.render({ target: '.notifications.content', response });
    var count = document.querySelectorAll('nav .notifications > ul.events > li').length;
    if (count > 0) {
      var badge = document.querySelector('nav .uk-badge');
      badge.textContent = count;
      if (document.querySelector('nav .notifications > .load-wrapper > a')) {
        badge.textContent += '+';
      }
      badge.hidden = false;
    }
  });
});

function registerHandler(query, handler) {
  if ('up' in window) {
    up.compiler(query, handler);
  } else {
    document.querySelectorAll(query).forEach(el => handler(el));
  }
}

function addTextInputHandler(input, handler) {
  [/* 'change', */ 'input', 'paste'].forEach(event => input.addEventListener(event, handler));
}

function addSlugifyNoticeHandler(input, notice, subject) {
  addTextInputHandler(input, function(){
    if (input.value) {
      fetch(API_BASE + '/slugify?text=' + encodeURIComponent(input.value))
      .then(res => res.text())
      .then(text => {
        if (text !== input.value) {
          notice.innerHTML = `The ${subject} will be normalized to <code>${text}</code>.`;
        } else {
          notice.textContent = '';
        }
      });
    } else {
      notice.textContent = '';
    }
  });
}

function addHandler(form) {
  var link = form.querySelector('input[name="link"]');
  var pasteLink = form.querySelector('button.paste-link');
  var checkLink = form.querySelector('input.from-link');
  // var checkProxatore = form.querySelector('input.with-proxatore');
  var langs = form.querySelector('select[name="langs"]');
  var image = form.querySelector('img.image');
  var video = form.querySelector('video.video');
  var upload = form.querySelector('input[name="file"]');

  form.querySelector('button.langs-reset').addEventListener('click', () => (langs.selectedIndex = -1));

  pasteLink.addEventListener('click', () => navigator.clipboard.readText().then(text => {
    link.value = text;
    linkHandler();
  }));

  upload.addEventListener('change', function(ev) {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
      var uri = e.target.result;
      image.parentElement.hidden = video.parentElement.hidden = true;
      if (uri.startsWith('data:image/')) {
        image.src = e.target.result;
        image.parentElement.hidden = false;
      } else if (uri.startsWith('data:video/')) {
        video.src = e.target.result;
        video.parentElement.hidden = false;
      }
    };
    reader.readAsDataURL(file);
  });

  form.addEventListener('paste', function(ev) {
    const items = (ev.clipboardData || ev.originalEvent.clipboardData).items;
    for (let item of items) {
      if (item.type.startsWith('image/')) {
        const file = item.getAsFile();
        const reader = new FileReader();
        reader.onload = function(e) {
          video.parentElement.hidden = true;
          image.src = e.target.result;
          image.parentElement.hidden = false;
          const dataTransfer = new DataTransfer();
          dataTransfer.items.add(file);
          upload.files = dataTransfer.files;
        };
        reader.readAsDataURL(file);
        break;
      }
    }
  });

  addTextInputHandler(link, linkHandler);

  function linkHandler() {
    var url = link.value.trim();
    if (checkLink.checked && url) {
      fetch(API_BASE + '/preview?url=' + encodeURIComponent(url))
      .then(res => res.json())
      .then(data => {
        for (var key in data) {
          var field = form.querySelector(`[name="${key}"]`);
          if (field) {
            field.value = data[key];
          }
          var el = form.querySelector(`[class="${key}"]`);
          if (el) {
            el.src = data[key];
            el.parentElement.hidden = false;
          }
        }
      });
    }
  }
}

function itemHandler(section) {
  var url = `${API_BASE}/collections/${section.dataset.itemId}`;
  var button = section.querySelector('div.pin button');
  var pins = section.querySelector('div.pin ul');
  var create = document.querySelector('#new-collection');
  var notice = create.querySelector('span.notice');
  var nameEl = create.querySelector('input[type="text"]');

  fetch(url)
  .then(res => (res.ok && res.json()))
  .then(data => {
    if (!data) return;

    Object.keys(data).forEach(name => pins.appendChild(Object.assign(document.createElement('li'), { innerHTML: `
      <label data-collection="${name}"><input class="uk-checkbox" type="checkbox" ${data[name] ? 'checked' : ''}> ${name || 'Profile'}</label>
    ` })));

    pins.querySelectorAll('li input').forEach(checkbox => {
      checkbox.addEventListener('change', () => {
        fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [checkbox.parentElement.dataset.collection]: checkbox.checked }) })
        .then(res => res.json())
        .then(data => Object.keys(data).forEach(name => pins.querySelector(`li [data-collection="${name}"] input`).checked = data[name]));
      });
    });

    button.classList.remove('uk-disabled');
    button.disabled = false;
  });

  pins.querySelector('button').addEventListener('click', () => UIkit.dropdown('div.pin div.uk-dropdown').hide());
  create.querySelector('button.uk-button-primary').addEventListener('click', () => {
    var name = nameEl.value;
    if (name) {
      fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [name]: true }) })
      .then(() => location.reload());
    }
  });

  addSlugifyNoticeHandler(nameEl, notice, 'name');
}

function lightboxHandler(clickable) {
  style = clickable.parentElement.style;
  clickable.addEventListener('click', () => {
    style.width = (style.width ? '' : '100%');
  });
  clickable.addEventListener('keypress', ev => {
    if (ev.key === 'Enter') {
      clickable.click();
    }
  })
}

function copyToClipboard() {
  navigator.clipboard.writeText(document.querySelector('link[rel=canonical]').href);
  UIkit.notification('Link copied to clipboard');
}
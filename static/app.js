const API_BASE = '//' + document.documentElement.dataset.root.split('://').slice(1).join('://') + '/api';

if ('up' in window) {
  up.compiler('form.add', addHandler);
  up.compiler('div.item', itemHandler);
} else {
  var add = document.querySelector('form.add');
  if (add) {
    addHandler(add);
  }
  var item = document.querySelector('div.item');
  if (item) {
    itemHandler(item);
  }
}

function addHandler(form) {
  var link = form.querySelector('input[name="link"]');
  var pasteLink = form.querySelector('button.paste-link');
  var checkLink = form.querySelector('input.from-link');
  // var checkProxatore = form.querySelector('input.with-proxatore');
  var image = form.querySelector('img.image');
  var video = form.querySelector('video.video');
  var upload = form.querySelector('input[name="file"]');

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

  [/* 'change', */ 'input', 'paste'].forEach(event => {
    link.addEventListener(event, linkHandler);
  });

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
  var button = section.querySelector('div.pin button');
  var pins = section.querySelector('div.pin ul');
  var create = document.querySelector('#new-collection');
  var url = `${API_BASE}/collections/${section.dataset.itemId}`;

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
  create.querySelector('button.uk-button-primary').addEventListener('click', () => fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ [create.querySelector('input').value]: true }) }).then(() => location.reload()));
}
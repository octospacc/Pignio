(function(){
const HTTP_BASE = '//' + document.documentElement.dataset.root.split('://').slice(1).join('://');
const API_BASE = HTTP_BASE + '/api';

const STRINGS = {
  normalizeNotice: {
    en: (subject, text, article) => `${getArticle(article)} ${subject} will be normalized to <code>${text}</code>.`,
    it: (subject, text, article) => `${getArticle(article)} ${STRINGS.get(subject)} sarà normalizzato come <code>${text}</code>.`,
  },
  copiedLink: {
    en: "Link copied to clipboard",
    it: "Link copiato negli appunti",
  },
  Profile: {
    en: "Profile",
    it: "Profilo",
  },
  Expand: {
    en: "Expand",
    it: "Espandi",
  },
  Shrink: {
    en: "Shrink",
    it: "Riduci",
  },
  name: {
    en: "name",
    it: "nome",
  },
};
STRINGS.get = (key) => {
  const lang = document.documentElement.lang;
  const data = STRINGS[key];
  return data && data[lang] || key; // (data ? Object.values(data)[0] : key);
};

function getArticle(variant) {
  switch (document.documentElement.lang) {
    case 'it':
      return ['Il', 'Lo'][variant];
    default:
      return 'The';
  }
}

registerHandler('form.Register', (form) => addSlugifyNoticeHandler(form.querySelector('input[name="username"]'), form.querySelector('span.notice'), 'username', 1));
registerHandler('form.add', addHandler);
registerHandler('form.media-trim', mediaTrimHandler);
registerHandler('nav form.uk-search', searchHandler);
registerHandler('article.item', itemHandler);
registerHandler('article.item div.clickable', clickableHandler, true);
registerHandler('article.item div.alt-clickable', clickableHandler, false);
registerHandler('select[name="ordering"]', select => select.addEventListener('change', () => select.parentElement.submit()));
registerHandler('form.prefs select.lang', select => select.addEventListener('change', () => {
  var form = document.querySelector('form.prefs');
  form.action += '?next=' + encodeURIComponent(location.href);
  form.submit();
}));
registerHandler('form.prefs button[value="theme"]', button => button.addEventListener('click', ev => {
  ev.preventDefault();
  var form = document.querySelector('form.prefs');
  var data = new FormData(form);
  data.append('option', 'theme');
  fetch(form.action, { method: form.method, body: data }).then(() => location.reload());
}));

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

function registerHandler(query, handler, ...args) {
  if ('up' in window) {
    up.compiler(query, (el) => handler(el, ...args));
  } else {
    document.querySelectorAll(query).forEach(el => handler(el, ...args));
  }
}

function addTextInputHandler(input, handler) {
  [/* 'change', */ 'input', 'paste'].forEach(event => input.addEventListener(event, handler));
}

function addSlugifyNoticeHandler(input, notice, subject, article) {
  addTextInputHandler(input, function(){
    if (input.value) {
      fetch(API_BASE + '/v0/slugify?text=' + encodeURIComponent(input.value))
      .then(res => res.text())
      .then(text => {
        if (text !== input.value) {
          notice.innerHTML = STRINGS.get('normalizeNotice')(subject, text, article);
        } else {
          notice.textContent = '';
        }
      });
    } else {
      notice.textContent = '';
    }
  });
}

function searchHandler(form) {
  var input = form.querySelector('[name="query"]');
  addTextInputHandler(input, function(){
    var extraInput = document.querySelector('main > form.search > input[name="query"]');
    if (extraInput) {
      extraInput.value = input.value;
    }
  });
  form.addEventListener('submit', function(ev){
    var extraForm = document.querySelector('main > form.search');
    if (extraForm) {
      ev.preventDefault();
      // extraForm.submit();
      extraForm.querySelector('button[type="submit"]').click();
    }
  });
}

function addHandler(form) {
  var link = form.querySelector('input[name="link"]');
  var pasteLink = form.querySelector('button.paste-link');
  var checkLink = form.querySelector('input.from-link');
  // var checkProxatore = form.querySelector('input.with-proxatore');
  var langs = form.querySelector('select[name="langs"]');
  var collections = form.querySelector('select[name="collections"]');
  var image = form.querySelector('img.image');
  var video = form.querySelector('video.video');
  var audio = form.querySelector('audio.audio');
  var doc = form.querySelector('object.doc');
  var upload = form.querySelector('input[name="file"]');

  form.querySelector('button.langs-reset').addEventListener('click', () => (langs.selectedIndex = -1));
  form.querySelector('button.collections-reset').addEventListener('click', () => (collections.selectedIndex = 0));

  pasteLink.addEventListener('click', () => navigator.clipboard.readText().then(text => {
    link.value = text;
    linkHandler();
  }));

  upload.addEventListener('change', function(ev) {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
      const uri = e.target.result;
      const [mime, ext] = uri.split(',')[0].split(';')[0].split(':')[1].toLowerCase().split('/')
      image.parentElement.hidden = video.parentElement.hidden = audio.parentElement.hidden = doc.parentElement.hidden = true;
      if (mime === 'image') {
        image.src = uri;
        image.parentElement.hidden = false;
      } else if (mime === 'video') {
        video.src = uri;
        video.parentElement.hidden = false;
      } else if (mime === 'audio') {
        audio.src = uri;
        audio.parentElement.hidden = false;
      } else if (ext === 'pdf') {
        doc.data = uri;
        doc.parentElement.hidden = false;
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
      fetch(API_BASE + '/v0/preview?url=' + encodeURIComponent(url))
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

function mediaTrimHandler(form) {
  var minGap = 0;

  var duration;
  var media = form.parentElement.querySelector('video, audio');
  var fieldStart = form.querySelector('input[name="start"]');
  var fieldEnd = form.querySelector('input[name="end"]');

  var slider1 = form.querySelector('input[name="range-start"]');
  var slider2 = form.querySelector('input[name="range-end"]');
  var sliderTrack = form.querySelector('.slider-track');

  media.addEventListener('loadedmetadata', onLoaded);

  function onLoaded() {
    media.removeEventListener('loadedmetadata', onLoaded);

    duration = media.duration;
    media.width = media.videoWidth;
    media.height = media.videoHeight;

    fieldStart.max = fieldEnd.max = slider1.max = slider2.max = duration;
    slider2.value = duration;
    if (!fieldEnd.value) {
      fieldEnd.value = duration;
    }
    setBounds();
    slider1.disabled = slider2.disabled = false;

    fieldStart.addEventListener('input', function(){
      slider1.value = fieldStart.value;
      setBounds();
    });
    fieldEnd.addEventListener('input', function(){
      slider2.value = fieldEnd.value;
      setBounds();
    });

    slider1.addEventListener('input', slide1);
    slider2.addEventListener('input', slide2);

    form.querySelector('button[name="backward"]').addEventListener('click', function(){
      var wasPlaying = !media.paused;
      media.currentTime = fieldStart.value;
      if (wasPlaying) media.play();
    });
    form.querySelector('button[name="forward"]').addEventListener('click', function(){
      var wasPlaying = !media.paused;
      media.currentTime = fieldEnd.value;
      if (wasPlaying) media.play();
    });

    form.querySelector('button[name="set-start"]').addEventListener('click', function(){
      fieldStart.value = media.currentTime;
      slider1.value = media.currentTime;
      setBounds();
    });
    form.querySelector('button[name="set-end"]').addEventListener('click', function(){
      fieldEnd.value = media.currentTime;
      slider2.value = media.currentTime;
      setBounds();
    });

    // slide1(); slide2();
  }

  function slide1() {
    if (parseFloat(slider2.value) - parseFloat(slider1.value) <= minGap) {
      slider1.value = parseFloat(slider2.value) - minGap;
    }
    fieldStart.value = slider1.value;
    setBounds();
  }

  function slide2() {
    if (parseFloat(slider2.value) - parseFloat(slider1.value) <= minGap) {
      slider2.value = parseFloat(slider1.value) + minGap;
    }
    fieldEnd.value = slider2.value;
    setBounds();
  }

  function setBounds() {
    var percent1 = (parseFloat(slider1.value) / duration) * 100;
    var percent2 = (parseFloat(slider2.value) / duration) * 100;
    sliderTrack.style.background = `linear-gradient(to right, #dadae5 ${percent1}% , #3264fe ${percent1}% , #3264fe ${percent2}%, #dadae5 ${percent2}%)`;
    
    var wasPlaying = !media.paused;
    media.src = media.src.split('#')[0] + `#t=${fieldStart.value},${fieldEnd.value}`;
    if (wasPlaying) media.play();
  }
}

function itemHandler(section) {
  var url = `${API_BASE}/v0/collections/${section.dataset.itemId}`;
  var userUrl = document.querySelector('footer .user')?.href;
  if (!userUrl) return;

  var button = section.querySelector('div.pin button');
  var pins = section.querySelector('div.pin ul');
  var avMedia = section.querySelector('video, audio');
  var create = document.querySelector('#new-collection');
  var notice = create.querySelector('span.notice');
  var nameEl = create.querySelector('input[type="text"]');

  if (avMedia && location.hash.startsWith('#t=')) {
    avMedia.src += location.hash;
  }

  fetch(url)
  .then(res => (res.ok && res.json()))
  .then(data => {
    if (!data) return;

    Object.keys(data).forEach(name => pins.appendChild(Object.assign(document.createElement('li'), { innerHTML: `
      <label data-collection="${name}">
        <input class="uk-checkbox" type="checkbox" ${data[name] ? 'checked' : ''}> ${name || STRINGS.get('Profile')}
      </label>
      <a href="${userUrl}/${name}" class="uk-icon-link uk-float-right" uk-icon="link-external"></a>
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

  addSlugifyNoticeHandler(nameEl, notice, 'name', 0);
}

function clickableHandler(clickable, lightbox) {
  var simpleLightbox;
  if (!clickable.classList.contains('tag-nsfw')) {
    clickable.classList.remove('alt-clickable');
  }
  // if (lightbox && clickable.children[0].tagName === 'IMG') {
  //   clickable.setAttribute('href', clickable.children[0].src);
  //   new SimpleLightbox(clickable);
  // }
  clickable.addEventListener('click', function(){
    if (lightbox && !clickable.classList.contains('lightbox')) {
      clickable.classList.add('lightbox');
      // clickable.setAttribute('href', clickable.children[0].src);
      clickable.dataset.src = clickable.children[0].src;
      simpleLightbox = new SimpleLightbox(clickable, { captions: false, sourceAttr: "data-src" });
    }
    if (clickable.classList.contains('tag-nsfw') && !clickable.dataset.unblur) {
      clickable.dataset.unblur = true;
      clickable.classList.remove('alt-clickable');
    } else {
      simpleLightbox.open();
      console.log(simpleLightbox)
    }
  });
  clickable.addEventListener('keypress', ev => {
    if (ev.key === 'Enter') {
      clickable.click();
    }
  });
}

function copyToClipboard() {
  navigator.clipboard.writeText(document.querySelector('link[rel=canonical]').href);
  UIkit.notification(STRINGS.get('copiedLink'));
}

function expandShrinkContent() {
  const style = document.querySelector('article.item > div').style;
  style.width = (style.width ? '' : '100%');
  const title = style.width ? STRINGS.get('Shrink') : STRINGS.get('Expand');
  const toggle = document.querySelector('button.uk-icon.expand-shrink');
  toggle.title = title;
  toggle.setAttribute('uk-tooltip', title);
  toggle.setAttribute('uk-icon', title.toLowerCase());
}

function switchRenderMode() {
  document.body.classList.toggle('rendering-pixelated');
}

window.Pignio = {copyToClipboard, expandShrinkContent, switchRenderMode};
})();
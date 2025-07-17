if ('up' in window) {
  up.compiler('form.add', addHandler);
} else {
  var form = document.querySelector('form.add');
  if (form) {
    addHandler(form);
  }
}

function addHandler(form) {
  var link = form.querySelector('input[name="link"]');
  var checkLink = form.querySelector('input.from-link');
  // var checkProxatore = form.querySelector('input.with-proxatore');
  var image = form.querySelector('img.image');
  var upload = form.querySelector('input[name="file"]');

  upload.addEventListener('change', function(ev) {
    const file = ev.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(e) {
      image.src = e.target.result;
      image.parentElement.hidden = false;
    };
    reader.readAsDataURL(file);
  });

  document.addEventListener('paste', function(ev) {
    const items = (ev.clipboardData || ev.originalEvent.clipboardData).items;
    for (let item of items) {
      if (item.type.indexOf('image') !== -1) {
        const file = item.getAsFile();
        const reader = new FileReader();
        reader.onload = function(e) {
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

  ['change', 'input', 'paste'].forEach(handler => {
    link.addEventListener(handler, () => {
      var url = link.value.trim();
      if (checkLink.checked && url) {
        fetch('../api/preview?url=' + encodeURIComponent(url))
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
        })
      }
    })
  });
}
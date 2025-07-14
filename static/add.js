var link = document.querySelector('form input[name="link"]');
var check = document.querySelector('form input[type="checkbox"]');
var image = document.querySelector('form img.image');
var upload = document.querySelector('form input[name="file"]');

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
    if (check.checked && url) {
      fetch('../api/preview?url=' + encodeURIComponent(url))
      .then(res => res.json())
      .then(data => {
        for (var key in data) {
          var field = document.querySelector(`form [name="${key}"]`);
          if (field) {
            field.value = data[key];
          }
          var el = document.querySelector(`form [class="${key}"]`);
          if (el) {
            el.src = data[key];
            el.parentElement.hidden = false;
          }
        }
      })
    }
  })
});
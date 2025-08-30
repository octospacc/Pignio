(function(){
    document.querySelectorAll('div > h2 > span').forEach(toggle => {
        toggle.tabIndex = 0;
        toggle.role = "button";
        const paragraphs = new Map();
        const baseCasing = toggle.textContent;
        const block = toggle.parentElement.parentElement;
        block.querySelectorAll('p').forEach(p => {
            paragraphs.set(p, baseCasing === 'Sentence Case' ? p.innerHTML : null);
        });
        toggle.addEventListener('click', () => {
            const casing = toggle.textContent;
            if (casing === 'Lowercase') {
                toggle.textContent = 'Uppercase';
                setParagraphs(paragraphs, 'toUpperCase');
            } else if (casing === 'Uppercase') {
                if (baseCasing === 'Sentence Case') {
                    toggle.textContent = 'Sentence Case';
                    setParagraphs(paragraphs);
                } else {
                    toggle.textContent = 'Lowercase';
                    setParagraphs(paragraphs, 'toLowerCase');
                }
            } else if (casing === 'Sentence Case') {
                toggle.textContent = 'Lowercase';
                setParagraphs(paragraphs, 'toLowerCase');
            }
        });
        toggle.addEventListener('keypress', ev => ev.key === 'Enter' && toggle.click());
    });
    function setParagraphs(paragraphs, method) {
        paragraphs.forEach((text, p) => {
            p.innerHTML = (method ? p.innerHTML[method]() : text).replaceAll('&NBSP;', '&nbsp;');
        });
    }
})();
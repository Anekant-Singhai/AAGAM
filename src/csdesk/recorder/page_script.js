// Runs in every page and frame of the CS Desk browser while a recording is on.
// It reports three things to the recorder: what fields a page has (a "snapshot"),
// which field she changed (a "change"), and which button or link she pressed (a "click").
// Typed text goes to the recorder process on this computer, which keeps only its shape
// and which company-file field it matched; passwords, OTPs and captchas are never read.
(() => {
  if (window.__csdeskRecorder) return;
  const BINDING = '__csdeskRecord';
  const CONTROLS = 'input:not([type=hidden]):not([type=submit]):not([type=button]):not([type=reset]):not([type=image]), select, textarea';
  const PRESSABLE = 'button, input[type=submit], input[type=button], input[type=reset], [role=button], a[href]';
  const SECRET = /\b(password|passwd|otp|one[\s-]?time\s+password|captcha)\b/i;

  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const send = (type, data) => {
    try {
      const fn = window[BINDING];
      if (typeof fn === 'function') fn({ type, url: location.href, top: window === window.top, ...data });
    } catch (e) { /* recording stopped */ }
  };
  const visible = (el) => {
    if (el.type === 'file') return true; // file inputs are often hidden behind a styled button
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    const s = getComputedStyle(el);
    return s.visibility !== 'hidden' && s.display !== 'none';
  };
  const textById = (id) => {
    const el = id && document.getElementById(id);
    return el ? clean(el.innerText || el.textContent) : '';
  };

  // The same sources Playwright's getByLabel uses come first; weaker ones are marked as such.
  function labelOf(el) {
    const by = el.getAttribute('aria-labelledby');
    if (by) {
      const t = clean(by.split(/\s+/).map(textById).join(' '));
      if (t) return [t, 'aria-labelledby'];
    }
    if (el.labels && el.labels.length) {
      const t = clean([...el.labels].map((l) => l.innerText || l.textContent).join(' '));
      if (t) return [t, 'label'];
    }
    const aria = clean(el.getAttribute('aria-label'));
    if (aria) return [aria, 'aria-label'];
    const title = clean(el.getAttribute('title'));
    if (title) return [title, 'title'];
    const placeholder = clean(el.getAttribute('placeholder'));
    if (placeholder) return [placeholder, 'placeholder'];
    let node = el;
    for (let i = 0; i < 3 && node.parentElement; i++) {
      node = node.parentElement;
      const t = clean(node.innerText);
      if (t && t.length <= 120) return [t, 'nearby text'];
    }
    return ['', 'none'];
  }

  function groupLabel(el) {
    const fieldset = el.closest('fieldset');
    const legend = fieldset && fieldset.querySelector('legend');
    if (legend) return clean(legend.innerText || legend.textContent);
    const group = el.closest('[role=radiogroup]');
    if (group) {
      const by = group.getAttribute('aria-labelledby');
      const t = clean(by ? textById(by) : group.getAttribute('aria-label'));
      if (t) return t;
    }
    return '';
  }

  function sectionOf(el) {
    let best = '';
    for (const h of document.querySelectorAll('h1, h2, h3, h4, h5, legend, [role=heading]')) {
      if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) best = clean(h.innerText || h.textContent).slice(0, 120);
      else break;
    }
    return best;
  }

  function cssPath(el) {
    const unique = (sel) => { try { return document.querySelectorAll(sel).length === 1; } catch (e) { return false; } };
    if (el.id && unique('#' + CSS.escape(el.id))) return '#' + CSS.escape(el.id);
    const name = el.getAttribute('name');
    const tag = el.tagName.toLowerCase();
    if (name) {
      const sel = `${tag}[name="${CSS.escape(name)}"]`;
      if (unique(sel)) return sel;
    }
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && parts.length < 6) {
      if (node.id && unique('#' + CSS.escape(node.id))) { parts.unshift('#' + CSS.escape(node.id)); break; }
      let i = 1;
      for (let sib = node.previousElementSibling; sib; sib = sib.previousElementSibling) if (sib.tagName === node.tagName) i++;
      parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${i})`);
      node = node.parentElement;
    }
    return parts.join(' > ');
  }

  function describe(el) {
    const tag = el.tagName.toLowerCase();
    const type = tag === 'input' ? (el.getAttribute('type') || 'text').toLowerCase() : tag;
    const [label, labelSource] = labelOf(el);
    const d = {
      tag, type, id: el.id || null, name: el.getAttribute('name'), label, label_source: labelSource,
      selector: cssPath(el), section: sectionOf(el),
      required: !!(el.required || el.getAttribute('aria-required') === 'true'),
      readonly: !!el.readOnly, disabled: !!el.disabled,
      has_value: type === 'checkbox' || type === 'radio' ? el.checked : type === 'file' ? el.files.length > 0 : !!el.value,
      secret: type === 'password' || SECRET.test([label, el.getAttribute('name'), el.id, el.getAttribute('autocomplete')].join(' ')),
      maxlength: el.maxLength > 0 ? el.maxLength : null,
    };
    if (tag === 'select') d.options = [...el.options].slice(0, 100).map((o) => clean(o.text));
    if (type === 'radio') {
      d.group_label = groupLabel(el);
      d.group_selector = el.name ? `input[type=radio][name="${CSS.escape(el.name)}"]` : null;
    }
    return d;
  }

  function valueOf(el, d) {
    if (d.secret) return { kind: 'secret' };
    if (d.type === 'checkbox') return { kind: 'checkbox', checked: el.checked };
    if (d.type === 'radio') return { kind: 'radio', option: d.label, checked: el.checked };
    if (d.type === 'file') return { kind: 'file', files: [...el.files].map((f) => f.name) };
    if (d.tag === 'select') {
      const o = el.options[el.selectedIndex];
      return { kind: 'select', option: o ? clean(o.text) : '' };
    }
    return { kind: 'text', text: el.value };
  }

  const pressedName = (el) => clean(el.innerText || el.value || el.getAttribute('aria-label') || el.getAttribute('title')).slice(0, 80);

  let lastSignature = null;
  let timer = null;
  function snapshot(reason) {
    const fields = [...document.querySelectorAll(CONTROLS)].filter(visible).map(describe);
    const signature = fields.map((f) => `${f.selector}|${f.label}|${f.has_value}`).join('\n');
    if (signature === lastSignature && reason !== 'load') return;
    lastSignature = signature;
    const heading = document.querySelector('h1, h2, [role=heading]');
    const buttons = [...document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]')]
      .filter(visible).slice(0, 60).map(pressedName).filter(Boolean);
    send('snapshot', { reason, heading: heading ? clean(heading.innerText).slice(0, 200) : '', title: document.title, fields, buttons });
  }

  const onChange = (e) => {
    const el = e.target;
    if (!el || !el.matches || !el.matches(CONTROLS)) return;
    const d = describe(el);
    send('change', { field: d, value: valueOf(el, d) });
  };
  const onClick = (e) => {
    const el = e.target && e.target.closest && e.target.closest(PRESSABLE);
    if (!el) return;
    const tag = el.tagName.toLowerCase();
    send('click', {
      name: pressedName(el), tag, role: el.getAttribute('role'), selector: cssPath(el),
      names: [clean(el.innerText), el.getAttribute('value'), el.getAttribute('aria-label'), el.getAttribute('title')].filter(Boolean),
      href: tag === 'a' ? (el.getAttribute('href') || '').split('?')[0].slice(0, 200) : null,
    });
    setTimeout(() => snapshot('after click'), 1200);
  };

  const observer = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(() => snapshot('page changed'), 800);
  });
  const start = () => {
    observer.observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ['style', 'class', 'hidden', 'disabled'] });
    snapshot('load');
  };
  document.addEventListener('change', onChange, true);
  document.addEventListener('click', onClick, true);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();

  window.__csdeskRecorder = {
    uninstall() {
      document.removeEventListener('change', onChange, true);
      document.removeEventListener('click', onClick, true);
      observer.disconnect();
      clearTimeout(timer);
      delete window.__csdeskRecorder;
    },
  };
})();

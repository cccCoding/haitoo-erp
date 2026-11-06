'use strict';

// 保留原生 select 的取值、禁用和表单校验，展开面板内按模板名称检索。
function createTemplatePicker(select) {
  const make = (tag, className, text) => {
    const element = document.createElement(tag);
    element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  };
  const root = make('div', 'template-picker');
  select.before(root);
  root.append(select);
  select.classList.add('template-native');
  select.tabIndex = -1;
  select.setAttribute('aria-hidden', 'true');
  const trigger = make('button', 'template-trigger');
  trigger.type = 'button';
  trigger.setAttribute('aria-label', '产品模板');
  trigger.setAttribute('aria-haspopup', 'listbox');
  trigger.setAttribute('aria-expanded', 'false');
  const value = make('span', 'template-value');
  const caret = make('span', 'template-caret', '▾');
  caret.setAttribute('aria-hidden', 'true');
  trigger.append(value, caret);
  const panel = make('div', 'template-panel');
  panel.hidden = true;
  const search = make('input', 'template-search');
  search.type = 'text';
  search.placeholder = '搜索模板名称';
  search.setAttribute('aria-label', '搜索模板名称');
  const list = make('div', 'template-options');
  list.setAttribute('role', 'listbox');
  list.setAttribute('aria-label', '产品模板');
  const count = make('div', 'template-count');
  panel.append(search, list, count);
  root.append(trigger, panel);
  let active = 0, matches = [];

  function close(focus = false) {
    panel.hidden = true;
    root.classList.remove('is-open');
    trigger.setAttribute('aria-expanded', 'false');
    search.value = '';
    if (focus) trigger.focus();
  }
  function choose(option) {
    if (select.disabled || option.disabled) return;
    select.value = option.value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
    sync();
    close(true);
  }
  function render() {
    const terms = search.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
    matches = Array.from(select.options).filter(option => !option.disabled && terms.every(term => option.text.toLocaleLowerCase().includes(term)));
    active = Math.min(active, Math.max(0, matches.length - 1));
    list.replaceChildren();
    matches.forEach((option, index) => {
      const row = make('button', 'template-option');
      const flags = Array(option.text.length).fill(false);
      for (const term of terms) {
        let start = option.text.toLocaleLowerCase().indexOf(term);
        while (start >= 0) {
          flags.fill(true, start, start + term.length);
          start = option.text.toLocaleLowerCase().indexOf(term, start + term.length);
        }
      }
      for (let start = 0; start < option.text.length;) {
        let end = start + 1;
        while (end < option.text.length && flags[end] === flags[start]) end++;
        row.append(make(flags[start] ? 'mark' : 'span', '', option.text.slice(start, end)));
        start = end;
      }
      row.type = 'button';
      row.setAttribute('role', 'option');
      row.setAttribute('aria-selected', String(option.selected));
      row.classList.toggle('is-active', index === active);
      row.onclick = () => choose(option);
      list.append(row);
    });
    if (!matches.length) list.append(make('p', 'template-empty', search.value.trim() ? '没有匹配的模板' : '暂无可选模板'));
    count.textContent = `匹配 ${matches.length} / 共 ${select.options.length} 项`;
  }
  function open() {
    if (select.disabled) return;
    search.value = '';
    active = Math.max(0, select.selectedIndex);
    panel.hidden = false;
    root.classList.add('is-open');
    trigger.setAttribute('aria-expanded', 'true');
    render();
    search.focus();
    list.children[active]?.scrollIntoView({ block: 'nearest' });
  }
  function sync() {
    value.textContent = select.selectedOptions[0]?.text || '请选择产品模板';
    trigger.disabled = select.disabled;
    if (select.disabled) close();
  }
  trigger.onclick = () => panel.hidden ? open() : close();
  trigger.onkeydown = event => { if (event.key === 'ArrowDown') { event.preventDefault(); open(); } };
  search.oninput = () => { active = 0; render(); };
  search.onkeydown = event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(true); }
    else if (event.key === 'Tab') { trigger.focus(); close(); }
    else if (event.key === 'Enter') { event.preventDefault(); if (matches[active]) choose(matches[active]); }
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (!matches.length) return;
      active = (active + (event.key === 'ArrowDown' ? 1 : -1) + matches.length) % matches.length;
      render();
      list.children[active]?.scrollIntoView({ block: 'nearest' });
    }
  };
  select.addEventListener('change', sync);
  select.addEventListener('invalid', event => { event.preventDefault(); open(); });
  document.addEventListener('pointerdown', event => { if (!root.contains(event.target)) close(); });
  select.closest('dialog')?.addEventListener('close', () => close());
  sync();
  return { sync };
}

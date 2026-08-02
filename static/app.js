let state = { items: [], tags: [], similar: {} };
let idx = 0;
let selTag = null;
let checked = new Set();
let dirty = false;
let saveTimer = null;

const $ = id => document.getElementById(id);

async function load() {
    const r = await fetch('/api/state');
    state = await r.json();
    document.title = 'sTagCraft — ' + state.dir.split('/').pop();
    renderFiles(); renderTags(); show(0);
}

// ---------------------------------------------------------------- metadata

let metaOpen = false;
let metaSeq = 0;                 // счётчик запросов, защита от гонки

function currentName() {
    const it = state.items[idx];
    return it ? it.name : null;
}

async function loadMeta(name) {
    const seq = ++metaSeq;
    let d;
    try {
        const r = await fetch('/api/meta?name=' + encodeURIComponent(name));
        if (!r.ok) throw new Error(r.status);
        d = await r.json();
    } catch {
        d = null;
    }
    if (seq !== metaSeq) return;   // ушёл более свежий запрос — этот ответ протух
    renderMeta(d);
}

function renderMeta(d) {
    const body = $('meta-body');
    body.textContent = '';
    if (!d || !d.available) { body.textContent = 'метаданных нет'; return; }

    d.prompts.forEach(p => {
        body.appendChild(metaBlock('позитив', p.positive));
        body.appendChild(metaBlock('негатив', p.negative));
    });
}

function metaBlock(label, text) {
    const wrap = document.createElement('div');
    wrap.className = 'meta-block';
    const h = document.createElement('div');
    h.className = 'meta-label';
    h.textContent = label;
    const v = document.createElement('div');
    v.className = 'meta-text';
    v.textContent = text;
    wrap.append(h, v);
    return wrap;
}

$('metadata').addEventListener('toggle', () => {
    metaOpen = $('metadata').open;
    if (metaOpen) loadMeta(currentName());
});

// теги текущего кадра как есть, с дублями и в исходном порядке
function curTags() {
    return $('cap').value.split(',').map(s => s.trim()).filter(Boolean);
}

function setCurTags(arr) {
    $('cap').value = arr.join(', ');
    markDirty();
    renderChips();
    renderTags();
}

function visibleItems() {
    if (!selTag) return state.items;
    return state.items.filter(it =>
        it.caption.split(',').map(s => s.trim()).includes(selTag));
}

function renderFiles() {
    const box = $('files');
    box.innerHTML = '';
    visibleItems().forEach((it) => {
        const real = state.items.indexOf(it);
        const d = document.createElement('div');
        d.className = 'thumb' + (real === idx ? ' active' : '');
        const tg = it.caption.split(',').map(s => s.trim()).filter(Boolean);
        const n = tg.length;
        const dup = n - new Set(tg).size;
        const info = n ? n + ' тег.' : 'пусто';
        const dupHtml = dup ? ' · <span class="dup">' + dup + ' дубл.</span>' : '';
        d.innerHTML = `
      <input type="checkbox" class="box" ${checked.has(it.name) ? 'checked' : ''}>
      <img src="/img/${encodeURIComponent(it.name)}" loading="lazy">
      <div class="meta">
        <div class="nm">${it.name}</div>
        <div class="cnt ${n ? '' : 'empty'}">${info}${dupHtml}</div>
      </div>`;
        d.querySelector('.box').onclick = e => {
            e.stopPropagation();
            e.target.checked ? checked.add(it.name) : checked.delete(it.name);
            $('ncheck').textContent = checked.size;
        };
        d.onclick = () => show(real);
        box.appendChild(d);
    });
}

function renderTags() {
    const f = $('filter').value.trim().toLowerCase();
    const box = $('taglist');
    const keep = box.scrollTop;          // не дёргать список при листании кадров
    const here = new Set(curTags());
    box.innerHTML = '';
    state.tags
        .filter(([t]) => !f || t.toLowerCase().includes(f))
        .forEach(([t, c]) => {
            const near = state.similar[t] || [];
            const on = here.has(t);
            const d = document.createElement('div');
            d.className = 'tag'
                + (t === selTag ? ' sel' : '')
                + (c <= 2 ? ' lonely' : '')
                + (near.length ? ' sim' : '')
                + (on ? ' on' : '');
            d.innerHTML = `<span class="n">${t}</span>`
                + `<span class="add">${on ? '✓' : '+'}</span>`
                + `<span class="c">${c}</span>`;
            if (near.length) {
                d.querySelector('.n').title = 'похоже на: ' + near.join(', ');
            }
            const add = d.querySelector('.add');
            add.title = on ? 'уже в этом кадре' : 'добавить в текущий кадр';
            add.onclick = e => {
                e.stopPropagation();
                if (on) return;
                setCurTags([...curTags(), t]);
            };
            d.onclick = () => {
                selTag = (selTag === t) ? null : t;
                renderTags(); renderFiles();
            };
            box.appendChild(d);
        });
    box.scrollTop = keep;
    if (window.updateRenNote) updateRenNote();
}

function show(i) {
    if (dirty) saveNow();
    if (i < 0 || i >= state.items.length) return;
    idx = i;
    const it = state.items[idx];
    $('pic').src = '/img/' + encodeURIComponent(it.name);
    $('cap').value = it.caption;
    $('curname').textContent = it.name;
    $('pos').textContent = `${idx + 1}/${state.items.length}`;
    $('pos').textContent = `${idx + 1}/${state.items.length}`;
    $('meta-body').textContent = '';              // гасим предыдущий кадр сразу
    if (metaOpen) loadMeta(it.name);
    renderChips(); renderFiles(); renderTags();
    const act = document.querySelector('.thumb.active');
    if (act) act.scrollIntoView({ block: 'nearest' });
}

function renderChips() {
    const box = $('chips');
    box.innerHTML = '';
    const counts = Object.fromEntries(state.tags);
    const tags = curTags();
    const seen = new Set();
    tags.forEach((t, i) => {
        const c = document.createElement('span');
        const n = counts[t] || 0;
        const dup = seen.has(t);
        const near = state.similar[t] || [];
        seen.add(t);

        // приоритет: дубль > похожий > редкий
        let cls = 'chip';
        let title = 'убрать';
        if (dup) {
            cls += ' dup';
            title = 'дубль внутри кэпшена — клик убирает эту копию';
        } else if (near.length) {
            cls += ' sim';
            title = 'похоже на: ' + near.join(', ') + ' — клик убирает';
        } else if (n <= 2) {
            cls += ' rare';
            title = 'редкий тег (' + n + ') — клик убирает';
        }
        c.className = cls;
        c.textContent = n > 1 ? `${t} · ${n}` : t;
        c.title = title;
        // удаляем именно эту позицию, иначе клик по дублю снёс бы обе копии
        c.onclick = () => setCurTags(tags.filter((_, j) => j !== i));
        box.appendChild(c);
    });
}

function markDirty() {
    dirty = true;
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 700);
}

async function saveNow() {
    if (!dirty) return;
    const it = state.items[idx];
    const cap = $('cap').value;
    it.caption = cap;
    dirty = false;
    const r = await fetch('/api/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: it.name, caption: cap })
    });
    const d = await r.json();
    if (d.tags) {
        state.tags = d.tags;
        state.similar = d.similar || {};
        renderTags(); renderChips();
    }
    renderFiles();
    const s = $('status');
    s.classList.add('show');
    setTimeout(() => s.classList.remove('show'), 900);
}

$('cap').addEventListener('input', markDirty);
$('cap').addEventListener('blur', saveNow);
$('filter').addEventListener('input', renderTags);

document.addEventListener('keydown', e => {
    const typing = ['TEXTAREA', 'INPUT'].includes(e.target.tagName);
    if (e.ctrlKey && e.key === 's') { e.preventDefault(); saveNow(); return; }
    if (typing) return;
    if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); step(1); }
    if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); step(-1); }
});

function step(d) {
    const vis = visibleItems();
    const cur = vis.indexOf(state.items[idx]);
    const next = vis[Math.min(Math.max(cur + d, 0), vis.length - 1)];
    if (next) show(state.items.indexOf(next));
}

// ---------------------------------------------------------- автодополнение

function tagCount(t) {
    const f = state.tags.find(([x]) => x === t);
    return f ? f[1] : 0;
}

/* Выпадающий список тегов датасета под полем ввода.
   Свой, а не <datalist>: нужно показывать частоту рядом с тегом
   и не зависеть от того, как браузер рисует нативный попап. */
function attachAC(input, onchange) {
    const wrap = document.createElement('div');
    wrap.className = 'ac';
    input.parentNode.insertBefore(wrap, input);
    wrap.appendChild(input);
    const list = document.createElement('div');
    list.className = 'ac-list';
    wrap.appendChild(list);

    let hits = [], cur = -1;

    const close = () => { list.classList.remove('open'); cur = -1; };

    function mark() {
        [...list.children].forEach((el, i) => el.classList.toggle('cur', i === cur));
        if (cur >= 0) list.children[cur].scrollIntoView({ block: 'nearest' });
    }

    function pick(t) {
        input.value = t;
        close();
        onchange();
    }

    function open() {
        const q = input.value.trim().toLowerCase();
        hits = state.tags
            .filter(([t]) => !q || t.toLowerCase().includes(q))
            .slice(0, 40);
        list.innerHTML = '';
        if (!hits.length) { close(); return; }
        hits.forEach(([t, c]) => {
            const d = document.createElement('div');
            d.className = 'ac-item';
            d.innerHTML = `<span class="n">${t}</span><span class="c">${c}</span>`;
            // mousedown, а не click: click прилетел бы уже после blur
            d.onmousedown = e => { e.preventDefault(); pick(t); };
            list.appendChild(d);
        });
        cur = -1;
        list.classList.add('open');
    }

    input.addEventListener('input', () => { open(); onchange(); });
    input.addEventListener('focus', open);
    input.addEventListener('blur', close);
    input.addEventListener('keydown', e => {
        const isOpen = list.classList.contains('open');
        if (e.key === 'ArrowDown' && isOpen) {
            e.preventDefault(); cur = Math.min(cur + 1, hits.length - 1); mark();
        } else if (e.key === 'ArrowUp' && isOpen) {
            e.preventDefault(); cur = Math.max(cur - 1, 0); mark();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (isOpen && cur >= 0) pick(hits[cur][0]);
            else { close(); $('ren-go').click(); }
        } else if (e.key === 'Escape') {
            close();
        }
    });
}

function updateRenNote() {
    const old = $('ren-old').value.trim();
    const neu = $('ren-new').value.trim();
    const note = $('ren-note');
    const btn = $('ren-go');
    note.className = 'note';

    if (!old) { note.textContent = ''; btn.disabled = true; return; }

    const n = tagCount(old);
    if (!n) {
        note.textContent = 'нет такого тега в датасете';
        note.classList.add('err');
        btn.disabled = true;
        return;
    }

    btn.disabled = false;
    const m = neu ? tagCount(neu) : 0;
    if (!neu) {
        note.textContent = `удалить «${old}» из ${n} кадр.`;
    } else if (m) {
        note.textContent = `${n} кадр. → сольётся с «${neu}» (уже в ${m} кадр.)`;
    } else {
        note.textContent = `${n} кадр. → новый тег «${neu}»`;
    }
}

attachAC($('ren-old'), updateRenNote);
attachAC($('ren-new'), updateRenNote);

$('ren-go').onclick = async () => {
    const old = $('ren-old').value.trim();
    if (!old || !tagCount(old)) return;
    const r = await fetch('/api/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ old, new: $('ren-new').value })
    });
    const d = await r.json();
    state = { items: d.items, tags: d.tags, similar: d.similar, dir: d.dir };
    $('ren-old').value = ''; $('ren-new').value = '';
    renderTags(); show(idx);
    const note = $('ren-note');
    note.className = 'note done';
    note.textContent = 'изменено файлов: ' + d.changed;
};

async function bulk(mode) {
    const tag = $('bulk-tag').value.trim();
    if (!tag || !checked.size) return;
    const r = await fetch('/api/bulk', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ names: [...checked], tag, mode })
    });
    const d = await r.json();
    state = { items: d.items, tags: d.tags, similar: d.similar, dir: d.dir };
    renderTags(); show(idx);
}
$('bulk-add').onclick = () => bulk('add');
$('bulk-del').onclick = () => bulk('del');

load();
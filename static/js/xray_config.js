(function () {
    'use strict';

    var API = '/api/xray/config';
    var EDITOR_FIELD_ID = 'config_yaml';
    var EDITOR_KEY = 'config_yaml';
    var state = {
        mode: 'form',
        schema: null,
        structured: null,
        text: '',
        path: '',
        activeSection: null,
        dirty: false,
    };

    var els = {};

    function $(id) {
        return document.getElementById(id);
    }

    function getMonacoEditor() {
        if (window.__monacoEditors && window.__monacoEditors[EDITOR_KEY]) {
            return window.__monacoEditors[EDITOR_KEY];
        }
        return null;
    }

    function getAceEditor() {
        if (!window.ace) return null;
        try {
            return window.ace.edit('editor-' + EDITOR_KEY);
        } catch (e) {
            return null;
        }
    }

    function getTextEditorValue() {
        var monacoEd = getMonacoEditor();
        if (monacoEd) return monacoEd.getValue();
        var aceEd = getAceEditor();
        if (aceEd) return aceEd.getValue();
        var hidden = document.getElementById(EDITOR_FIELD_ID);
        return hidden ? hidden.value : (state.text || '');
    }

    function setTextEditorValue(text) {
        text = text == null ? '' : String(text);
        var hidden = document.getElementById(EDITOR_FIELD_ID);
        if (hidden) hidden.value = text;
        var monacoEd = getMonacoEditor();
        if (monacoEd && monacoEd.getValue() !== text) {
            monacoEd.setValue(text);
        }
        var aceEd = getAceEditor();
        if (aceEd && aceEd.getValue() !== text) {
            aceEd.setValue(text, -1);
        }
    }

    function layoutTextEditor() {
        var monacoEd = getMonacoEditor();
        if (monacoEd && typeof monacoEd.layout === 'function') {
            // после снятия d-none Monaco нужно пересчитать размер
            setTimeout(function () { monacoEd.layout(); }, 0);
        }
        var aceEd = getAceEditor();
        if (aceEd && typeof aceEd.resize === 'function') {
            setTimeout(function () { aceEd.resize(); }, 0);
        }
    }

    function showStatus(message, kind) {
        var el = els.status;
        if (!el) return;
        el.className = 'alert mb-3 alert-' + (kind || 'info');
        el.textContent = message;
        el.classList.remove('d-none');
    }

    function hideStatus() {
        if (els.status) els.status.classList.add('d-none');
    }

    function escapeHtml(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getByPath(obj, path) {
        if (!path) return obj;
        var cur = obj;
        var parts = path.split('.');
        for (var i = 0; i < parts.length; i++) {
            if (cur == null || typeof cur !== 'object') return undefined;
            cur = cur[parts[i]];
        }
        return cur;
    }

    function setByPath(obj, path, value) {
        var parts = path.split('.');
        var cur = obj;
        for (var i = 0; i < parts.length - 1; i++) {
            if (!cur[parts[i]] || typeof cur[parts[i]] !== 'object') {
                cur[parts[i]] = {};
            }
            cur = cur[parts[i]];
        }
        cur[parts[parts.length - 1]] = value;
    }

    function parseInputValue(type, raw, checked) {
        if (type === 'bool') return !!checked;
        if (type === 'null') {
            var t = String(raw).trim();
            if (t === '' || t === 'null') return null;
            return t;
        }
        if (type === 'int') {
            if (raw === '' || raw == null) return null;
            var n = parseInt(raw, 10);
            return isNaN(n) ? null : n;
        }
        if (type === 'float') {
            if (raw === '' || raw == null) return null;
            var f = parseFloat(raw);
            return isNaN(f) ? null : f;
        }
        if (type === 'list') {
            var s = String(raw).trim();
            if (!s) return [];
            try {
                return JSON.parse(s);
            } catch (e) {
                try {
                    // простой YAML flow: [a, b]
                    return JSON.parse(s.replace(/'/g, '"'));
                } catch (e2) {
                    throw new Error('Invalid list JSON for value: ' + s);
                }
            }
        }
        return raw == null ? '' : String(raw);
    }

    function collectFormValues() {
        var root = {};
        var inputs = els.formFields.querySelectorAll('[data-config-path]');
        for (var i = 0; i < inputs.length; i++) {
            var input = inputs[i];
            var path = input.getAttribute('data-config-path');
            var type = input.getAttribute('data-config-type') || 'str';
            var value;
            if (input.tagName === 'SELECT' || input.getAttribute('data-config-choices') === '1') {
                value = parseChoiceWire(input.value, type);
            } else if (type === 'bool') {
                value = parseInputValue(type, null, input.checked);
            } else {
                value = parseInputValue(type, input.value, false);
            }
            setByPath(root, path, value);
        }
        return root;
    }

    function choiceLabel(v) {
        if (v === null || v === undefined) return 'null';
        if (typeof v === 'boolean') return v ? 'true' : 'false';
        return String(v);
    }

    function choiceWireValue(v) {
        // значение в option value / для сравнения
        if (v === null || v === undefined) return '__null__';
        if (typeof v === 'boolean') return v ? '__true__' : '__false__';
        return String(v);
    }

    function parseChoiceWire(wire, type) {
        if (wire === '__null__') return null;
        if (wire === '__true__') return true;
        if (wire === '__false__') return false;
        return parseInputValue(type === 'null' ? 'null' : type, wire, false);
    }

    function renderSelect(path, type, value, choices) {
        var html = '<select class="form-select" id="cfg-' + escapeHtml(path) +
            '" data-config-path="' + escapeHtml(path) +
            '" data-config-type="' + escapeHtml(type) +
            '" data-config-choices="1">';
        var currentWire = choiceWireValue(value);
        var seen = {};
        for (var i = 0; i < choices.length; i++) {
            var c = choices[i];
            var wire = choiceWireValue(c);
            if (seen[wire]) continue;
            seen[wire] = true;
            html += '<option value="' + escapeHtml(wire) + '"' +
                (wire === currentWire ? ' selected' : '') + '>' +
                escapeHtml(choiceLabel(c)) + '</option>';
        }
        if (!seen[currentWire]) {
            html += '<option value="' + escapeHtml(currentWire) + '" selected>' +
                escapeHtml(choiceLabel(value)) + '</option>';
        }
        html += '</select>';
        return html;
    }

    function renderLeaf(node) {
        var path = node.path;
        var type = node.type || 'str';
        var help = node.help || '';
        var choices = node.choices;
        var value = getByPath(state.structured, path);
        if (value === undefined) value = node.value;

        var html = '<div class="mb-3">';
        html += '<label class="form-label" for="cfg-' + escapeHtml(path) + '"><code>' +
            escapeHtml(node.key) + '</code></label>';

        if (choices && choices.length && type !== 'list') {
            var selectType = type === 'null' ? 'null' : type;
            // для enum со строками/null — сохраняем через wire-значения
            html += renderSelect(path, selectType, value, choices);
        } else if (type === 'bool') {
            html += '<div class="form-check form-switch">';
            html += '<input class="form-check-input" type="checkbox" id="cfg-' + escapeHtml(path) +
                '" data-config-path="' + escapeHtml(path) + '" data-config-type="bool"' +
                (value ? ' checked' : '') + '>';
            html += '<label class="form-check-label" for="cfg-' + escapeHtml(path) + '">' +
                (value ? 'true' : 'false') + '</label></div>';
        } else if (type === 'int' || type === 'float') {
            html += '<input class="form-control" type="number" step="' +
                (type === 'float' ? 'any' : '1') + '" id="cfg-' + escapeHtml(path) +
                '" data-config-path="' + escapeHtml(path) + '" data-config-type="' + type +
                '" value="' + escapeHtml(value == null ? '' : value) + '">';
        } else if (type === 'list') {
            var listStr = '';
            try {
                listStr = JSON.stringify(value == null ? [] : value);
            } catch (e) {
                listStr = '[]';
            }
            html += '<textarea class="form-control font-monospace" rows="2" id="cfg-' +
                escapeHtml(path) + '" data-config-path="' + escapeHtml(path) +
                '" data-config-type="list">' + escapeHtml(listStr) + '</textarea>';
        } else {
            // str / null
            var display = value == null ? '' : value;
            html += '<input class="form-control" type="text" id="cfg-' + escapeHtml(path) +
                '" data-config-path="' + escapeHtml(path) + '" data-config-type="' +
                (type === 'null' ? 'null' : 'str') + '" value="' + escapeHtml(display) +
                '" placeholder="' + (type === 'null' ? 'null' : '') + '">';
        }

        if (help) {
            html += '<div class="form-text" style="white-space: pre-line;">' +
                escapeHtml(help) + '</div>';
        }
        html += '</div>';
        return html;
    }

    function renderObject(node, depth) {
        var html = '';
        var children = node.children || [];
        for (var i = 0; i < children.length; i++) {
            var child = children[i];
            if (child.type === 'object') {
                html += '<fieldset class="border rounded p-3 mb-3">';
                html += '<legend class="float-none w-auto px-2 fs-6"><code>' +
                    escapeHtml(child.key) + '</code></legend>';
                if (child.help) {
                    html += '<p class="form-text mt-0" style="white-space: pre-line;">' +
                        escapeHtml(child.help) + '</p>';
                }
                html += renderObject(child, depth + 1);
                html += '</fieldset>';
            } else {
                html += renderLeaf(child);
            }
        }
        return html;
    }

    function renderSections() {
        var schema = state.schema;
        var sections = (schema && schema.children) || [];
        els.sections.innerHTML = '';
        if (!sections.length) {
            els.formFields.innerHTML = '<div class="text-muted">No sections</div>';
            return;
        }
        if (!state.activeSection || !sections.some(function (s) { return s.key === state.activeSection; })) {
            state.activeSection = sections[0].key;
        }
        for (var i = 0; i < sections.length; i++) {
            var sec = sections[i];
            var li = document.createElement('li');
            li.className = 'nav-item';
            li.setAttribute('role', 'presentation');
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'nav-link' + (sec.key === state.activeSection ? ' active' : '');
            btn.textContent = sec.key;
            btn.setAttribute('data-section', sec.key);
            btn.addEventListener('click', function (ev) {
                // перед сменой секции сохранить текущие поля в structured
                try {
                    var partial = collectFormValues();
                    state.structured = deepMerge(state.structured || {}, partial);
                } catch (e) {
                    showStatus(e.message || String(e), 'danger');
                    return;
                }
                state.activeSection = ev.currentTarget.getAttribute('data-section');
                renderSections();
            });
            li.appendChild(btn);
            els.sections.appendChild(li);
        }
        var active = sections.filter(function (s) { return s.key === state.activeSection; })[0];
        els.formFields.innerHTML = active ? renderObject(active, 0) : '';
        bindFormDirty();
    }

    function deepMerge(a, b) {
        var out = Object.assign({}, a);
        Object.keys(b || {}).forEach(function (k) {
            if (b[k] && typeof b[k] === 'object' && !Array.isArray(b[k]) &&
                a[k] && typeof a[k] === 'object' && !Array.isArray(a[k])) {
                out[k] = deepMerge(a[k], b[k]);
            } else {
                out[k] = b[k];
            }
        });
        return out;
    }

    function bindFormDirty() {
        var inputs = els.formFields.querySelectorAll('[data-config-path]');
        for (var i = 0; i < inputs.length; i++) {
            inputs[i].addEventListener('change', function () { state.dirty = true; });
            inputs[i].addEventListener('input', function () { state.dirty = true; });
            if (inputs[i].type === 'checkbox') {
                inputs[i].addEventListener('change', function (ev) {
                    var lab = ev.target.parentNode.querySelector('.form-check-label');
                    if (lab) lab.textContent = ev.target.checked ? 'true' : 'false';
                });
            }
        }
    }

    function setMode(mode) {
        state.mode = mode;
        var isForm = mode === 'form';
        els.formPane.classList.toggle('d-none', !isForm);
        els.textPane.classList.toggle('d-none', isForm);
        els.modeForm.classList.toggle('active', isForm);
        els.modeText.classList.toggle('active', !isForm);
        if (!isForm) {
            layoutTextEditor();
        }
    }

    function applyPayload(data) {
        state.text = data.text || '';
        state.structured = data.structured || {};
        state.schema = data.schema || { children: [] };
        state.path = data.path || '';
        els.path.textContent = state.path;
        setTextEditorValue(state.text);
        if (data.warning) {
            els.warning.textContent = data.warning;
        }
        renderSections();
        state.dirty = false;
        if (state.mode === 'text') {
            layoutTextEditor();
        }
    }

    function load() {
        hideStatus();
        return fetch(API, { credentials: 'same-origin' })
            .then(function (r) {
                return r.json().then(function (data) {
                    if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
                    return data;
                });
            })
            .then(function (data) {
                applyPayload(data);
            })
            .catch(function (err) {
                showStatus(err.message || String(err), 'danger');
            });
    }

    function save() {
        hideStatus();
        var body;
        try {
            if (state.mode === 'text') {
                body = { mode: 'text', text: getTextEditorValue() };
            } else {
                var partial = collectFormValues();
                var values = deepMerge(state.structured || {}, partial);
                body = { mode: 'form', values: values };
            }
        } catch (e) {
            showStatus(e.message || String(e), 'danger');
            return;
        }

        els.save.disabled = true;
        fetch(API, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        })
            .then(function (r) {
                return r.json().then(function (data) {
                    if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
                    return data;
                });
            })
            .then(function (data) {
                applyPayload(data);
                showStatus(
                    (data.warning || 'Saved.') + '',
                    'success'
                );
            })
            .catch(function (err) {
                showStatus(err.message || String(err), 'danger');
            })
            .finally(function () {
                els.save.disabled = false;
            });
    }

    function init() {
        els.root = $('xray-config-root');
        if (!els.root) return;
        els.warning = $('xray-config-warning');
        els.status = $('xray-config-status');
        els.path = $('xray-config-path');
        els.save = $('xray-config-save');
        els.refresh = $('xray-config-refresh');
        els.modeForm = $('xray-config-mode-form');
        els.modeText = $('xray-config-mode-text');
        els.formPane = $('xray-config-form-pane');
        els.textPane = $('xray-config-text-pane');
        els.sections = $('xray-config-sections');
        els.formFields = $('xray-config-form-fields');
        els.textarea = document.getElementById(EDITOR_FIELD_ID);

        els.modeForm.addEventListener('click', function () {
            if (state.mode === 'form') return;
            // сохранить текст из редактора в state перед уходом с вкладки
            state.text = getTextEditorValue();
            setMode('form');
            renderSections();
        });
        els.modeText.addEventListener('click', function () {
            if (state.mode === 'text') return;
            try {
                var partial = collectFormValues();
                state.structured = deepMerge(state.structured || {}, partial);
            } catch (e) {
                showStatus(e.message || String(e), 'danger');
                return;
            }
            setMode('text');
        });
        els.save.addEventListener('click', save);
        if (els.refresh) {
            els.refresh.addEventListener('click', load);
        }
        if (els.textarea) {
            els.textarea.addEventListener('input', function () { state.dirty = true; });
            els.textarea.addEventListener('change', function () { state.dirty = true; });
        }

        setMode('form');
        load();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();

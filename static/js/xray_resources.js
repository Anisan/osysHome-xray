/**
 * Shared Resources dashboard + widget runtime.
 * Mount once per .xray-res root (full page or single-metric widget).
 */
(function (global) {
    if (global.XrayResources) return;

    var STORAGE_KEY = 'xray.resources.cardModes';
    var HISTORY_MINUTES = 30;

    var DEFAULT_MODES = {
        cpu: 'spark',
        memory: 'spark',
        disk: 'value',
        threads: 'spark',
        network: 'history',
        connections: 'history',
        fds: 'spark',
        children: 'spark',
        listen: 'value',
        remotes: 'spark',
        process: 'spark',
        diskio: 'value',
        uptime: 'value'
    };

    var PRESETS = {
        values: {
            cpu: 'value', memory: 'value', disk: 'value', threads: 'value',
            network: 'value', connections: 'value', fds: 'value', children: 'value',
            listen: 'value', remotes: 'value', process: 'value', diskio: 'value'
        },
        sparks: {
            cpu: 'spark', memory: 'spark', disk: 'spark', threads: 'spark',
            network: 'history', connections: 'history', fds: 'spark', children: 'spark',
            listen: 'spark', remotes: 'spark', process: 'spark', diskio: 'value'
        },
        history: {
            cpu: 'history', memory: 'history', disk: 'history', threads: 'history',
            network: 'history', connections: 'history', fds: 'history', children: 'history',
            listen: 'history', remotes: 'history', process: 'history', diskio: 'history'
        }
    };

    var MODE_ICONS = {
        value: 'fa-font',
        spark: 'fa-chart-line',
        history: 'fa-chart-area'
    };

    function cssVar(name, fallback) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
    }

    function themeColors() {
        var primary = cssVar('--bs-primary', '#0d6efd');
        var primaryRgb = cssVar('--bs-primary-rgb', '13, 110, 253');
        var secondaryRgb = cssVar('--bs-secondary-rgb', '108, 117, 125');
        var muted = cssVar('--bs-secondary-color', '#6c757d');
        var border = cssVar('--bs-border-color', '#dee2e6');
        return {
            primary: primary,
            primaryFill: 'rgba(' + primaryRgb + ', 0.22)',
            secondary: 'rgba(' + secondaryRgb + ', 0.9)',
            secondaryFill: 'rgba(' + secondaryRgb + ', 0.12)',
            muted: muted,
            grid: border
        };
    }

    function fmtBytesPerSec(v) {
        if (v == null || isNaN(v)) return '0 B/s';
        var abs = Math.abs(v);
        if (abs >= 1048576) return (v / 1048576).toFixed(2) + ' MB/s';
        if (abs >= 1024) return (v / 1024).toFixed(1) + ' KB/s';
        return Math.round(v) + ' B/s';
    }

    function fmtUptime(sec) {
        sec = Math.max(0, Math.floor(sec || 0));
        var d = Math.floor(sec / 86400);
        var h = Math.floor((sec % 86400) / 3600);
        var m = Math.floor((sec % 3600) / 60);
        if (d > 0) return d + 'd ' + h + 'h';
        if (h > 0) return h + 'h ' + m + 'm';
        if (m > 0) return m + 'm ' + (sec % 60) + 's';
        return (sec % 60) + 's';
    }

    function loadModes() {
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return Object.assign({}, DEFAULT_MODES);
            return Object.assign({}, DEFAULT_MODES, JSON.parse(raw));
        } catch (e) {
            return Object.assign({}, DEFAULT_MODES);
        }
    }

    function saveModes(modes) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(modes)); } catch (e) {}
    }

    function baseOptions(spark) {
        var c = themeColors();
        return {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false }, tooltip: { enabled: !spark } },
            scales: spark ? {
                x: { display: false },
                y: { display: false, beginAtZero: true }
            } : {
                x: {
                    ticks: { maxTicksLimit: 7, color: c.muted, font: { size: 10 } },
                    grid: { display: false },
                    border: { display: false }
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: c.muted, font: { size: 10 } },
                    grid: { color: c.grid, borderDash: [4, 4], drawBorder: false },
                    border: { display: false }
                }
            }
        };
    }

    function lineDataset(label, color, fill) {
        return {
            label: label,
            data: [],
            borderColor: color,
            backgroundColor: fill,
            borderWidth: 2,
            tension: 0.35,
            pointRadius: 0,
            pointHoverRadius: 3,
            fill: !!fill,
            cubicInterpolationMode: 'monotone'
        };
    }

    /**
     * @param {HTMLElement} root
     * @param {object} opts
     * @param {string} [opts.idPrefix='']
     * @param {number} [opts.pollMs=3000]
     * @param {boolean} [opts.enablePresets=false]
     * @param {object} [opts.i18n]
     */
    function mount(root, opts) {
        if (!root || typeof Chart === 'undefined') {
            console.error('XrayResources: root or Chart.js missing');
            return null;
        }
        opts = opts || {};
        var prefix = opts.idPrefix || '';
        var pollMs = opts.pollMs || 3000;
        var i18n = Object.assign({
            download: 'Download',
            upload: 'Upload',
            read: 'Read',
            write: 'Write',
            process: 'process',
            nicNetns: 'NIC / netns',
            throughputNA: 'throughput N/A',
            updated: 'Updated'
        }, opts.i18n || {});

        var charts = {};
        var modes = loadModes();
        var lastHistory = null;
        var pollTimer = null;
        var themeObserver = null;

        function el(id) {
            return document.getElementById(prefix + id);
        }

        function setText(id, text) {
            var node = el(id);
            if (node) node.textContent = text;
        }

        function setHtml(id, html) {
            var node = el(id);
            if (node) node.innerHTML = html;
        }

        function destroyChart(id) {
            var full = prefix + id;
            if (charts[full]) {
                charts[full].destroy();
                delete charts[full];
            }
        }

        function makeChart(id, datasets, options) {
            destroyChart(id);
            var node = el(id);
            if (!node) return null;
            var full = prefix + id;
            charts[full] = new Chart(node.getContext('2d'), {
                type: 'line',
                data: { labels: [], datasets: datasets },
                options: options
            });
            return charts[full];
        }

        function updateChart(id, labels, series) {
            var chart = charts[prefix + id];
            if (!chart) return;
            chart.data.labels = labels;
            series.forEach(function (data, i) {
                if (chart.data.datasets[i]) chart.data.datasets[i].data = data;
            });
            chart.update('none');
        }

        function cardMetrics() {
            var list = [];
            root.querySelectorAll('[data-card]').forEach(function (card) {
                list.push(card.getAttribute('data-card'));
            });
            return list;
        }

        function initCharts() {
            var c = themeColors();
            var sparkOpt = baseOptions(true);
            var histOpt = baseOptions(false);
            var metrics = cardMetrics();
            var has = {};
            metrics.forEach(function (m) { has[m] = true; });

            ['cpu', 'memory', 'disk', 'threads'].forEach(function (name) {
                if (!has[name]) return;
                makeChart('spark-' + name, [lineDataset(name, c.primary, c.primaryFill)], sparkOpt);
                makeChart('hist-' + name, [lineDataset(name, c.primary, c.primaryFill)], histOpt);
            });

            if (has.process) {
                makeChart('spark-process', [
                    lineDataset('RSS', c.primary, c.primaryFill),
                    lineDataset('VMS', c.secondary, c.secondaryFill)
                ], sparkOpt);
                makeChart('hist-process', [
                    lineDataset('RSS', c.primary, c.primaryFill),
                    lineDataset('VMS', c.secondary, c.secondaryFill)
                ], histOpt);
            }

            if (has.network) {
                makeChart('chart-network-io', [
                    lineDataset(i18n.download, c.primary, c.primaryFill),
                    lineDataset(i18n.upload, c.secondary, c.secondaryFill)
                ], histOpt);
            }

            if (has.connections) {
                makeChart('chart-connections', [
                    lineDataset('ESTABLISHED', c.primary, c.primaryFill),
                    lineDataset('CLOSE_WAIT', cssVar('--bs-warning', '#ffc107'), 'rgba(255, 193, 7, 0.18)'),
                    lineDataset('TIME_WAIT', c.secondary, c.secondaryFill)
                ], Object.assign({}, histOpt, {
                    scales: Object.assign({}, histOpt.scales, {
                        y: Object.assign({}, histOpt.scales.y, {
                            ticks: Object.assign({}, histOpt.scales.y.ticks, { precision: 0 })
                        })
                    })
                }));
            }

            if (has.diskio) {
                makeChart('chart-disk-io', [
                    lineDataset(i18n.read, c.primary, c.primaryFill),
                    lineDataset(i18n.write, c.secondary, c.secondaryFill)
                ], histOpt);
            }

            if (has.fds) {
                makeChart('spark-fds', [lineDataset('fds', c.primary, c.primaryFill)], sparkOpt);
                makeChart('hist-fds', [lineDataset('fds', c.primary, c.primaryFill)], histOpt);
            }
            if (has.children) {
                makeChart('spark-children', [
                    lineDataset('count', c.primary, c.primaryFill),
                    lineDataset('CPU %', c.secondary, c.secondaryFill)
                ], sparkOpt);
                makeChart('hist-children', [
                    lineDataset('count', c.primary, c.primaryFill),
                    lineDataset('CPU %', c.secondary, c.secondaryFill)
                ], histOpt);
            }
            if (has.listen) {
                makeChart('spark-listen', [lineDataset('listen', c.primary, c.primaryFill)], sparkOpt);
                makeChart('hist-listen', [lineDataset('listen', c.primary, c.primaryFill)], histOpt);
            }
            if (has.remotes) {
                makeChart('spark-remotes', [
                    lineDataset('hosts', c.primary, c.primaryFill),
                    lineDataset('conns', c.secondary, c.secondaryFill)
                ], sparkOpt);
                makeChart('hist-remotes', [
                    lineDataset('hosts', c.primary, c.primaryFill),
                    lineDataset('conns', c.secondary, c.secondaryFill)
                ], histOpt);
            }
        }

        function applyThemeToCharts() {
            var c = themeColors();
            Object.keys(charts).forEach(function (id) {
                var chart = charts[id];
                if (!chart) return;
                var spark = id.indexOf('spark-') >= 0;
                if (chart.data.datasets[0]) {
                    chart.data.datasets[0].borderColor = c.primary;
                    chart.data.datasets[0].backgroundColor = c.primaryFill;
                }
                if (chart.data.datasets[1] && chart.data.datasets[1].label !== 'CLOSE_WAIT') {
                    chart.data.datasets[1].borderColor = c.secondary;
                    chart.data.datasets[1].backgroundColor = c.secondaryFill;
                }
                if (!spark && chart.options.scales && chart.options.scales.x) {
                    chart.options.scales.x.ticks.color = c.muted;
                    chart.options.scales.y.ticks.color = c.muted;
                    chart.options.scales.y.grid.color = c.grid;
                }
                chart.update('none');
            });
        }

        function buildModeButtons() {
            root.querySelectorAll('.xr-modes[data-modes]').forEach(function (wrap) {
                var card = wrap.closest('[data-card]');
                if (!card) return;
                var id = card.getAttribute('data-card');
                var allowed = (wrap.getAttribute('data-modes') || 'value,spark,history').split(',');
                wrap.innerHTML = '';
                allowed.forEach(function (mode) {
                    var btn = document.createElement('button');
                    btn.type = 'button';
                    btn.setAttribute('data-mode', mode);
                    btn.title = mode;
                    btn.innerHTML = '<i class="fas ' + (MODE_ICONS[mode] || 'fa-circle') + '"></i>';
                    btn.addEventListener('click', function () {
                        setCardMode(id, mode);
                    });
                    wrap.appendChild(btn);
                });
            });
        }

        function resizeCharts() {
            requestAnimationFrame(function () {
                Object.keys(charts).forEach(function (cid) {
                    if (charts[cid]) charts[cid].resize();
                });
            });
        }

        function setCardMode(id, mode) {
            modes[id] = mode;
            saveModes(modes);
            applyModesToDom();
            if (lastHistory) paintHistory(lastHistory);
            resizeCharts();
        }

        function applyModesToDom() {
            root.querySelectorAll('[data-card]').forEach(function (card) {
                var id = card.getAttribute('data-card');
                var mode = modes[id] || card.getAttribute('data-mode') || 'value';
                card.setAttribute('data-mode', mode);
                card.querySelectorAll('.xr-modes button').forEach(function (btn) {
                    btn.classList.toggle('active', btn.getAttribute('data-mode') === mode);
                });
            });
            if (opts.enablePresets) {
                root.querySelectorAll('[data-preset]').forEach(function (btn) {
                    var preset = PRESETS[btn.getAttribute('data-preset')];
                    var active = preset && Object.keys(preset).every(function (k) {
                        return modes[k] === preset[k];
                    });
                    btn.classList.toggle('active', !!active);
                    btn.classList.toggle('btn-secondary', !!active);
                    btn.classList.toggle('btn-outline-secondary', !active);
                });
            }
        }

        function applyStats(data) {
            var lastEl = el('resources-last-update');
            if (!data || data.available === false) {
                if (lastEl) {
                    lastEl.textContent = (data && data.error) ? data.error : 'unavailable';
                }
                return;
            }

            setText('res-cpu', (data.cpu_percent != null ? data.cpu_percent : 0).toFixed(1));
            setText('res-mem-pct-val', (data.memory_percent != null ? data.memory_percent : 0).toFixed(1));
            setText('res-rss',
                (data.memory_rss_mb != null ? data.memory_rss_mb : 0).toFixed(2) +
                ' MB / VMS ' + (data.memory_vms_mb != null ? data.memory_vms_mb : 0).toFixed(1) + ' MB');
            setText('res-rss-big', (data.memory_rss_mb != null ? data.memory_rss_mb : 0).toFixed(1) + ' MB');
            setText('res-vms-big', (data.memory_vms_mb != null ? data.memory_vms_mb : 0).toFixed(1) + ' MB');
            setText('res-threads', data.num_threads != null ? data.num_threads : '—');
            setText('res-fds', data.num_fds != null ? ('fds/handles: ' + data.num_fds) : '');

            if (el('res-fds-count')) {
                setText('res-fds-count', data.num_fds != null ? data.num_fds : '—');
                if (data.fd_soft_limit != null) {
                    setText('res-fds-limit',
                        (data.fd_usage_percent != null ? data.fd_usage_percent.toFixed(1) + '% · ' : '') +
                        'soft ' + data.fd_soft_limit +
                        (data.fd_hard_limit != null ? ' / hard ' + data.fd_hard_limit : ''));
                } else {
                    setText('res-fds-limit', data.num_fds != null ? 'handles (no rlimit)' : '—');
                }
            }

            if (el('res-children-count')) {
                setText('res-children-count', data.children_count != null ? data.children_count : 0);
                setText('res-children-stats',
                    'CPU ' + (data.children_cpu_percent != null ? data.children_cpu_percent : 0).toFixed(1) +
                    '% · RSS ' + (data.children_memory_rss_mb != null ? data.children_memory_rss_mb : 0).toFixed(1) + ' MB');
            }
            if (el('res-top-children')) {
                var children = data.top_children || [];
                setHtml('res-top-children', children.length
                    ? children.map(function (c) {
                        return '<div><strong>' +
                            Number(c.cpu_percent != null ? c.cpu_percent : 0).toFixed(1) +
                            '%</strong> · ' + (c.name || ('pid:' + c.pid)) +
                            ' <span class="text-muted">#' + c.pid + '</span>' +
                            ' · ' + Number(c.memory_rss_mb != null ? c.memory_rss_mb : 0).toFixed(1) +
                            ' MB</div>';
                    }).join('')
                    : '—');
            }

            if (el('res-listen-count')) {
                var ports = data.listen_ports || [];
                setText('res-listen-count', ports.length || (data.net_listen != null ? data.net_listen : 0));
                setText('res-listen-ports', ports.length ? ports.join(', ') : '—');
            }

            if (el('res-top-remotes')) {
                var remotes = data.top_remotes || [];
                var totalConns = remotes.reduce(function (a, r) { return a + (r.count || 0); }, 0);
                setText('res-remotes-total', remotes.length
                    ? (remotes.length + ' hosts · ' + totalConns + ' conn')
                    : '0');
                setHtml('res-top-remotes', remotes.length
                    ? remotes.map(function (r) {
                        return '<div><strong>' + r.count + '</strong> · ' + r.addr + '</div>';
                    }).join('')
                    : '—');
            }

            var usedPct = Math.max(0, 100 - (data.disk_free_percent != null ? data.disk_free_percent : 0));
            setText('res-disk-used-pct', usedPct.toFixed(1));
            setText('res-disk-used',
                (data.disk_used_gb != null ? data.disk_used_gb : 0).toFixed(2) + ' / ' +
                (data.disk_total_gb != null ? data.disk_total_gb : 0).toFixed(2) + ' GB');

            setText('res-net-conn', data.net_established != null ? data.net_established
                : (data.net_connections != null ? data.net_connections : '—'));
            setText('res-net-est', data.net_established != null ? data.net_established
                : (data.net_connections != null ? data.net_connections : 0));
            setText('res-net-cw', data.net_close_wait != null ? data.net_close_wait : 0);
            setText('res-net-tw', data.net_time_wait != null ? data.net_time_wait : 0);
            setText('res-net-states',
                'LISTEN ' + (data.net_listen != null ? data.net_listen : 0) +
                ' · other ' + (data.net_other != null ? data.net_other : 0));

            if (data.net_io_available) {
                setText('res-net-recv', fmtBytesPerSec(data.net_recv_bps));
                setText('res-net-sent', fmtBytesPerSec(data.net_sent_bps));
                setText('res-net-scope',
                    data.net_io_scope === 'process' ? i18n.process : i18n.nicNetns);
            } else {
                setText('res-net-recv', 'N/A');
                setText('res-net-sent', 'N/A');
                setText('res-net-scope', i18n.throughputNA);
            }

            setText('res-io-read-big', fmtBytesPerSec(data.io_read_bps));
            setText('res-io-write-big', fmtBytesPerSec(data.io_write_bps));
            setText('res-uptime', fmtUptime(data.uptime_sec));
            setText('res-pid', 'pid ' + (data.pid != null ? data.pid : '—'));

            if (lastEl) {
                lastEl.textContent = i18n.updated + ': ' +
                    new Date((data.timestamp || Date.now() / 1000) * 1000).toLocaleTimeString();
            }
        }

        function paintHistory(history) {
            if (!history || !history.length) return;
            var labels = history.map(function (h) {
                return new Date(h.timestamp * 1000).toLocaleTimeString();
            });
            var cpu = history.map(function (h) { return h.cpu_percent; });
            var memPct = history.map(function (h) { return h.memory_percent; });
            var diskUsed = history.map(function (h) {
                return Math.max(0, 100 - (h.disk_free_percent || 0));
            });
            var threads = history.map(function (h) { return h.num_threads; });
            var recv = history.map(function (h) { return h.net_recv_bps || 0; });
            var sent = history.map(function (h) { return h.net_sent_bps || 0; });
            var conn = history.map(function (h) {
                return h.net_established != null ? h.net_established : h.net_connections;
            });
            var cw = history.map(function (h) { return h.net_close_wait || 0; });
            var tw = history.map(function (h) { return h.net_time_wait || 0; });
            var ioR = history.map(function (h) { return h.io_read_bps || 0; });
            var ioW = history.map(function (h) { return h.io_write_bps || 0; });
            var rss = history.map(function (h) { return h.memory_rss_mb; });
            var vms = history.map(function (h) { return h.memory_vms_mb; });
            var fds = history.map(function (h) { return h.num_fds != null ? h.num_fds : null; });
            var chCount = history.map(function (h) { return h.children_count || 0; });
            var chCpu = history.map(function (h) { return h.children_cpu_percent || 0; });
            var listen = history.map(function (h) {
                if (h.listen_ports && h.listen_ports.length) return h.listen_ports.length;
                return h.net_listen || 0;
            });
            var remoteHosts = history.map(function (h) {
                return (h.top_remotes && h.top_remotes.length) ? h.top_remotes.length : 0;
            });
            var remoteConns = history.map(function (h) {
                var rem = h.top_remotes || [];
                return rem.reduce(function (a, r) { return a + (r.count || 0); }, 0);
            });

            updateChart('spark-cpu', labels, [cpu]);
            updateChart('hist-cpu', labels, [cpu]);
            updateChart('spark-memory', labels, [memPct]);
            updateChart('hist-memory', labels, [memPct]);
            updateChart('spark-disk', labels, [diskUsed]);
            updateChart('hist-disk', labels, [diskUsed]);
            updateChart('spark-threads', labels, [threads]);
            updateChart('hist-threads', labels, [threads]);
            updateChart('spark-process', labels, [rss, vms]);
            updateChart('hist-process', labels, [rss, vms]);
            updateChart('chart-network-io', labels, [recv, sent]);
            updateChart('chart-connections', labels, [conn, cw, tw]);
            updateChart('chart-disk-io', labels, [ioR, ioW]);
            updateChart('spark-fds', labels, [fds]);
            updateChart('hist-fds', labels, [fds]);
            updateChart('spark-children', labels, [chCount, chCpu]);
            updateChart('hist-children', labels, [chCount, chCpu]);
            updateChart('spark-listen', labels, [listen]);
            updateChart('hist-listen', labels, [listen]);
            updateChart('spark-remotes', labels, [remoteHosts, remoteConns]);
            updateChart('hist-remotes', labels, [remoteHosts, remoteConns]);

            var n = history.length;
            var avgRecv = recv.reduce(function (a, b) { return a + b; }, 0) / n;
            var avgSent = sent.reduce(function (a, b) { return a + b; }, 0) / n;
            setText('res-net-avg', fmtBytesPerSec(avgRecv) + ' / ' + fmtBytesPerSec(avgSent));
        }

        function applyHistory(payload) {
            lastHistory = (payload && payload.history) || [];
            paintHistory(lastHistory);
        }

        function refresh() {
            fetch('/api/xray/resources/stats')
                .then(function (r) { return r.json(); })
                .then(applyStats)
                .catch(function (err) { console.error('resources stats', err); });
            fetch('/api/xray/resources/history?minutes=' + HISTORY_MINUTES)
                .then(function (r) { return r.json(); })
                .then(applyHistory)
                .catch(function (err) { console.error('resources history', err); });
        }

        function watchResize() {
            if (typeof ResizeObserver === 'undefined') return;
            var ro = new ResizeObserver(function () { resizeCharts(); });
            ro.observe(root);
            var item = root.closest('.grid-stack-item');
            if (item) ro.observe(item);
        }

        buildModeButtons();
        applyModesToDom();
        initCharts();
        watchResize();
        refresh();
        pollTimer = setInterval(refresh, pollMs);
        setTimeout(resizeCharts, 100);

        if (opts.enablePresets) {
            root.querySelectorAll('[data-preset]').forEach(function (btn) {
                btn.addEventListener('click', function () {
                    var name = btn.getAttribute('data-preset');
                    var preset = PRESETS[name];
                    if (!preset) return;
                    modes = Object.assign({}, DEFAULT_MODES, preset);
                    saveModes(modes);
                    applyModesToDom();
                    if (lastHistory) paintHistory(lastHistory);
                    resizeCharts();
                });
            });
        }

        if (document.body && window.MutationObserver) {
            themeObserver = new MutationObserver(function (mutations) {
                for (var i = 0; i < mutations.length; i++) {
                    if (mutations[i].attributeName === 'data-bs-theme' ||
                        mutations[i].attributeName === 'data-ui-theme') {
                        applyThemeToCharts();
                        break;
                    }
                }
            });
            themeObserver.observe(document.body, { attributes: true });
            if (document.documentElement) {
                themeObserver.observe(document.documentElement, { attributes: true });
            }
        }

        return {
            destroy: function () {
                if (pollTimer) clearInterval(pollTimer);
                if (themeObserver) themeObserver.disconnect();
                Object.keys(charts).forEach(function (id) {
                    if (charts[id]) charts[id].destroy();
                });
                charts = {};
            },
            refresh: refresh
        };
    }

    global.XrayResources = { mount: mount };
})(window);

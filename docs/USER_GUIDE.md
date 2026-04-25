# XRAY - User Guide

![XRAY Icon](../static/xray.png "XRAY plugin")

## Purpose

`XRAY` is a system diagnostics module for osysHome. It gives administrators one place to inspect runtime state and perform maintenance operations for:

- background cycles;
- cache;
- object storage;
- object properties and methods activity;
- notifications;
- database state;
- thread pools and threads;
- cleaner statistics;
- Python/system packages and environment.

> [!IMPORTANT]
> XRAY includes destructive actions (`clear`, `drop`, remove from storage, clear notifications). Use them only when you understand the impact.

---

## What the User Gets

| Capability | What it does |
| --- | --- |
| Live service control | Start, stop, or restart plugin cycles |
| Cache diagnostics | Show cache keys/values and clear cache |
| Storage diagnostics | Show in-memory object stats and remove entries |
| Runtime telemetry | View properties/methods access stats, source, and timing |
| Notifications center | Mark read/unread, delete one, or clear all |
| DB diagnostics | View DB info, table sizes/counts, pool health and history |
| Thread diagnostics | See thread pools, queue metrics, execution times, and active threads |
| System page | Python info, package list, and install package from UI |
| Analytics page | Real-time charts built from advanced object stats |
| Dashboard widgets | `default` and `batch_writer` widgets |

---

## Admin Interface Overview

Main page:

```text
/admin/xray
```

Main tabs:

1. `Cycles`
2. `Cache`
3. `Objects storage`
4. `Properties`
5. `Methods`
6. `Notifications`
7. `Database`
8. `Thread Pools`
9. `Threads`
10. `Cleaner`
11. `System`
12. `Analytics`

---

## Quick Start Checklist

- [ ] Open `/admin/xray`.
- [ ] Check `Cycles` and ensure required plugins are alive.
- [ ] Check `Database` health score and pool usage.
- [ ] Check `Thread Pools` for queue growth, failures, and rejected tasks.
- [ ] Check `Notifications` and mark or clear old records.
- [ ] Use cleanup operations only if needed (`cache`, `storage`, `notifications`, tables).

---

## Common User Workflows

### 1) Restart a stuck cyclic module

1. Open `Cycles`.
2. Find the module row.
3. Click `Restart` (or `Start`/`Stop`).

### 2) Clear stale cache entries

1. Open `Cache`.
2. Review key/value rows.
3. Click `Clear cache`.

### 3) Remove orphan object from memory storage

1. Open `Objects storage`.
2. Locate object by name/description.
3. Click `Remove from storage`.

### 4) Work with notifications

1. Open `Notifications`.
2. Use per-row actions (`Read`, `Unread`, `Delete`).
3. Use bulk actions (`Read all`, `Clear all`) if needed.

### 5) Inspect database health and clean tables

1. Open `Database`.
2. Check DB metadata and pool cards.
3. Review table row count and size.
4. Use `Clear` or `Drop` for a table only with full impact awareness.

> [!CAUTION]
> `Drop` removes the table itself, not only data.

### 6) Track runtime performance hotspots

1. Open `Thread Pools` to inspect utilization and recent tasks.
2. Open `Analytics` for top methods, slow methods, timeline, and load levels.
3. Open `Methods` and `Properties` for object-level details.

---

## Tab-by-Tab Notes

### `Cycles`

- Shows plugins that expose the `cycle` action.
- Displays last activity and alive/stopped state.
- Provides `Restart`, `Stop`, `Start`.

### `Cache`

- Shows cache backend type (`redis`, `simple`, ...).
- Displays key/value snapshot in a sortable table.
- `Clear cache` clears the full backend.

### `Objects storage`

- Shows object usage counters: `getObject`, `getProperty`, `setProperty`, `callMethod`.
- Supports full storage clear and per-object remove.

### `Properties`

- Shows read/write counters and timestamps.
- Shows source and current value.
- Useful to find noisy or stale properties.

### `Methods`

- Shows execution counters, last execution time, and accumulated execution time.
- Shows invocation source and params.

### `Notifications`

- Color-coded by category.
- Supports mark read/unread, delete, mark all read, clear all.

### `Database`

- Left card: DB type, version, size, counts, connection info.
- Right cards: active connections, pool health score, overflow.
- Chart: pool usage history.
- Table list: row count/size/module plus admin cleanup actions.

### `Thread Pools`

- Polls every 30 seconds.
- Shows utilization, queue size, completed/failed/rejected tasks.
- Includes batch writer metrics and recent tasks table.

### `Threads`

- Lists all runtime threads (`id`, `name`, `alive`, `daemon`).

### `Cleaner`

- Shows cleanup history for object properties with retention details.

### `System`

- Shows Python runtime, executable, venv info, Flask version.
- Shows installed packages (`pip list --format=freeze`).
- Allows installing package by name from the page.

### `Analytics`

- Real-time charts (refresh every 30 seconds):
- object operations distribution;
- top methods by count;
- top slow methods;
- activity timeline;
- load-level distribution;
- source distribution;
- health overview.

---

## Widgets

XRAY exposes two widgets:

| Widget name | Description |
| --- | --- |
| `default` | Services alive/stopped and object count snapshot |
| `batch_writer` | Batch writer operational statistics |

---

## Troubleshooting

### Pool cards show no data

Check:

- module initialized correctly;
- API endpoint `/api/xray/database/pool/stats` is reachable;
- current user has admin permissions and API key in API calls.

### Thread pools tab is empty

Check:

- thread-pool providers are available in runtime (`_poolLinkedProperty`, `_poolSay`, `_poolPlaysound`, `_batch_writer`);
- browser console for failed requests to `/api/xray/thread_pools/stats`.

### Package install fails

Check:

- internet/package index availability on server;
- python executable rights for `pip install`;
- package name validity.

---

## See Also

- [Technical Reference](TECHNICAL_REFERENCE.md)
- [Module index](index.md)

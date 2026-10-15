from __future__ import annotations

import os
import time
import threading
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ResourceStats:
    timestamp: float
    available: bool
    cpu_percent: float
    memory_rss_mb: float
    memory_vms_mb: float
    memory_percent: float
    num_threads: int
    num_fds: Optional[int]
    fd_soft_limit: Optional[int]
    fd_hard_limit: Optional[int]
    fd_usage_percent: Optional[float]
    io_read_bps: float
    io_write_bps: float
    net_connections: int  # ESTABLISHED (compat)
    net_established: int
    net_close_wait: int
    net_time_wait: int
    net_listen: int
    net_other: int
    net_sent_bps: Optional[float]
    net_recv_bps: Optional[float]
    net_io_available: bool
    net_io_scope: str  # process | netns | none
    listen_ports: List[str] = field(default_factory=list)
    top_remotes: List[Dict[str, Any]] = field(default_factory=list)
    children_count: int = 0
    children_cpu_percent: float = 0.0
    children_memory_rss_mb: float = 0.0
    top_children: List[Dict[str, Any]] = field(default_factory=list)
    disk_free_percent: float = 0.0
    disk_used_gb: float = 0.0
    disk_total_gb: float = 0.0
    uptime_sec: float = 0.0
    pid: int = 0
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _unavailable_stats(now: float, error: str = "") -> ResourceStats:
    return ResourceStats(
        timestamp=now,
        available=False,
        cpu_percent=0.0,
        memory_rss_mb=0.0,
        memory_vms_mb=0.0,
        memory_percent=0.0,
        num_threads=0,
        num_fds=None,
        fd_soft_limit=None,
        fd_hard_limit=None,
        fd_usage_percent=None,
        io_read_bps=0.0,
        io_write_bps=0.0,
        net_connections=0,
        net_established=0,
        net_close_wait=0,
        net_time_wait=0,
        net_listen=0,
        net_other=0,
        net_sent_bps=None,
        net_recv_bps=None,
        net_io_available=False,
        net_io_scope="none",
        pid=os.getpid(),
        error=error,
    )


class ResourceMonitor:
    """Periodic process-level resource sampling for osysHome (in-memory only)."""

    def __init__(self, logger, disk_path: Optional[str] = None):
        self.logger = logger
        self.disk_path = disk_path or os.getcwd()
        self.stats_history: List[ResourceStats] = []
        self.max_history = 1000
        self._lock = threading.Lock()
        self._monitoring = False
        self._psutil = None
        self._process = None
        self._last_io = None  # (ts, read_bytes, write_bytes)
        self._last_net = None  # (ts, sent, recv)
        self._latest: Optional[ResourceStats] = None
        self._primed_children: set = set()

        try:
            import psutil

            self._psutil = psutil
            self._process = psutil.Process(os.getpid())
            self._process.cpu_percent(interval=None)
        except ImportError:
            self.logger.warning("psutil is not installed; resource monitoring unavailable")
        except Exception as ex:
            self.logger.warning("Resource monitor init failed: %s", ex)
            self._psutil = None
            self._process = None

    @property
    def available(self) -> bool:
        return self._psutil is not None and self._process is not None

    def _collect_io_rates(self, now: float) -> tuple:
        read_bps = 0.0
        write_bps = 0.0
        try:
            io = self._process.io_counters()
            read_b = int(io.read_bytes or 0)
            write_b = int(io.write_bytes or 0)
            for child in self._process.children(recursive=True):
                try:
                    cio = child.io_counters()
                    read_b += int(cio.read_bytes or 0)
                    write_b += int(cio.write_bytes or 0)
                except Exception:
                    continue
            if self._last_io is not None:
                prev_ts, prev_r, prev_w = self._last_io
                dt = max(now - prev_ts, 1e-6)
                read_bps = max((read_b - prev_r) / dt, 0.0)
                write_bps = max((write_b - prev_w) / dt, 0.0)
            self._last_io = (now, read_b, write_b)
        except Exception:
            pass
        return round(read_bps, 2), round(write_bps, 2)

    def _list_inet_connections(self):
        try:
            if hasattr(self._process, "net_connections"):
                return self._process.net_connections(kind="inet")
            return self._process.connections(kind="inet")
        except Exception:
            return []

    def _fmt_addr(self, addr) -> str:
        if not addr:
            return ""
        ip = getattr(addr, "ip", None)
        port = getattr(addr, "port", None)
        if ip is None and isinstance(addr, (tuple, list)) and len(addr) >= 2:
            ip, port = addr[0], addr[1]
        if ip is None:
            return str(addr)
        return f"{ip}:{port}"

    def _collect_connection_details(self) -> Dict[str, Any]:
        established = getattr(self._psutil, "CONN_ESTABLISHED", "ESTABLISHED")
        close_wait = getattr(self._psutil, "CONN_CLOSE_WAIT", "CLOSE_WAIT")
        time_wait = getattr(self._psutil, "CONN_TIME_WAIT", "TIME_WAIT")
        listen = getattr(self._psutil, "CONN_LISTEN", "LISTEN")

        counts = {
            "established": 0,
            "close_wait": 0,
            "time_wait": 0,
            "listen": 0,
            "other": 0,
        }
        listen_ports: List[str] = []
        remote_counter: Counter = Counter()

        try:
            conns = self._list_inet_connections()
        except Exception:
            conns = []

        for c in conns:
            status = getattr(c, "status", None)
            if status == established:
                counts["established"] += 1
            elif status == close_wait:
                counts["close_wait"] += 1
            elif status == time_wait:
                counts["time_wait"] += 1
            elif status == listen:
                counts["listen"] += 1
                local = self._fmt_addr(getattr(c, "laddr", None))
                if local and local not in listen_ports:
                    listen_ports.append(local)
            else:
                counts["other"] += 1

            if status == established:
                remote = self._fmt_addr(getattr(c, "raddr", None))
                if remote:
                    # aggregate by host only for cleaner top
                    host = remote.rsplit(":", 1)[0]
                    remote_counter[host] += 1

        listen_ports.sort()
        top_remotes = [
            {"addr": addr, "count": int(cnt)}
            for addr, cnt in remote_counter.most_common(5)
        ]
        return {
            **counts,
            "listen_ports": listen_ports,
            "top_remotes": top_remotes,
        }

    def _read_net_io_counters(self) -> tuple:
        if hasattr(self._process, "net_io_counters"):
            try:
                counters = self._process.net_io_counters()
                if counters is not None:
                    return (
                        int(getattr(counters, "bytes_sent", 0) or 0),
                        int(getattr(counters, "bytes_recv", 0) or 0),
                        "process",
                    )
            except Exception:
                pass
        counters = self._psutil.net_io_counters()
        if counters is None:
            raise RuntimeError("net_io_counters unavailable")
        return (
            int(getattr(counters, "bytes_sent", 0) or 0),
            int(getattr(counters, "bytes_recv", 0) or 0),
            "netns",
        )

    def _collect_net_io(self, now: float) -> tuple:
        sent_bps: Optional[float] = None
        recv_bps: Optional[float] = None
        net_io_available = False
        net_io_scope = "none"
        try:
            sent, recv, scope = self._read_net_io_counters()
            net_io_available = True
            net_io_scope = scope
            if self._last_net is not None:
                prev_ts, prev_s, prev_r = self._last_net
                dt = max(now - prev_ts, 1e-6)
                sent_bps = round(max((sent - prev_s) / dt, 0.0), 2)
                recv_bps = round(max((recv - prev_r) / dt, 0.0), 2)
            else:
                sent_bps = 0.0
                recv_bps = 0.0
            self._last_net = (now, sent, recv)
        except Exception:
            pass
        return sent_bps, recv_bps, net_io_available, net_io_scope

    def _collect_disk(self) -> tuple:
        try:
            usage = self._psutil.disk_usage(self.disk_path)
            total_gb = usage.total / (1024 ** 3)
            used_gb = usage.used / (1024 ** 3)
            free_percent = round(100.0 - usage.percent, 2)
            return free_percent, round(used_gb, 3), round(total_gb, 3)
        except Exception:
            return 0.0, 0.0, 0.0

    def _collect_fd_limits(self, num_fds: Optional[int]) -> tuple:
        soft = hard = usage = None
        try:
            if hasattr(self._process, "rlimit") and hasattr(self._psutil, "RLIMIT_NOFILE"):
                soft, hard = self._process.rlimit(self._psutil.RLIMIT_NOFILE)
                soft = int(soft)
                hard = int(hard)
                if num_fds is not None and soft > 0:
                    usage = round(100.0 * num_fds / soft, 2)
        except Exception:
            pass
        return soft, hard, usage

    def _collect_children(self) -> tuple:
        count = 0
        cpu = 0.0
        rss = 0
        mem_pct = 0.0
        details: List[Dict[str, Any]] = []
        try:
            children = self._process.children(recursive=True)
        except Exception:
            return 0, 0.0, 0.0, 0.0, []
        for child in children:
            try:
                count += 1
                if child.pid not in self._primed_children:
                    child_cpu = float(child.cpu_percent(interval=None) or 0.0)
                    self._primed_children.add(child.pid)
                else:
                    child_cpu = float(child.cpu_percent(interval=None) or 0.0)
                    cpu += child_cpu
                child_rss = int(child.memory_info().rss or 0)
                rss += child_rss
                mem_pct += float(child.memory_percent() or 0.0)
                try:
                    name = child.name() or f"pid:{child.pid}"
                except Exception:
                    name = f"pid:{child.pid}"
                details.append({
                    "pid": int(child.pid),
                    "name": name,
                    "cpu_percent": round(child_cpu, 1),
                    "memory_rss_mb": round(child_rss / (1024 ** 2), 1),
                })
            except Exception:
                continue
        alive = {c.pid for c in children if hasattr(c, "pid")}
        self._primed_children &= alive
        details.sort(
            key=lambda d: (d.get("cpu_percent") or 0, d.get("memory_rss_mb") or 0),
            reverse=True,
        )
        top_children = details[:5]
        return (
            count,
            round(cpu, 2),
            round(rss / (1024 ** 2), 2),
            round(mem_pct, 2),
            top_children,
        )

    def get_resource_stats(self) -> ResourceStats:
        now = time.time()
        if not self.available:
            return _unavailable_stats(now, "psutil unavailable")

        try:
            parent_cpu = float(self._process.cpu_percent(interval=None) or 0.0)
            mem = self._process.memory_info()
            parent_rss = int(mem.rss or 0)
            parent_vms = int(mem.vms or 0)
            parent_mem_pct = float(self._process.memory_percent() or 0.0)
            threads = int(self._process.num_threads() or 0)

            children_count, children_cpu, children_rss_mb, children_mem_pct, top_children = (
                self._collect_children()
            )
            vms = parent_vms
            try:
                for child in self._process.children(recursive=True):
                    try:
                        threads += int(child.num_threads() or 0)
                        vms += int(child.memory_info().vms or 0)
                    except Exception:
                        continue
            except Exception:
                pass

            cpu = round(parent_cpu + children_cpu, 2)
            rss = parent_rss + int(children_rss_mb * (1024 ** 2))
            mem_percent = round(parent_mem_pct + children_mem_pct, 2)

            num_fds = None
            try:
                if hasattr(self._process, "num_fds"):
                    num_fds = int(self._process.num_fds())
                elif hasattr(self._process, "num_handles"):
                    num_fds = int(self._process.num_handles())
            except Exception:
                num_fds = None

            fd_soft, fd_hard, fd_usage = self._collect_fd_limits(num_fds)
            create_time = float(self._process.create_time() or now)
            uptime = max(now - create_time, 0.0)

            io_read_bps, io_write_bps = self._collect_io_rates(now)
            conn = self._collect_connection_details()
            net_sent_bps, net_recv_bps, net_io_available, net_io_scope = self._collect_net_io(now)
            disk_free, disk_used, disk_total = self._collect_disk()

            established = int(conn["established"])
            return ResourceStats(
                timestamp=now,
                available=True,
                cpu_percent=cpu,
                memory_rss_mb=round(rss / (1024 ** 2), 2),
                memory_vms_mb=round(vms / (1024 ** 2), 2),
                memory_percent=mem_percent,
                num_threads=threads,
                num_fds=num_fds,
                fd_soft_limit=fd_soft,
                fd_hard_limit=fd_hard,
                fd_usage_percent=fd_usage,
                io_read_bps=io_read_bps,
                io_write_bps=io_write_bps,
                net_connections=established,
                net_established=established,
                net_close_wait=int(conn["close_wait"]),
                net_time_wait=int(conn["time_wait"]),
                net_listen=int(conn["listen"]),
                net_other=int(conn["other"]),
                net_sent_bps=net_sent_bps,
                net_recv_bps=net_recv_bps,
                net_io_available=net_io_available,
                net_io_scope=net_io_scope,
                listen_ports=list(conn["listen_ports"]),
                top_remotes=list(conn["top_remotes"]),
                children_count=children_count,
                children_cpu_percent=children_cpu,
                children_memory_rss_mb=children_rss_mb,
                top_children=list(top_children),
                disk_free_percent=disk_free,
                disk_used_gb=disk_used,
                disk_total_gb=disk_total,
                uptime_sec=round(uptime, 1),
                pid=self._process.pid,
            )
        except Exception as ex:
            self.logger.debug("Resource sample failed: %s", ex)
            return _unavailable_stats(now, str(ex))

    def sample(self) -> ResourceStats:
        stats = self.get_resource_stats()
        with self._lock:
            self._latest = stats
            if stats.available:
                self.stats_history.append(stats)
                if len(self.stats_history) > self.max_history:
                    self.stats_history.pop(0)
        return stats

    def get_latest(self) -> Optional[ResourceStats]:
        with self._lock:
            return self._latest

    def get_stats_history(self, minutes: int = 30) -> List[ResourceStats]:
        cutoff = time.time() - (minutes * 60)
        with self._lock:
            return [s for s in self.stats_history if s.timestamp > cutoff]

    def start_monitoring(self, interval: float = 2.0):
        if self._monitoring:
            return
        if not self.available:
            self.logger.warning("Resource monitoring not started (psutil unavailable)")
            return

        self._monitoring = True
        interval = max(float(interval), 0.5)

        def monitor_loop():
            while self._monitoring:
                try:
                    self.sample()
                except Exception as ex:
                    self.logger.error("Resource monitoring error: %s", ex)
                time.sleep(interval)

        thread = threading.Thread(target=monitor_loop, daemon=True, name="xray-resource-monitor")
        thread.start()
        self.logger.info("Resource monitoring started with %.1fs interval", interval)

    def stop_monitoring(self):
        self._monitoring = False
        self.logger.info("Resource monitoring stopped")

from flask import request, jsonify
from flask_restx import Namespace, Resource
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_admin_required
from plugins.xray import xray
import time
from app.core.lib.common import writeSystemStatsMetric, incrementSystemStatsMetric
from app.core.lib.constants import PropertyType

_api_ns = Namespace(name="Xray", description="XRay namespace", validate=True)

_instance: xray = None
_PLUGIN = "xray"


def _record_api_call(metric_prefix: str, handler):
    """Record API request count, errors and latency to SystemStats."""
    incrementSystemStatsMetric(_PLUGIN, "api_requests_total", 1)
    start = time.perf_counter()
    try:
        result = handler()
        status = 200
        if isinstance(result, tuple) and len(result) > 1:
            status = result[1]
        if status >= 400:
            incrementSystemStatsMetric(_PLUGIN, "api_errors_total", 1)
        return result
    except Exception:
        incrementSystemStatsMetric(_PLUGIN, "api_errors_total", 1)
        raise
    finally:
        latency_ms = round((time.perf_counter() - start) * 1000, 2)
        writeSystemStatsMetric(
            _PLUGIN,
            f"api_{metric_prefix}_latency_ms",
            latency_ms,
            prop_type=PropertyType.Float,
        )


def _collect_thread_pool_stats(pool_obj, pool_alias: str):
    """
    Return unified stats mapping for classic pool and adaptive router.
    """
    if hasattr(pool_obj, "get_stats"):
        router_stats = pool_obj.get_stats()
        if isinstance(router_stats, dict) and all(
            key in router_stats for key in ("safe_pool", "medium_pool", "trusted_pool")
        ):
            return {
                f"{pool_alias}.safe": router_stats["safe_pool"],
                f"{pool_alias}.medium": router_stats["medium_pool"],
                f"{pool_alias}.trusted": router_stats["trusted_pool"],
                f"{pool_alias}.router": {
                    "meta_type": "router",
                    "thread_pool": {
                        "pool_generation": router_stats.get("safe_pool", {}).get("thread_pool", {}).get("pool_generation", 0),
                        "max_workers": (
                            router_stats.get("safe_pool", {}).get("thread_pool", {}).get("max_workers", 0)
                            + router_stats.get("medium_pool", {}).get("thread_pool", {}).get("max_workers", 0)
                            + router_stats.get("trusted_pool", {}).get("thread_pool", {}).get("max_workers", 0)
                        ),
                        "active_tasks": {},
                        "completed_tasks": (
                            router_stats.get("safe_pool", {}).get("thread_pool", {}).get("completed_tasks", 0)
                            + router_stats.get("medium_pool", {}).get("thread_pool", {}).get("completed_tasks", 0)
                            + router_stats.get("trusted_pool", {}).get("thread_pool", {}).get("completed_tasks", 0)
                        ),
                        "failed_tasks": (
                            router_stats.get("safe_pool", {}).get("thread_pool", {}).get("failed_tasks", 0)
                            + router_stats.get("medium_pool", {}).get("thread_pool", {}).get("failed_tasks", 0)
                            + router_stats.get("trusted_pool", {}).get("thread_pool", {}).get("failed_tasks", 0)
                        ),
                        "rejected_tasks": (
                            router_stats.get("safe_pool", {}).get("thread_pool", {}).get("rejected_tasks", 0)
                            + router_stats.get("medium_pool", {}).get("thread_pool", {}).get("rejected_tasks", 0)
                            + router_stats.get("trusted_pool", {}).get("thread_pool", {}).get("rejected_tasks", 0)
                        ),
                        "max_concurrent_tasks": (
                            router_stats.get("safe_pool", {}).get("thread_pool", {}).get("max_concurrent_tasks", 0)
                            + router_stats.get("medium_pool", {}).get("thread_pool", {}).get("max_concurrent_tasks", 0)
                            + router_stats.get("trusted_pool", {}).get("thread_pool", {}).get("max_concurrent_tasks", 0)
                        ),
                        "queue_size": (
                            router_stats.get("safe_pool", {}).get("thread_pool", {}).get("queue_size", 0)
                            + router_stats.get("medium_pool", {}).get("thread_pool", {}).get("queue_size", 0)
                            + router_stats.get("trusted_pool", {}).get("thread_pool", {}).get("queue_size", 0)
                        ),
                        "pool_utilization": (
                            (
                                router_stats.get("safe_pool", {}).get("thread_pool", {}).get("pool_utilization", 0.0)
                                + router_stats.get("medium_pool", {}).get("thread_pool", {}).get("pool_utilization", 0.0)
                                + router_stats.get("trusted_pool", {}).get("thread_pool", {}).get("pool_utilization", 0.0)
                            ) / 3.0
                        ),
                    },
                    "execution_time": {
                        "avg_execution_time": 0,
                        "min_execution_time": 0,
                        "max_execution_time": 0,
                        "total_execution_time": 0,
                    },
                    "history": [],
                    "router": {
                        "routing_thresholds": router_stats.get("routing_thresholds", {}),
                        "owners_count": len(router_stats.get("owners", {})),
                        "owners": router_stats.get("owners", {}),
                    },
                },
            }
    if hasattr(pool_obj, "get_monitoring_stats"):
        return {pool_alias: pool_obj.get_monitoring_stats()}
    return {}


def create_api_ns(instance: xray):
    global _instance
    _instance = instance
    return _api_ns


@_api_ns.route("/database/info")
class database_info(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Database Information card data (same as Database tab)."""
        def _handler():
            try:
                return jsonify(_instance.get_db_info())
            except Exception as exc:
                return jsonify({"error": str(exc)}), 500

        return _record_api_call("database_info", _handler)


@_api_ns.route("/database/pool/stats")
class pool_stats(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить текущую статистику пула соединений"""
        def _handler():
            stats = _instance.get_pool_stats()
            if stats:
                return jsonify(stats.__dict__)
            return jsonify({"error": "Pool monitoring not available"}), 503

        return _record_api_call("pool_stats", _handler)


@_api_ns.route("/database/pool/history")
class pool_history(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить историю статистики пула"""
        def _handler():
            minutes = request.args.get("minutes", 60, type=int)
            history = _instance.get_pool_history(minutes)

            return jsonify(
                {
                    "history": [
                        {
                            "active_connections": stat.active_connections,
                            "idle_connections": stat.idle_connections,
                            "total_connections": stat.total_connections,
                            "overflow": stat.overflow,
                            "timestamp": stat.timestamp,
                            "usage_percent": round(
                                (stat.active_connections / stat.pool_size) * 100, 1
                            ),
                        }
                        for stat in history
                    ],
                    "period_minutes": minutes,
                    "total_records": len(history),
                }
            )

        return _record_api_call("pool_history", _handler)


@_api_ns.route("/database/pool/health")
class pool_health(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить показатели здоровья пула"""
        def _handler():
            stats = _instance.get_pool_stats()
            if not stats:
                return jsonify({"error": "Pool monitoring not available"}), 503

            health_score = 100
            warnings = []

            if stats.pool_usage_percent > 90:
                health_score -= 80
                warnings.append("Critical pool usage")
            elif stats.pool_usage_percent > 80:
                health_score -= 50
                warnings.append("High pool usage")

            recommendations = []
            if stats.pool_usage_percent > 85:
                recommendations.append("Consider increasing pool size")

            health_score = max(health_score, 0)
            writeSystemStatsMetric(_PLUGIN, "db_pool_health_score", health_score, prop_type=PropertyType.Integer)

            return jsonify(
                {
                    "health_score": health_score,
                    'status': 'healthy' if health_score > 80 else 'warning' if health_score > 50 else 'critical',
                    "warnings": warnings,
                    "recommendations": recommendations,
                }
            )

        return _record_api_call("pool_health", _handler)

@_api_ns.route("/resources/stats")
class resources_stats(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Current osysHome process resource snapshot for realtime UI."""
        # flask-restx + custom JSON representation: возвращать dict / (dict, code), не jsonify()
        stats = _instance.get_resource_stats()
        if stats is None:
            return {"available": False, "error": "Resource monitoring not available"}, 503
        payload = stats.to_dict() if hasattr(stats, "to_dict") else dict(stats.__dict__)
        return payload


@_api_ns.route("/resources/history")
class resources_history(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """In-memory resource history for realtime charts."""
        minutes = request.args.get("minutes", 30, type=int)
        history = _instance.get_resource_history(minutes)
        monitor = getattr(_instance, "_resource_monitor", None)
        return {
            "history": [
                (stat.to_dict() if hasattr(stat, "to_dict") else dict(stat.__dict__))
                for stat in history
            ],
            "period_minutes": minutes,
            "total_records": len(history),
            "available": bool(monitor and monitor.available),
        }


@_api_ns.route("/analytics/stats")
class analytics_stats(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить сырые данные для аналитики"""
        def _handler():
            from app.core.main.ObjectsStorage import objects_storage

            stats = objects_storage.getAdvancedStats()

            return jsonify({
                "stats": stats,
                "timestamp": time.time()
            })

        return _record_api_call("analytics", _handler)

@_api_ns.route("/thread_pools/stats")
class thread_pools_stats(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить статистику всех пулов потоков"""
        def _handler():
            from app.core.main.ObjectManager import _poolLinkedProperty, _batch_writer
            from app.core.lib.common import _poolSay, _poolPlaysound
            data = {}
            data.update(_collect_thread_pool_stats(_poolLinkedProperty, "linked_pool"))
            data.update(_collect_thread_pool_stats(_poolSay, "say_pool"))
            data.update(_collect_thread_pool_stats(_poolPlaysound, "playsound_pool"))
            data["batch_writer"] = _batch_writer.get_stats()
            bw = data.get("batch_writer") or {}
            writeSystemStatsMetric(
                _PLUGIN,
                "batch_writer_queue_size",
                int(bw.get("queue_size") or 0),
                prop_type=PropertyType.Integer,
            )
            return jsonify(data)

        return _record_api_call("thread_pools", _handler)

@_api_ns.route("/thread_pools/history")
class thread_pools_history(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить историю пулов потоков"""
        def _handler():
            from app.core.main.ObjectManager import _poolLinkedProperty, _batch_writer
            from app.core.lib.common import _poolSay, _poolPlaysound
            data = {}
            data.update(_collect_thread_pool_stats(_poolLinkedProperty, "linked_pool"))
            data.update(_collect_thread_pool_stats(_poolSay, "say_pool"))
            data.update(_collect_thread_pool_stats(_poolPlaysound, "playsound_pool"))
            data["batch_writer"] = _batch_writer.get_stats()
            return jsonify(data)

        return _record_api_call("thread_pools_history", _handler)

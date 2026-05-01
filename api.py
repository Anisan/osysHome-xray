from flask import request, jsonify
from flask_restx import Namespace, Resource
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_admin_required
from plugins.xray import xray
import time

_api_ns = Namespace(name="Xray", description="XRay namespace", validate=True)

_instance: xray = None


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


@_api_ns.route("/database/pool/stats")
class pool_stats(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить текущую статистику пула соединений"""
        stats = _instance.get_pool_stats()
        if stats:
            return jsonify(stats.__dict__)
        return jsonify({"error": "Pool monitoring not available"}), 503


@_api_ns.route("/database/pool/history")
class pool_history(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить историю статистики пула"""
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


@_api_ns.route("/database/pool/health")
class pool_health(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить показатели здоровья пула"""
        stats = _instance.get_pool_stats()
        if not stats:
            return jsonify({"error": "Pool monitoring not available"}), 503

        health_score = 100
        warnings = []

        # Проверки здоровья
        if stats.pool_usage_percent > 90:
            health_score -= 80
            warnings.append("Critical pool usage")
        elif stats.pool_usage_percent > 80:
            health_score -= 50
            warnings.append("High pool usage")

        recommendations = []
        if stats.pool_usage_percent > 85:
            recommendations.append("Consider increasing pool size")

        return jsonify(
            {
                "health_score": max(health_score, 0),
                'status': 'healthy' if health_score > 80 else 'warning' if health_score > 50 else 'critical',
                "warnings": warnings,
                "recommendations": recommendations,
            }
        )

@_api_ns.route("/analytics/stats")
class analytics_stats(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить сырые данные для аналитики"""
        from app.core.main.ObjectsStorage import objects_storage

        stats = objects_storage.getAdvancedStats()

        # Возвращаем сырые данные без обработки
        return jsonify({
            "stats": stats,
            "timestamp": time.time()
        })

@_api_ns.route("/thread_pools/stats")
class thread_pools_stats(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить статистику всех пулов потоков"""
        from app.core.main.ObjectManager import _poolLinkedProperty, _batch_writer
        from app.core.lib.common import _poolSay, _poolPlaysound
        data = {}
        data.update(_collect_thread_pool_stats(_poolLinkedProperty, "linked_pool"))
        data.update(_collect_thread_pool_stats(_poolSay, "say_pool"))
        data.update(_collect_thread_pool_stats(_poolPlaysound, "playsound_pool"))
        data["batch_writer"] = _batch_writer.get_stats()
        return jsonify(data)

@_api_ns.route("/thread_pools/history")
class thread_pools_history(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить историю пулов потоков"""
        from app.core.main.ObjectManager import _poolLinkedProperty, _batch_writer
        from app.core.lib.common import _poolSay, _poolPlaysound
        data = {}
        data.update(_collect_thread_pool_stats(_poolLinkedProperty, "linked_pool"))
        data.update(_collect_thread_pool_stats(_poolSay, "say_pool"))
        data.update(_collect_thread_pool_stats(_poolPlaysound, "playsound_pool"))
        data["batch_writer"] = _batch_writer.get_stats()
        return jsonify(data)

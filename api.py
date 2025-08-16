from flask import request, jsonify
from flask_restx import Namespace, Resource
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_admin_required
from plugins.xray import xray
import time

_api_ns = Namespace(name="Xray", description="XRay namespace", validate=True)

_instance: xray = None


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
        from app.core.main.ObjectManager import _poolLinkedProperty, _poolSaveHistory
        from app.core.lib.common import _poolSay, _poolPlaysound
        data = {"linked_pool":_poolLinkedProperty.get_monitoring_stats(),
                "save_history_pool": _poolSaveHistory.get_monitoring_stats(),
                "say_pool": _poolSay.get_monitoring_stats(),
                "playsound_pool": _poolPlaysound.get_monitoring_stats()}
        return jsonify(data)

@_api_ns.route("/thread_pools/history")
class thread_pools_history(Resource):
    @api_key_required
    @handle_admin_required
    def get(self):
        """Получить историю пулов потоков"""
        from app.core.main.ObjectManager import _poolLinkedProperty, _poolSaveHistory
        from app.core.lib.common import _poolSay, _poolPlaysound
        data = {"linked_pool":_poolLinkedProperty.get_monitoring_stats(),
                "save_history_pool": _poolSaveHistory.get_monitoring_stats(),
                "say_pool": _poolSay.get_monitoring_stats(),
                "playsound_pool": _poolPlaysound.get_monitoring_stats()}
        return jsonify(data)

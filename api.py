import json
from flask import request, jsonify
from flask_restx import Namespace, Resource
from app.api.decorators import api_key_required
from app.authentication.handlers import handle_admin_required
from plugins.xray import xray

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

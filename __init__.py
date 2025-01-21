r"""
XRAY
"""
from sqlalchemy import delete, update
from app.database import row2dict, session_scope
from app.core.main.BasePlugin import BasePlugin
from flask import render_template, redirect
from app.core.main.PluginsHelper import plugins
from app.core.main.ObjectsStorage import objects_storage
from app.core.models.Plugins import Notify
from app.core.lib.constants import CategoryNotify
class xray(BasePlugin):

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "XRAY"
        self.version = '0.1'
        self.description = """Xray view system"""
        self.category = "System"
        self.author = "Eraser"
        self.actions = ["widget"]

    def initialization(self):
        pass

    def admin(self, request):
        tab = request.args.get("tab", "")
        op = request.args.get("op", None)
        notify = request.args.get("notify", None)
        
        if notify:
            if op == 'read':
                from app.core.lib.common import readNotify
                readNotify(notify)
            elif op == 'unread':
                with session_scope() as session:
                    sql = update(Notify).where(Notify.id == notify).values(read=False)
                    session.execute(sql)
                    session.commit()
            elif op == 'remove':
                with session_scope() as session:
                    sql = delete(Notify).where(Notify.id == notify)
                    session.execute(sql)
                    session.commit()
            return redirect("xray?tab=notifications")
        
        if op == 'clear_cache':
            from app.extensions import cache
            cache.clear()
            return redirect("xray?tab=cache")
        
        if op == 'clear_storage':
            objects_storage.clear()
            return redirect("xray?tab=objects")
        
        if op == 'read_all':
            with session_scope() as session:
                sql = update(Notify).values(read=True)
                session.execute(sql)
                session.commit()
            return redirect("xray?tab=notifications")
        
        if op == 'clear_notifications':
            with session_scope() as session:
                sql = delete(Notify)
                session.execute(sql)
                session.commit()
            return redirect("xray?tab=notifications")

        if op == "remove":
            object = request.args.get("object", None)
            if object:
                objects_storage.delObjectByName(object)
            return redirect("xray?tab=objects")

        cycle = request.args.get("cycle", None)
        if cycle:
            if cycle in plugins:
                plugin = plugins[cycle]
                if op == 'restart':
                    plugin['instance'].stop_cycle()
                    plugin['instance'].start_cycle()
                if op == 'start':
                    plugin['instance'].start_cycle()
                if op == 'stop':
                    plugin['instance'].stop_cycle()
                    
            return redirect("xray?tab=")

        if tab == "cache":
            from app.extensions import cache

            values = {}
            for k in cache.cache._cache:
                values[k] = cache.get(k)
            content = {
                "count": len(values),
                "cache": values,
                "tab": tab,
            }
            return render_template("xray_cache.html", **content)
        elif tab == "objects":
            content = {
                "objects": objects_storage.getStats(),
                "tab": tab,
            }
            return render_template("xray_objects.html", **content)
        elif tab == "props":
            props = {}
            stats = objects_storage.getAdvancedStats()
            for key,obj in stats.items():
                for name,prop in obj['stat_properties'].items():
                    if prop['last_write']:
                        props[key + "." + name] = prop
                        props[key + "." + name]['object_id'] = obj['id']
                        props[key + "." + name]['description'] = obj['description'] if obj['description'] else obj['name']
            content = {
                "props": props,
                "tab": tab,
            }
            return render_template("xray_props.html", **content)
        elif tab == "methods":
            props = {}
            stats = objects_storage.getAdvancedStats()
            for key,obj in stats.items():
                for name,prop in obj['stat_methods'].items():
                    if prop['last_executed']:
                        props[key + "." + name] = prop
                        props[key + "." + name]['object_id'] = obj['id']
                        props[key + "." + name]['description'] = obj['description'] if obj['description'] else obj['name']
            content = {
                "methods": props,
                "tab": tab,
            }
            return render_template("xray_methods.html", **content)
        elif tab == "notifications":
            notifications = Notify.query.order_by(Notify.created).all()
            res = []
            for rec in notifications:
                item = row2dict(rec)
                item['color'] = "danger"
                if rec.category == CategoryNotify.Debug:
                    item['color'] = "secondary"
                elif rec.category == CategoryNotify.Warning:
                    item['color'] = "warning"
                elif rec.category == CategoryNotify.Info:
                    item['color'] = "success"
                res.append(item)
            content = {
                "notifications": res,
                "tab": tab,
            }
            return render_template("xray_notifications.html", **content)
        else:
            values = {}
            for name,plugin in plugins.items():

                if 'cycle' in plugin['instance'].actions:
                    values[name] = {
                        "active": plugin['instance'].is_alive(),
                        "last_active": plugin['instance'].dtUpdated
                    } 
            content = {
                "count": len(values),
                "cycles": values,
                "tab": tab,
            }
            return render_template("xray_cycles.html", **content)
            
    def widget(self):
        content = {}
        services_count = 0
        service_work = 0
        for name,plugin in plugins.items():
            if 'cycle' in plugin['instance'].actions:
                services_count = services_count + 1
                if plugin['instance'].is_alive():
                    service_work = service_work + 1
        content['services'] = {"count": services_count, "alive": service_work, "stopped": services_count - service_work}
        from app.extensions import cache
        content['cache_count'] = len(cache.cache._cache)
        content['objects'] = len(objects_storage.items())
        return render_template("widget_xray.html",**content)

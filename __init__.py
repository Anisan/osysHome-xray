r"""
XRAY
"""

from app.core.main.BasePlugin import BasePlugin
from flask import render_template, redirect
from app.core.main.PluginsHelper import plugins
from app.core.main.ObjectsStorage import objects_storage
class xray(BasePlugin):

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "XRAY"
        self.version = '0.1'
        self.description = """Xray view system"""
        self.category = "System"
        self.author = "Eraser"

    def initialization(self):
        pass

    def admin(self, request):
        tab = request.args.get("tab", "")
        op = request.args.get("op", None)
        
        if op == 'clear_cache':
            from app.extensions import cache
            cache.clear()
            return redirect("xray?tab=cache")
        
        if op == 'clear_storage':
            objects_storage.clear()
            return redirect("xray?tab=objects")
        
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
            

r"""
XRAY
"""
import json
import os
from app.core.utils import CustomJSONEncoder
import sys
import subprocess
import platform
import pkg_resources
from sqlalchemy import delete, update, text
from app.database import row2dict, session_scope, db, convert_utc_to_local
from app.core.main.BasePlugin import BasePlugin
from flask import render_template, redirect
from app.core.main.PluginsHelper import plugins
from app.core.main.ObjectsStorage import objects_storage
from app.core.models.Plugins import Notify
from app.core.lib.constants import CategoryNotify
from app.api import api
from plugins.xray.utils.pool_monitor import DatabasePoolMonitor
from app.core.lib.object import updateProperty

class xray(BasePlugin):

    def __init__(self, app):
        super().__init__(app, __name__)
        self.title = "XRAY"
        self.version = '0.1'
        self.description = """Xray view system"""
        self.category = "System"
        self.author = "Eraser"
        self.actions = ["widget"]

        from plugins.xray.api import create_api_ns
        api_ns = create_api_ns(self)
        api.add_namespace(api_ns, path="/xray")

    def initialization(self):
        from app.database import engine
        self._pool_monitor = DatabasePoolMonitor(engine, self.logger)
        interval = 5
        from app.configuration import Config
        if Config.DEBUG:
            interval = 1
        self._pool_monitor.start_monitoring(interval)

    def get_pool_stats(self):
        """API для получения текущей статистики пула"""
        if self._pool_monitor:
            return self._pool_monitor.get_pool_stats()
        return None

    def get_pool_history(self, minutes: int = 60):
        """API для получения истории статистики пула"""
        if self._pool_monitor:
            return self._pool_monitor.get_stats_history(minutes)
        return []

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
                updateProperty("SystemVar.UnreadNotify", False, self.name)
            return redirect("xray?tab=notifications")

        if op == 'clear_notifications':
            with session_scope() as session:
                sql = delete(Notify)
                session.execute(sql)
                session.commit()
                updateProperty("SystemVar.UnreadNotify", False, self.name)
            return redirect("xray?tab=notifications")

        table_name = request.args.get("table", None)
        if table_name:
            table_name = f'"{table_name}"' if db.engine.dialect.name == 'postgresql' else f'`{table_name}`'
        if op == 'clear_table':
            with session_scope() as session:
                try:
                    query = text(f"DELETE FROM {table_name};")
                    session.execute(query)
                    session.commit()
                    self.logger.info(f"✅ Table {table_name} cleared")
                except Exception as e:
                    session.rollback()
                    self.logger.error(f"❌ Error clear table {table_name}: {e}")
            return redirect("xray?tab=db")
        if op == 'drop_table':
            with session_scope() as session:
                try:
                    query = text(f"DROP TABLE {table_name};")
                    session.execute(query)
                    session.commit()
                    self.logger.info(f"✅ Table {table_name} droped")
                except Exception as e:
                    session.rollback()
                    self.logger.error(f"❌ Error drop table {table_name}: {e}")
            return redirect("xray?tab=db")

        if op == "remove":
            object = request.args.get("object", None)
            if object:
                objects_storage.remove_object(object)
            return redirect("xray?tab=objects")

        if op == "install_package":
            package = request.args.get("package", None)
            if not package:
                return redirect("xray?tab=system")

            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', package], check=True)
                self.logger.info(f"Installed package '{package}'!")
            except subprocess.CalledProcessError as e:
                self.logger.exception(e)

            return redirect("xray?tab=system")

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
            keys = []
            cache_type = cache.app.config.get('CACHE_TYPE', 'unknown')
            if cache_type == 'redis':
                key_prefix = cache.app.config.get('CACHE_KEY_PREFIX', '')
                if key_prefix:
                    pattern = f"{key_prefix}*"
                else:
                    pattern = "*"
                redis_client = cache.cache._write_client
                for key in redis_client.scan_iter(match=pattern):
                    # Удаляем префикс
                    key = key[len(key_prefix):]
                    keys.append(key.decode('utf-8'))

            elif cache_type == 'simple':
                keys = cache.cache._cache

            values = {}
            for k in keys:
                values[k] = json.dumps(cache.get(k), cls=CustomJSONEncoder, ensure_ascii=False)
            content = {
                "count": len(values),
                "cache_type": cache_type,
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
                        props[key + "." + name]['last_write'] = convert_utc_to_local(prop['last_write'])
                        props[key + "." + name]['last_read'] = convert_utc_to_local(prop['last_read'])
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
                        props[key + "." + name]['last_executed'] = convert_utc_to_local(prop['last_executed'])
                        props[key + "." + name]['exec_time'] = prop['exec_time']

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
        elif tab == "db":
            tables = self.__get_table_info()
            db_info = self.__get_db_info()
            content = {
                "tables": tables,
                "db_info": db_info,
                "tab": tab,
            }
            return render_template("xray_db.html", **content)
        elif tab == "thread_pools":
            content = {"tab": tab}
            return render_template("xray_thread_pools.html", **content)
        elif tab == "threads":
            data = []
            import threading
            threads = threading.enumerate()
            for thread in threads:
                data.append({
                    'name': thread.name,
                    'id': thread.ident,
                    'alive': thread.is_alive(),
                    'daemon': thread.daemon
                })
            content = {
                "threads": data,
                "tab": tab,
            }
            return render_template("xray_threads.html", **content)
        elif tab == "cleaner":
            stats = objects_storage.getCleanerStat()
            content = {
                "stats": stats,
                "tab": tab,
            }
            return render_template("xray_cleaner.html", **content)
        elif tab == "system":
            packs = self.get_installed_packages()
            content = {
                'packages': packs,
                'python': {
                    'info': sys.version,
                    'version': platform.python_version(),
                    'exec': sys.executable,
                    'path': sys.prefix
                },
                'flask': {
                    'version': pkg_resources.get_distribution("flask").version if 'flask' in {pkg.key for pkg in pkg_resources.working_set} else 'Not install',
                },
                'venv': {
                    'active': True if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) else False,
                    'path': sys.prefix
                },
                'tab': tab,
            }
            return render_template("xray_system.html", **content)
        elif tab == "analytics":
            content = {
                "tab": tab,
            }
            return render_template("xray_analytics.html", **content)
        else:
            values = {}
            for name,plugin in plugins.items():

                if 'cycle' in plugin['instance'].actions:
                    values[name] = {
                        "active": plugin['instance'].is_alive(),
                        "last_active": convert_utc_to_local(plugin['instance'].dtUpdated)
                    }
            content = {
                "count": len(values),
                "cycles": values,
                "tab": tab,
            }
            return render_template("xray_cycles.html", **content)

    def get_installed_packages(self):
        try:
            packages = []
            # for dist in pkg_resources.working_set:
            #     packages.append({'name': dist.project_name, 'version': dist.version})
            # packages = sorted(packages, key=lambda x: x["name"])
            result = subprocess.run([sys.executable, '-m', 'pip', 'list', '--format=freeze'], capture_output=True, text=True)
            packages = []
            for line in result.stdout.split('\n'):
                if line.strip():
                    name, version = line.split('==') if '==' in line else (line.strip(), '?')
                    packages.append({'name': name, 'version': version})
            return packages
        except Exception as e:
            self.logger.exception(e)
            return []

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
        content['objects'] = len(objects_storage.items())
        return render_template("widget_xray.html",**content)

    def __get_table_info(self):
        """
        Получает список таблиц с количеством строк и размером таблиц.
        Работает для PostgreSQL, MySQL и SQLite.
        """
        engine = db.engine
        tables = []

        # Получаем все таблицы, определённые в SQLAlchemy
        sqlalchemy_tables = {}
        for class_name, model in db.Model.registry._class_registry.items():
            if hasattr(model, '__tablename__') and hasattr(model, '__table__'):
                table_name = model.__tablename__
                sqlalchemy_tables[table_name] = model.__module__.split(".")[1]

        def format_size(size_bytes):
            """
            Преобразует размер в байтах в удобочитаемый формат (например, "2.5 MB", "10 KB").
            """
            if size_bytes == 0:
                return "0 B"

            size_name = ("B", "KB", "MB", "GB", "TB")
            i = 0
            while size_bytes >= 1024 and i < len(size_name) - 1:
                size_bytes /= 1024
                i += 1
            return f"{size_bytes:.2f} {size_name[i]}"

        if engine.dialect.name == 'postgresql':
            # Для PostgreSQL используем pg_total_relation_size для получения размера в байтах
            query = text("""
                SELECT
                    table_name,
                    (xpath('/row/cnt/text()', xml_count))[1]::text::int AS row_count,
                    pg_total_relation_size(quote_ident(table_name)) AS size_bytes
                FROM (
                    SELECT
                        table_name,
                        query_to_xml(format('SELECT COUNT(*) AS cnt FROM %I', table_name), false, true, '') AS xml_count
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                ) AS subquery;
            """)
            result = db.session.execute(query)
            for row in result:
                table_name = row.table_name
                module = sqlalchemy_tables.get(table_name, 'Unknown')
                tables.append({
                    'table_name': table_name,
                    'module': module,
                    'row_count': row.row_count,
                    'size': format_size(row.size_bytes)
                })

        elif engine.dialect.name == 'mysql':
            # Для MySQL используем information_schema.tables для получения размера в байтах
            query = text("""
                SELECT
                    table_name,
                    table_rows AS row_count,
                    (data_length + index_length) AS size_bytes
                FROM information_schema.tables
                WHERE table_schema = DATABASE();
            """)
            result = db.session.execute(query)
            for row in result:
                table_name = row.table_name
                module = sqlalchemy_tables.get(table_name, 'Unknown')
                tables.append({
                    'table_name': table_name,
                    'module': module,
                    'row_count': row.row_count,
                    'size': format_size(row.size_bytes)
                })

        elif engine.dialect.name == 'sqlite':
            # Для SQLite используем PRAGMA table_info и COUNT(*)
            query = text("SELECT name FROM sqlite_master WHERE type='table';")
            result = db.session.execute(query)
            for row in result:
                table_name = row.name
                module = sqlalchemy_tables.get(table_name, 'Unknown')
                count_query = text(f"SELECT COUNT(*) AS row_count FROM '{table_name}';")
                count_result = db.session.execute(count_query).scalar()
                size_query = text("SELECT page_count * page_size AS size_bytes FROM pragma_page_count(), pragma_page_size();")
                size_result = db.session.execute(size_query).scalar()
                tables.append({
                    'table_name': table_name,
                    'module': module,
                    'row_count': count_result,
                    'size': format_size(size_result)
                })

        else:
            raise NotImplementedError(f"Unsupported database dialect: {engine.dialect.name}")
        return tables

    def __get_db_info(self):
        """
        Получает информацию о подключенной СУБД: версия, размер, тип и другие параметры.
        Работает для PostgreSQL, MySQL и SQLite.
        """
        engine = db.engine
        dialect = engine.dialect.name
        db_info = {
            'type': dialect.upper(),
            'version': 'Unknown',
            'database_name': 'Unknown',
            'database_size': 'Unknown',
            'connection_string': str(engine.url).split('@')[-1] if '@' in str(engine.url) else str(engine.url).replace('sqlite:///', ''),
            'max_connections': 'Unknown',
            'active_connections': 'Unknown',
            'idle_connections': 'Unknown',
            'tables_count': 0,
            'indexes_count': 0,
            'views_count': 0,
            'connections_usage_percent': 0,
            'server_uptime': 'Unknown',
            'charset': 'Unknown',
            'collation': 'Unknown',
        }

        def format_size(size_bytes):
            """Преобразует размер в байтах в удобочитаемый формат."""
            if size_bytes == 0 or size_bytes is None:
                return "0 B"
            size_name = ("B", "KB", "MB", "GB", "TB")
            i = 0
            size = float(size_bytes)
            while size >= 1024 and i < len(size_name) - 1:
                size /= 1024
                i += 1
            return f"{size:.2f} {size_name[i]}"

        try:
            if dialect == 'postgresql':
                # Получаем версию PostgreSQL
                try:
                    version_query = text("SELECT version();")
                    result = db.session.execute(version_query).scalar()
                    db_info['version'] = result.split(',')[0] if result else 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get PostgreSQL version: %s", e)
                
                # Получаем имя базы данных
                try:
                    db_name_query = text("SELECT current_database();")
                    db_name = db.session.execute(db_name_query).scalar()
                    db_info['database_name'] = db_name if db_name else 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get database name: %s", e)
                
                # Получаем размер базы данных
                try:
                    size_query = text("SELECT pg_database_size(current_database());")
                    size_bytes = db.session.execute(size_query).scalar()
                    db_info['database_size'] = format_size(size_bytes) if size_bytes is not None else '0 B'
                except Exception as e:
                    self.logger.warning("Failed to get database size: %s", e)
                
                # Получаем информацию о подключениях
                try:
                    conn_query = text("""
                        SELECT 
                            setting::int as max_conn,
                            (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()) as active_conn,
                            (SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle') as idle_conn
                        FROM pg_settings WHERE name = 'max_connections';
                    """)
                    conn_result = db.session.execute(conn_query).fetchone()
                    if conn_result:
                        db_info['max_connections'] = conn_result.max_conn if conn_result.max_conn is not None else 0
                        db_info['active_connections'] = conn_result.active_conn if conn_result.active_conn is not None else 0
                        db_info['idle_connections'] = conn_result.idle_conn if conn_result.idle_conn is not None else 0
                    else:
                        # Альтернативный способ получения max_connections
                        try:
                            max_conn_query = text("SHOW max_connections;")
                            max_conn = db.session.execute(max_conn_query).scalar()
                            db_info['max_connections'] = int(max_conn) if max_conn else 0
                        except Exception:
                            pass
                        # Получаем активные подключения отдельно
                        try:
                            active_query = text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();")
                            db_info['active_connections'] = db.session.execute(active_query).scalar() or 0
                        except Exception:
                            pass
                        # Получаем idle подключения отдельно
                        try:
                            idle_query = text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND state = 'idle';")
                            db_info['idle_connections'] = db.session.execute(idle_query).scalar() or 0
                        except Exception:
                            pass
                except Exception as e:
                    self.logger.warning("Failed to get connection info: %s", e)
                
                # Количество таблиц
                try:
                    tables_query = text("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
                    """)
                    tables_count = db.session.execute(tables_query).scalar()
                    db_info['tables_count'] = tables_count if tables_count is not None else 0
                except Exception as e:
                    self.logger.warning("Failed to get tables count: %s", e)
                    # Альтернативный способ
                    try:
                        alt_tables_query = text("""
                            SELECT COUNT(*) 
                            FROM pg_tables 
                            WHERE schemaname = 'public';
                        """)
                        db_info['tables_count'] = db.session.execute(alt_tables_query).scalar() or 0
                    except Exception:
                        pass
                
                # Дополнительная статистика
                try:
                    # Количество индексов
                    indexes_query = text("""
                        SELECT COUNT(*) 
                        FROM pg_indexes 
                        WHERE schemaname = 'public';
                    """)
                    db_info['indexes_count'] = db.session.execute(indexes_query).scalar() or 0
                except Exception:
                    db_info['indexes_count'] = 0
                
                try:
                    # Количество представлений (views)
                    views_query = text("""
                        SELECT COUNT(*) 
                        FROM information_schema.views 
                        WHERE table_schema = 'public';
                    """)
                    db_info['views_count'] = db.session.execute(views_query).scalar() or 0
                except Exception:
                    db_info['views_count'] = 0
                
                try:
                    # Использование подключений в процентах
                    if db_info['max_connections'] and db_info['max_connections'] != 'Unknown' and db_info['max_connections'] != 'N/A':
                        total_conn = db_info['active_connections'] + db_info['idle_connections']
                        if isinstance(total_conn, int) and isinstance(db_info['max_connections'], int):
                            db_info['connections_usage_percent'] = round((total_conn / db_info['max_connections']) * 100, 1)
                        else:
                            db_info['connections_usage_percent'] = 0
                    else:
                        db_info['connections_usage_percent'] = 0
                except Exception:
                    db_info['connections_usage_percent'] = 0
                
                try:
                    # Время работы сервера
                    uptime_query = text("SELECT date_trunc('second', current_timestamp - pg_postmaster_start_time()) as uptime;")
                    uptime_result = db.session.execute(uptime_query).scalar()
                    if uptime_result:
                        # Конвертируем interval в строку
                        db_info['server_uptime'] = str(uptime_result)
                    else:
                        db_info['server_uptime'] = 'Unknown'
                except Exception:
                    db_info['server_uptime'] = 'Unknown'

            elif dialect == 'mysql':
                # Получаем версию MySQL
                try:
                    version_query = text("SELECT VERSION();")
                    version = db.session.execute(version_query).scalar()
                    db_info['version'] = version if version else 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get MySQL version: %s", e)
                
                # Получаем имя базы данных
                try:
                    db_name_query = text("SELECT DATABASE();")
                    db_name = db.session.execute(db_name_query).scalar()
                    db_info['database_name'] = db_name if db_name else 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get database name: %s", e)
                
                # Получаем размер базы данных
                try:
                    size_query = text("""
                        SELECT 
                            SUM(data_length + index_length) AS size_bytes,
                            @@character_set_database AS charset,
                            @@collation_database AS collation
                        FROM information_schema.tables 
                        WHERE table_schema = DATABASE();
                    """)
                    size_result = db.session.execute(size_query).fetchone()
                    if size_result:
                        db_info['database_size'] = format_size(size_result.size_bytes) if size_result.size_bytes else '0 B'
                        db_info['charset'] = size_result.charset or 'Unknown'
                        db_info['collation'] = size_result.collation or 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get database size: %s", e)
                
                # Получаем информацию о подключениях
                try:
                    conn_query = text("""
                        SELECT 
                            @@max_connections as max_conn,
                            (SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE DB = DATABASE()) as active_conn,
                            (SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE DB = DATABASE() AND COMMAND = 'Sleep') as idle_conn
                    """)
                    conn_result = db.session.execute(conn_query).fetchone()
                    if conn_result:
                        db_info['max_connections'] = conn_result.max_conn if conn_result.max_conn is not None else 0
                        db_info['active_connections'] = conn_result.active_conn if conn_result.active_conn is not None else 0
                        db_info['idle_connections'] = conn_result.idle_conn if conn_result.idle_conn is not None else 0
                except Exception as e:
                    self.logger.warning("Failed to get connection info: %s", e)
                
                # Количество таблиц
                try:
                    tables_query = text("""
                        SELECT COUNT(*) 
                        FROM information_schema.tables 
                        WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE';
                    """)
                    tables_count = db.session.execute(tables_query).scalar()
                    db_info['tables_count'] = tables_count if tables_count is not None else 0
                except Exception as e:
                    self.logger.warning("Failed to get tables count: %s", e)

            elif dialect == 'sqlite':
                # Версия SQLite
                try:
                    version_query = text("SELECT sqlite_version();")
                    sqlite_version = db.session.execute(version_query).scalar()
                    db_info['version'] = f"SQLite {sqlite_version}" if sqlite_version else 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get SQLite version: %s", e)
                
                # Путь к базе данных
                try:
                    db_path = str(engine.url).replace('sqlite:///', '')
                    db_name = db_path.split('/')[-1] if '/' in db_path else db_path.split('\\')[-1]
                    db_info['database_name'] = db_name if db_name else 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get database name: %s", e)
                
                # Получаем размер файла БД
                try:
                    db_path = str(engine.url).replace('sqlite:///', '')
                    if os.path.exists(db_path):
                        size_bytes = os.path.getsize(db_path)
                        db_info['database_size'] = format_size(size_bytes)
                    else:
                        db_info['database_size'] = 'Unknown'
                except Exception as e:
                    self.logger.warning("Failed to get database size: %s", e)
                
                # Количество таблиц
                try:
                    tables_query = text("SELECT COUNT(*) FROM sqlite_master WHERE type='table';")
                    tables_count = db.session.execute(tables_query).scalar()
                    db_info['tables_count'] = tables_count if tables_count is not None else 0
                except Exception as e:
                    self.logger.warning("Failed to get tables count: %s", e)
                
                # SQLite не имеет понятия max_connections в том же смысле
                db_info['max_connections'] = 'N/A'
                db_info['active_connections'] = 'N/A'
                db_info['idle_connections'] = 'N/A'

        except Exception as e:
            self.logger.exception("Error getting database info: %s", e)
            db_info['error'] = str(e)
        
        # Убеждаемся, что все обязательные поля заполнены
        if not db_info['type'] or db_info['type'] == 'UNKNOWN':
            db_info['type'] = engine.dialect.name.upper() if engine.dialect.name else 'UNKNOWN'
        
        # Обрабатываем числовые значения
        if db_info['tables_count'] is None or (isinstance(db_info['tables_count'], str) and db_info['tables_count'] in ['Unknown', 'N/A']):
            db_info['tables_count'] = 0
        
        if db_info['indexes_count'] is None:
            db_info['indexes_count'] = 0
            
        if db_info['views_count'] is None:
            db_info['views_count'] = 0
        
        if db_info['connections_usage_percent'] is None:
            db_info['connections_usage_percent'] = 0
        
        # Для подключений: если значение 'Unknown' или None, устанавливаем 0 (кроме SQLite, где 'N/A' нормально)
        if db_info['active_connections'] == 'Unknown' or db_info['active_connections'] is None:
            if dialect != 'sqlite':
                db_info['active_connections'] = 0
        
        if db_info['idle_connections'] == 'Unknown' or db_info['idle_connections'] is None:
            if dialect != 'sqlite':
                db_info['idle_connections'] = 0

        return db_info

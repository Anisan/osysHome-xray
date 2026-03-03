# xray - System Diagnostics Module

![xray Icon](static/xray.png)

System diagnostics and monitoring tool for viewing system information, database statistics, cache status, and notifications.

## Description

The `xray` module provides comprehensive system diagnostics and monitoring capabilities for the osysHome platform. It enables viewing system information, database pool statistics, cache management, object storage status, and notification management.

## Main Features

- ✅ **System Information**: View system details, Python version, platform info
- ✅ **Database Pool Monitoring**: Monitor database connection pool statistics
- ✅ **Cache Management**: View and clear cache
- ✅ **Object Storage**: View objects in memory storage
- ✅ **Notification Management**: Manage system notifications
- ✅ **Module Information**: View installed modules and versions
- ✅ **Widget Support**: Dashboard widget

## Admin Panel

The module provides a comprehensive admin interface with multiple tabs:

### System Tab
- Python version
- Platform information
- Installed packages
- System resources

### Database Tab
- Connection pool statistics
- Pool history
- Active connections
- Pool size information

### Cache Tab
- Cache statistics
- Clear cache functionality
- Cache size information

### Objects Tab
- Objects in memory storage
- Clear storage functionality
- Object count

### Notifications Tab
- View notifications
- Mark as read/unread
- Delete notifications
- Clear all notifications

### Modules Tab
- Installed modules list
- Module versions
- Module information

## API

The module provides RESTful API endpoints:
- **GET /api/xray/...**: System diagnostics API

## Usage

### Viewing System Information

1. Navigate to xray module
2. Select desired tab
3. View system information
4. Perform maintenance operations

## Technical Details

- **Pool Monitoring**: Real-time database pool monitoring
- **Cache**: Flask-Caching integration
- **Storage**: ObjectsStorage integration
- **Notifications**: System notification management

## Version

Current version: **0.1**

## Category

System

## Actions

The module provides the following actions:
- `widget` - Dashboard widget

## Requirements

- Flask
- SQLAlchemy
- osysHome core system

## Author

Eraser

## License

See the main osysHome project license


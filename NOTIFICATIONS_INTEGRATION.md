# Notifications Integration Guide (WebSocket + REST)

This document describes how to integrate the notifications system from the frontend.

Base API:
- REST: `https://api.dandelionz.com.ng`
- WebSocket: `wss://api.dandelionz.com.ng`

Auth:
- REST: `Authorization: Bearer <access_token>`
- WebSocket: JWT is accepted either via:
  - Query param: `?token=<access_token>`
  - Header: `Authorization: Bearer <access_token>`

---
**WebSocket**
Endpoint:
- `wss://api.dandelionz.com.ng/ws/notifications/?token=<access_token>`

Connection flow:
- On connect, server sends:
```json
{
  "type": "connection_established",
  "timestamp": "2026-02-06T10:00:00.000Z",
  "user_id": "123",
  "message": "Connected to notification service"
}
```

Server push message (realtime notification):
```json
{
  "type": "notification",
  "data": {
    "id": "d8fbeef1-....",
    "title": "Order Shipped",
    "message": "Order #1234 has been shipped",
    "description": "",
    "priority": "normal",
    "category": "order",
    "action_url": "/orders/1234",
    "action_text": "View Order",
    "is_read": false,
    "is_draft": false,
    "metadata": {},
    "created_at": "2026-02-06T10:00:00.000Z",
    "scheduled_for": null,
    "notification_type": {
      "name": "order_update",
      "display_name": "Order Update",
      "icon": "truck",
      "color": "#0EA5E9"
    }
  },
  "timestamp": "2026-02-06T10:00:00.000Z"
}
```

Heartbeat:
```json
{
  "type": "heartbeat",
  "timestamp": "2026-02-06T10:00:30.000Z"
}
```

Client -> Server messages:

1) Ping
```json
{ "type": "ping" }
```
Response:
```json
{ "type": "pong", "timestamp": "..." }
```

2) Mark as read
```json
{ "type": "mark_as_read", "notification_id": "uuid" }
```
Response:
```json
{ "type": "notification_read", "notification_id": "uuid", "success": true }
```

3) Mark as unread
```json
{ "type": "mark_as_unread", "notification_id": "uuid" }
```
Response:
```json
{ "type": "notification_unread", "notification_id": "uuid", "success": true }
```

4) Fetch unread
```json
{ "type": "fetch_unread", "limit": 20 }
```
Response:
```json
{
  "type": "unread_notifications",
  "count": 2,
  "notifications": [ ... ]
}
```

5) Fetch recent
```json
{ "type": "fetch_recent", "limit": 20 }
```
Response:
```json
{
  "type": "recent_notifications",
  "count": 20,
  "notifications": [ ... ]
}
```

6) Archive
```json
{ "type": "archive", "notification_id": "uuid" }
```
Response:
```json
{ "type": "notification_archived", "notification_id": "uuid" }
```

Errors:
```json
{ "type": "error", "message": "Notification not found or unauthorized" }
```

Notes:
- Realtime delivery happens via WebSocket when notifications are created.
- Draft notifications do not emit realtime messages until published.

---
**REST API**

All REST endpoints require `Authorization: Bearer <access_token>`.

**1) User notifications (unified)**

Base path:
- `GET /user/notifications/` -> list current user notifications (excluding drafts)
- `GET /user/notifications/{id}/` -> detail
- `DELETE /user/notifications/{id}/` -> soft delete

Additional actions:
- `GET /user/notifications/unread_count/`
- `GET /user/notifications/stats/`
- `POST /user/notifications/mark_as_read/`
- `POST /user/notifications/mark_all_as_read/`
- `POST /user/notifications/{id}/archive/`
- `POST /user/notifications/{id}/unarchive/`
- `POST /user/notifications/bulk_delete/`

Payloads:
Mark as read:
```json
{ "notification_id": "uuid" }
```

Mark all as read:
```json
{}
```

Bulk delete:
```json
{ "notification_ids": ["uuid1", "uuid2"] }
```

**2) Notification types**
- `GET /user/notifications/types/`
- `GET /user/notifications/types/{id}/`

**3) Preferences**
- `GET /user/notifications/preferences/`
- `PUT /user/notifications/preferences/`
- `POST /user/notifications/preferences/enable-quiet-hours/`
- `POST /user/notifications/preferences/disable-quiet-hours/`
- `POST /user/notifications/preferences/enable-dnd/`
- `POST /user/notifications/preferences/disable-dnd/`

Example update preferences:
```json
{
  "websocket_enabled": true,
  "email_enabled": true,
  "push_enabled": false,
  "quiet_hours_enabled": true,
  "quiet_hours_start": "22:00",
  "quiet_hours_end": "07:00"
}
```

**4) Vendor-specific list**
- `GET /user/vendor/notifications/` -> same as user list, filtered to vendor user

**5) Delivery agent list**
- `GET /user/delivery/notifications/`

---
**Admin Notifications (Create, List, Drafts, Publish)**

Create or broadcast:
- `POST /user/admin/notifications/`

List:
- `GET /user/admin/notifications/`
- Optional filter: `?is_draft=true|false`

Publish draft:
- `POST /user/admin/notifications/publish/{notification_id}/`

Create payload (targeted to a single user):
```json
{
  "user_uuid": "31371b24-d533-42ba-a664-26ddce48a9d5",
  "title": "KYC Approved",
  "message": "Your KYC has been approved.",
  "priority": "normal",
  "category": "vendor_approval",
  "notification_type": "4f6a... (UUID of NotificationType)",
  "action_url": "/vendor/kyc",
  "action_text": "View",
  "metadata": { "source": "admin" },
  "is_draft": false,
  "scheduled_for": null,
  "send_websocket": true,
  "send_email": false,
  "send_push": false
}
```

Create payload (broadcast to group):
```json
{
  "recipient_group": "vendor",
  "title": "System Maintenance",
  "message": "We will be down for maintenance at 12:00 AM.",
  "priority": "high",
  "category": "system",
  "is_draft": false,
  "scheduled_for": null,
  "send_websocket": true
}
```

Draft payload:
```json
{
  "recipient_group": "vendor",
  "title": "Upcoming Feature",
  "message": "We are launching a new feature next week.",
  "is_draft": true
}
```
To publish a draft:
```
POST /user/admin/notifications/publish/<notification_id>/
```

Scheduled payload:
```json
{
  "recipient_group": "vendor",
  "title": "Payout Notice",
  "message": "Payouts will be processed tonight.",
  "scheduled_for": "2026-02-06T23:00:00Z"
}
```

Notes:
- Drafts do not appear in user/vendor REST lists until published.
- Scheduled notifications are queued via Celery and sent at `scheduled_for`.
- For realtime delivery, `send_websocket` should be `true`.

---
**Common Response Shape (Admin Create)**
```json
{
  "success": true,
  "data": { ...notification fields... },
  "message": "Notification created successfully",
  "count": 1
}
```

---
**Implementation Notes**
- Realtime updates are delivered via WebSocket to `user_<user_id>` group.
- Broadcasts are implemented by creating one notification per user, ensuring both REST and WebSocket consistency.
- If a user does not see a notification, verify:
  - Correct user UUID or recipient_group
  - WebSocket is connected with a valid token
  - Notification is not a draft

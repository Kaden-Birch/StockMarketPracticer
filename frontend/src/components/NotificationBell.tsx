import { useCallback, useEffect, useState } from "react";
import { api, NotificationView } from "../api";
import { useEvents } from "../hooks/useEvents";

export default function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState<NotificationView[]>([]);
  const [desktopOn, setDesktopOn] = useState(
    typeof Notification !== "undefined" && Notification.permission === "granted",
  );

  const refresh = useCallback(() => {
    api
      .notifications()
      .then((res) => {
        setUnread(res.unread_count);
        setItems(res.notifications);
      })
      .catch(() => undefined);
  }, []);
  useEffect(refresh, [refresh]);

  useEvents((type, data) => {
    if (type !== "notification") return;
    refresh();
    const d = data as { title?: string; body?: string };
    if (desktopOn && typeof Notification !== "undefined" && d.title) {
      try {
        new Notification(`AIPTP — ${d.title}`, { body: d.body ?? "" });
      } catch {
        /* some environments block constructor use */
      }
    }
  });

  async function enableDesktop() {
    if (typeof Notification === "undefined") return;
    const perm = await Notification.requestPermission();
    setDesktopOn(perm === "granted");
  }

  async function markAllRead() {
    await api.markNotificationsRead();
    refresh();
  }

  return (
    <div style={{ position: "relative" }}>
      <button className="ghost" onClick={() => setOpen(!open)} aria-label="Notifications"
        aria-expanded={open} style={{ width: "100%" }}>
        Inbox{unread > 0 ? ` (${unread})` : ""}
      </button>
      {open && (
        <div
          className="search-results"
          style={{ left: 0, bottom: "110%", top: "auto", minWidth: 360, maxHeight: 420 }}
          role="region"
          aria-label="Notification inbox"
        >
          <div style={{ display: "flex", gap: 8, padding: "8px 12px",
                        borderBottom: "1px solid var(--border)", alignItems: "center" }}>
            <strong style={{ flex: 1 }}>Notifications</strong>
            {!desktopOn && (
              <button className="ghost" onClick={enableDesktop} title="Show desktop notifications">
                Enable desktop
              </button>
            )}
            <button className="ghost" onClick={markAllRead}>Mark all read</button>
          </div>
          {items.length === 0 && (
            <div className="muted" style={{ padding: 12 }}>Nothing yet.</div>
          )}
          {items.map((n) => (
            <div key={n.id} style={{ cursor: "default", opacity: n.read ? 0.6 : 1 }}>
              <div><strong>{n.title}</strong></div>
              {n.body && <div className="muted">{n.body}</div>}
              <div className="muted" style={{ fontSize: 11 }}>
                {new Date(n.created_at + (n.created_at.endsWith("Z") ? "" : "Z")).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

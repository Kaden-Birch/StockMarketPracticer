import { useEffect, useRef } from "react";

/** Subscribes to the server's WebSocket event stream and invokes the handler
 * for each event. Reconnects with a simple backoff. */
export function useEvents(onEvent: (type: string, data: unknown) => void) {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    let retry = 1000;

    function connect() {
      const proto = window.location.protocol === "https:" ? "wss" : "ws";
      socket = new WebSocket(`${proto}://${window.location.host}/api/v1/ws`);
      socket.onmessage = (msg) => {
        try {
          const { type, data } = JSON.parse(msg.data);
          handlerRef.current(type, data);
        } catch {
          /* ignore malformed frames */
        }
      };
      socket.onopen = () => {
        retry = 1000;
      };
      socket.onclose = () => {
        if (!closed) {
          setTimeout(connect, retry);
          retry = Math.min(retry * 2, 15000);
        }
      };
    }
    connect();
    return () => {
      closed = true;
      socket?.close();
    };
  }, []);
}

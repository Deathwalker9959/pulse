import { useEffect, useRef, useState } from "react";

const RECONNECT_BASE_MS = 1_000;
const RECONNECT_MAX_MS = 30_000;
const RECONNECT_FACTOR = 1.5;

export function useWebSocket(url: string, onMessage: (data: string) => void): boolean {
  const [connected, setConnected] = useState(false);
  const onMessageRef = useRef(onMessage);
  useEffect(() => { onMessageRef.current = onMessage; });

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
    let delay = RECONNECT_BASE_MS;
    let cancelled = false;

    function connect() {
      socket = new WebSocket(url);

      socket.onopen = () => {
        if (cancelled) { socket?.close(); return; }
        setConnected(true);
        delay = RECONNECT_BASE_MS;
      };

      socket.onmessage = (event) => {
        if (!cancelled) onMessageRef.current(event.data as string);
      };

      socket.onerror = () => socket?.close();

      socket.onclose = () => {
        setConnected(false);
        if (!cancelled) {
          reconnectTimer = setTimeout(() => {
            delay = Math.min(delay * RECONNECT_FACTOR, RECONNECT_MAX_MS);
            connect();
          }, delay);
        }
      };
    }

    connect();

    return () => {
      cancelled = true;
      clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [url]);

  return connected;
}

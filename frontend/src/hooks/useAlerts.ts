import { useCallback, useEffect, useRef, useState } from "react";
import type { AnomalyEvent } from "../api/client";

const MAX_ALERTS = 100;
const BASE_DELAY = 1_000;
const MAX_DELAY = 30_000;

export function useAlerts() {
  const [alerts, setAlerts] = useState<AnomalyEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const delayRef = useRef(BASE_DELAY);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${protocol}://${window.location.host}/ws/alerts`);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      delayRef.current = BASE_DELAY;
    };

    ws.onmessage = (ev: MessageEvent<string>) => {
      try {
        const event = JSON.parse(ev.data) as AnomalyEvent;
        setAlerts(prev => [event, ...prev].slice(0, MAX_ALERTS));
      } catch {
        // Ignore malformed frames.
      }
    };

    ws.onclose = () => {
      setConnected(false);
      // Exponential backoff reconnect — capped at MAX_DELAY.
      retryRef.current = setTimeout(() => {
        delayRef.current = Math.min(delayRef.current * 2, MAX_DELAY);
        connect();
      }, delayRef.current);
    };

    ws.onerror = () => ws.close();
  }, []);

  useEffect(() => {
    connect();
    return () => {
      if (retryRef.current) clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { alerts, connected };
}

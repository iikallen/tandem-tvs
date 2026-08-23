import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, ApiError } from "../../shared/api";

export type RealtimeStatus = "connected" | "reconnecting" | "stopped";
const DELAYS = [1_000, 2_000, 5_000, 10_000, 30_000];

export function usePublicationRealtime(publicationId: string): RealtimeStatus {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<RealtimeStatus>("reconnecting");

  useEffect(() => {
    let disposed = false;
    let socket: WebSocket | undefined;
    let timer: number | undefined;
    let attempt = 0;

    const reconcile = async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ["publication", publicationId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["comments", publicationId],
        }),
        queryClient.invalidateQueries({
          queryKey: ["reactions", publicationId],
        }),
        queryClient.invalidateQueries({ queryKey: ["news"] }),
      ]);
    };
    const schedule = () => {
      if (disposed) return;
      setStatus("reconnecting");
      const base = DELAYS[Math.min(attempt, DELAYS.length - 1)];
      attempt += 1;
      timer = window.setTimeout(
        connect,
        Math.round(base * (0.8 + Math.random() * 0.4)),
      );
    };
    const connect = async () => {
      try {
        const { ticket } = await api.realtimeTicket(publicationId);
        if (disposed) return;
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        socket = new WebSocket(
          `${protocol}//${window.location.host}/ws/v1/publications/${encodeURIComponent(publicationId)}?ticket=${encodeURIComponent(ticket)}`,
        );
        socket.onopen = () => {
          attempt = 0;
          setStatus("connected");
          void reconcile();
        };
        socket.onmessage = (message) => {
          try {
            const event = JSON.parse(message.data as string) as {
              version?: number;
              publication_id?: string;
            };
            if (event.version === 1 && event.publication_id === publicationId)
              void reconcile();
          } catch {
            // A malformed hint is ignored; REST stays authoritative.
          }
        };
        socket.onclose = (event) => {
          if (disposed) return;
          if ([4401, 4403, 4404].includes(event.code)) setStatus("stopped");
          else schedule();
        };
        socket.onerror = () => socket?.close();
      } catch (error) {
        if (
          error instanceof ApiError &&
          [401, 403, 404].includes(error.status)
        ) {
          setStatus("stopped");
        } else schedule();
      }
    };

    void connect();
    return () => {
      disposed = true;
      if (timer !== undefined) window.clearTimeout(timer);
      socket?.close(1000, "page left");
    };
  }, [publicationId, queryClient]);
  return status;
}

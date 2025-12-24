import { useEffect, useRef, useCallback, useState } from 'react';
import type { WebSocketMessage } from '@/types';

type EventHandler = (data: any) => void;

const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8003/ws';
const RECONNECT_INTERVAL = 3000;
const MAX_RECONNECT_ATTEMPTS = 5;

export const useWebSocket = () => {
  const ws = useRef<WebSocket | null>(null);
  const handlers = useRef<Map<string, Set<EventHandler>>>(new Map());
  const reconnectAttempts = useRef(0);
  const reconnectTimeout = useRef<NodeJS.Timeout>();
  const [isConnected, setIsConnected] = useState(false);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const connect = useCallback(() => {
    try {
      ws.current = new WebSocket(WS_URL);

      ws.current.onopen = () => {
        console.log('WebSocket connected');
        setIsConnected(true);
        setConnectionError(null);
        reconnectAttempts.current = 0;
      };

      ws.current.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          const { event_type, data } = message;

          // Notify specific event handlers
          handlers.current.get(event_type)?.forEach((handler) => handler(data));

          // Notify wildcard handlers
          handlers.current.get('*')?.forEach((handler) => handler(message));
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      ws.current.onerror = (error) => {
        console.error('WebSocket error:', error);
        setConnectionError('Connection error occurred');
      };

      ws.current.onclose = () => {
        console.log('WebSocket closed');
        setIsConnected(false);

        // Attempt to reconnect
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current++;
          console.log(
            `Reconnecting... Attempt ${reconnectAttempts.current}/${MAX_RECONNECT_ATTEMPTS}`
          );

          reconnectTimeout.current = setTimeout(() => {
            connect();
          }, RECONNECT_INTERVAL * reconnectAttempts.current);
        } else {
          setConnectionError('Max reconnection attempts reached');
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket connection:', error);
      setConnectionError('Failed to connect');
    }
  }, []);

  useEffect(() => {
    // WebSocket disabled - backend endpoint /ws not implemented yet
    // Using polling via React Query instead
    // connect();

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (ws.current) {
        ws.current.close();
      }
    };
  }, [connect]);

  const subscribe = useCallback((eventType: string, handler: EventHandler) => {
    if (!handlers.current.has(eventType)) {
      handlers.current.set(eventType, new Set());
    }
    handlers.current.get(eventType)!.add(handler);

    // Return unsubscribe function
    return () => {
      handlers.current.get(eventType)?.delete(handler);
    };
  }, []);

  const send = useCallback((eventType: string, data: any) => {
    if (ws.current?.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify({ event_type: eventType, data }));
    } else {
      console.warn('WebSocket is not connected');
    }
  }, []);

  const reconnect = useCallback(() => {
    reconnectAttempts.current = 0;
    if (ws.current) {
      ws.current.close();
    }
    connect();
  }, [connect]);

  return {
    subscribe,
    send,
    reconnect,
    isConnected,
    connectionError,
  };
};

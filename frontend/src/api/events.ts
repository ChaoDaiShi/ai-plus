/** SSE 订阅（api.md §6）：原生 EventSource 命名事件，服务端断线自动补发。 */

import { apiEventSourceUrl } from './client';
import type { SseEventDto, TaskStatusDto } from '../types/api';

export interface TaskEventHandlers {
  onNodeUpdated?: (payload: {
    node: string;
    status: string;
    progress?: number;
    message?: string;
    duration_ms?: number | null;
    output_summary?: Record<string, unknown> | null;
    skip_reason?: string | null;
  }) => void;
  onItemUpdated?: (payload: Record<string, unknown>) => void;
  onTaskCompleted?: (status: TaskStatusDto) => void;
  onTaskFailed?: (status: TaskStatusDto, error?: unknown) => void;
  onTaskCanceled?: (status: TaskStatusDto) => void;
  onStreamEnd?: (lastEventId: string, status: string) => void;
  onError?: () => void;
}

/** 订阅任务事件流；返回关闭函数。收到终态/stream.end 后自动关闭。 */
export function subscribeTaskEvents(
  taskId: string,
  after: string | number,
  handlers: TaskEventHandlers,
): () => void {
  const source = new EventSource(
    apiEventSourceUrl(`/api/v1/insight/task/${taskId}/events?after=${after}`),
  );

  const unwrap = (event: MessageEvent): SseEventDto => JSON.parse(event.data);
  const close = () => source.close();

  source.addEventListener('node.updated', event => {
    handlers.onNodeUpdated?.(unwrap(event as MessageEvent).payload as never);
  });
  source.addEventListener('item.updated', event => {
    handlers.onItemUpdated?.(unwrap(event as MessageEvent).payload);
  });
  source.addEventListener('task.completed', () => {
    handlers.onTaskCompleted?.('COMPLETED');
    close();
  });
  source.addEventListener('task.failed', event => {
    handlers.onTaskFailed?.('FAILED', unwrap(event as MessageEvent).payload);
    close();
  });
  source.addEventListener('task.canceled', () => {
    handlers.onTaskCanceled?.('CANCELED');
    close();
  });
  source.addEventListener('stream.end', event => {
    const data = JSON.parse((event as MessageEvent).data) as {
      last_event_id: string;
      status: string;
    };
    handlers.onStreamEnd?.(data.last_event_id, data.status);
    close();
  });
  source.onerror = () => {
    handlers.onError?.();
  };

  return close;
}

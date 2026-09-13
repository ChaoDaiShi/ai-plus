/** 任务 API（api.md §3–§4、§7）。 */

import { apiFetch } from './client';
import type {
  TaskCreatedDto,
  TaskListItemDto,
  TaskSnapshotDto,
} from '../types/api';

export async function createTask(
  projectId: string,
  asins: string[],
  marketplace = 'US',
): Promise<TaskCreatedDto> {
  return apiFetch<TaskCreatedDto>('/api/v1/insight/task', {
    method: 'POST',
    headers: { 'Idempotency-Key': crypto.randomUUID() },
    body: JSON.stringify({ project_id: projectId, asins, marketplace }),
  });
}

export async function getTask(taskId: string): Promise<TaskSnapshotDto> {
  return apiFetch<TaskSnapshotDto>(`/api/v1/insight/task/${taskId}`);
}

export async function listTasks(limit = 20): Promise<TaskListItemDto[]> {
  const body = await apiFetch<{ items: TaskListItemDto[]; next_cursor: string | null }>(
    `/api/v1/insight/tasks?limit=${limit}`,
  );
  return body.items;
}

export async function cancelTask(taskId: string): Promise<void> {
  await apiFetch(`/api/v1/insight/task/${taskId}/cancel`, { method: 'POST' });
}

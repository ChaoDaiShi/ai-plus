/** 系统信息：健康检查与非生产环境的预置项目 ID。 */

import { apiFetch } from './client';

export interface HealthDto {
  status: string;
  version: string;
  env: string;
  dev_project_id?: string;
}

export async function getHealth(): Promise<HealthDto> {
  return apiFetch<HealthDto>('/health');
}

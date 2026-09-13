/** 报告与证据 API（api.md §5）。 */

import { apiFetch } from './client';
import type {
  EvidencePageDto,
  ReportDto,
} from '../types/api';

export async function getReport(taskId: string, itemId: string): Promise<ReportDto> {
  return apiFetch<ReportDto>(
    `/api/v1/insight/task/${taskId}/items/${itemId}/report`,
  );
}

export async function getEvidence(
  taskId: string,
  itemId: string,
  params: {
    reportId: string;
    clusterId?: string;
    proposalId?: string;
    cursor?: string;
    limit?: number;
  },
): Promise<EvidencePageDto> {
  const query = new URLSearchParams({ report_id: params.reportId });
  if (params.clusterId) query.set('cluster_id', params.clusterId);
  if (params.proposalId) query.set('proposal_id', params.proposalId);
  if (params.cursor) query.set('cursor', params.cursor);
  if (params.limit) query.set('limit', String(params.limit));
  return apiFetch<EvidencePageDto>(
    `/api/v1/insight/task/${taskId}/items/${itemId}/evidence?${query.toString()}`,
  );
}

/** 后端 Report DTO → 前端视图模型适配层。 */

import type { ClusterDto, ProposalDto, ReportDto } from '../types/api';
import type { PainPointCluster, ProposalView } from '../types';

export const CATEGORY_LABELS: Record<string, string> = {
  quality: '结构强度',
  function: '功能失效',
  size: '规格公差',
  accessory: '配件缺失',
  instructions: '装配说明',
  packaging: '包装履约',
  other: '其他',
};

export interface TaskWorkspace {
  taskId: string;
  itemId: string;
  asin: string;
  status: string;
  report: ReportDto | null;
}

export function isZhLocale(locale: string): boolean {
  return locale.startsWith('zh');
}

export function clusterToView(cluster: ClusterDto, zh: boolean): PainPointCluster {
  return {
    id: cluster.id,
    name: zh ? cluster.name_zh : cluster.name_en,
    category: cluster.category,
    categoryLabel: CATEGORY_LABELS[cluster.category] ?? cluster.category,
    frequency: cluster.frequency,
    severity: cluster.severity,
    shareRatio: cluster.share_ratio ?? 0,
    sampleQuote: cluster.sample_quote?.text ?? '',
    translatedQuote: cluster.sample_quote?.translation ?? '',
    sampleReviewId: cluster.sample_quote?.review_id ?? '',
    reviewIds: [],
    photoCount: cluster.photo_count,
    evidenceCount: cluster.evidence_count,
    denominator: cluster.denominator,
    severityReason: cluster.severity_reason,
  };
}

export function proposalToView(proposal: ProposalDto): ProposalView {
  return {
    id: proposal.id,
    column: proposal.column,
    title: proposal.title,
    problem: proposal.action && proposal.assumptions[0]
      ? proposal.assumptions[0].replace(/^问题定性：/, '')
      : '',
    action: proposal.action,
    expectedEffect: proposal.expected_effect,
    verificationRequired: proposal.verification_required,
    evidenceCount: proposal.evidence_count,
    targetClusterIds: proposal.target_cluster_ids,
  };
}

export function reportToWorkspaceViews(report: ReportDto, zh: boolean) {
  return {
    clusters: report.clusters.map(c => clusterToView(c, zh)),
    productProposals: report.proposals.product.map(proposalToView),
    packagingProposals: report.proposals.packaging.map(proposalToView),
  };
}

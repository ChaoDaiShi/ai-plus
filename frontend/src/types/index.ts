export interface AuthUser {
  id: string;
  name: string;
  email: string;
  role: 'owner' | 'pm' | 'supply_chain';
  roleName: string;
  avatar?: string;
}

export type Marketplace = 'US';

/** 后端 P0 七节点（与 backend NODE_ORDER 对齐）。 */
export type AgentNode =
  | 'ingestion'
  | 'normalization'
  | 'embedding'
  | 'clustering'
  | 'proposal'
  | 'evidence_validation'
  | 'publish';

export type TaskStatusUi = 'pending' | 'running' | 'completed' | 'failed' | 'canceled' | 'vetoed';

export interface TaskNodeInfo {
  key: AgentNode;
  name: string;
  desc: string;
  status: 'idle' | 'running' | 'completed' | 'failed' | 'canceled' | 'skipped';
  durationMs?: number;
  outputSummary?: string;
  progress?: number;
}

/** 任务工作区摘要（由后端任务快照 + 报告派生）。 */
export interface InsightTask {
  taskId: string;
  itemId: string;
  asin: string;
  title: string;
  marketplace: Marketplace;
  status: TaskStatusUi;
  progress: number;
  createdAt: string;
  completedAt?: string;
  reportId?: string | null;
  nodes: TaskNodeInfo[];
}

/** 痛点簇视图模型（源自 Report.clusters）。 */
export interface PainPointCluster {
  id: string;
  name: string;
  category: string;
  categoryLabel: string;
  frequency: number;
  denominator: number;
  severity: number;
  shareRatio: number;
  sampleQuote: string;
  translatedQuote: string;
  sampleReviewId: string;
  reviewIds: string[];
  photoCount: number;
  evidenceCount: number;
  severityReason: string;
}

/** 双栏建议视图模型（源自 Report.proposals）。 */
export interface ProposalView {
  id: string;
  column: 'PRODUCT' | 'PACKAGING';
  title: string;
  problem: string;
  action: string;
  expectedEffect: string;
  verificationRequired: string[];
  evidenceCount: number;
  targetClusterIds: string[];
}

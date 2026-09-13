/** Backend API DTOs（docs/api.md 契约）。 */

export type TaskStatusDto =
  | 'QUEUED'
  | 'RUNNING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELED';

export type NodeKey =
  | 'ingestion'
  | 'normalization'
  | 'embedding'
  | 'clustering'
  | 'proposal'
  | 'evidence_validation'
  | 'publish';

export interface TaskItemCreatedDto {
  item_id: string;
  asin: string;
  status: TaskStatusDto;
}

export interface TaskCreatedDto {
  task_id: string;
  status: TaskStatusDto;
  phase: 'P0';
  reused: boolean;
  window: { start_date: string; end_date: string };
  items: TaskItemCreatedDto[];
  links: { self: string; events: string };
}

export interface NodeStateDto {
  key: string;
  status: string;
  duration_ms?: number | null;
  started_at?: string | null;
  completed_at?: string | null;
  output_summary?: Record<string, unknown> | null;
  skip_reason?: string | null;
}

export interface TaskItemSnapshotDto {
  item_id: string;
  asin: string;
  status: TaskStatusDto;
  attempt: number;
  current_node: string | null;
  nodes: NodeStateDto[];
  progress?: {
    completed_nodes: number;
    total_nodes: number;
    processed_reviews: number;
    total_reviews: number | null;
  } | null;
  report_id: string | null;
  error: { code: string; message: string; retryable?: boolean } | null;
}

export interface TaskSnapshotDto {
  task_id: string;
  project_id: string;
  phase: 'P0';
  status: TaskStatusDto;
  created_at: string;
  completed_at?: string | null;
  last_event_id: string;
  item_counts: Record<string, number>;
  items: TaskItemSnapshotDto[];
  warnings: { code: string; message: string; item_id: string | null }[];
}

export interface TaskListItemDto {
  task_id: string;
  project_id: string;
  created_at: string;
  status: TaskStatusDto;
  asins: string[];
  item_counts: Record<string, number>;
  warnings_count: number;
}

export interface MetricDto {
  value: number | null;
  reason: string;
  basis: { sample_count: number | null; denominator: number | null } | null;
}

export interface ClusterDto {
  id: string;
  name_zh: string;
  name_en: string;
  category: string;
  frequency: number;
  denominator: number;
  share_ratio: number | null;
  severity: number;
  severity_reason: string;
  sample_quote: { review_id: string; text: string; translation: string | null } | null;
  evidence_count: number;
  photo_count: number;
}

export interface ProposalDto {
  id: string;
  column: 'PRODUCT' | 'PACKAGING';
  title: string;
  action: string;
  target_cluster_ids: string[];
  expected_effect: string;
  assumptions: string[];
  verification_required: string[];
  evidence_count: number;
  photo_count: number;
}

export interface ReportDto {
  report_id: string;
  report_version: number;
  item_id: string;
  task_id: string;
  asin: string;
  published_at: string;
  source_mode: 'DEMO_DATASET' | 'LIVE_API';
  snapshot: {
    id: string;
    source: string;
    observed_at: string;
    window: { start_date: string; end_date: string };
    content_hash: string;
  };
  product: {
    asin: string;
    marketplace: string;
    title: string | null;
    price: number | null;
    currency: string | null;
    bsr: number | null;
    observed_at: string | null;
  };
  availability: 'SUFFICIENT' | 'LIMITED' | 'INSUFFICIENT';
  limitations: string[];
  coverage: {
    raw_count: number;
    valid_count: number;
    excluded_count: number;
    negative_count: number;
    rating_distribution: Record<string, number>;
    language_distribution: Record<string, number>;
    month_distribution: Record<string, number>;
    missing_reasons: Record<string, number>;
    sampling_mode: string;
  };
  metrics: {
    sample_average_rating: MetricDto;
    sample_negative_rate: MetricDto;
    issue_count: MetricDto;
    reform_potential_index: MetricDto;
    fba_savings_per_unit: MetricDto;
  };
  clusters: ClusterDto[];
  proposals: { product: ProposalDto[]; packaging: ProposalDto[] };
  veto_status: 'NOT_EVALUATED' | 'PASSED' | 'VETOED';
  provenance: {
    embedding_model_revision: string;
    embedding_mode: 'demo' | 'bge_m3';
    llm_model_id: string | null;
    prompt_version: string;
    pipeline_version: string;
    clustering_version: string | null;
    cleaning_version: string;
  };
}

export interface EvidenceItemDto {
  review_id: string;
  source_review_id: string;
  asin: string | null;
  source_url: string | null;
  rating: number | null;
  language: string | null;
  reviewed_at: string | null;
  observed_at: string;
  text: string;
  translation: string | null;
  images: unknown[];
}

export interface EvidencePageDto {
  report_id: string;
  target: { type: 'cluster' | 'proposal'; id: string };
  total: number;
  items: EvidenceItemDto[];
  next_cursor: string | null;
}

export interface SseEventDto {
  schema_version: number;
  task_id: string;
  seq: number;
  item_id: string | null;
  attempt: number | null;
  occurred_at: string | null;
  payload: Record<string, unknown>;
}

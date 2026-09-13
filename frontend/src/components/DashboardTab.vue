<script setup lang="ts">
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  Play,
  ShieldAlert,
  Sliders,
  Wrench,
} from 'lucide-vue-next';
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import type { InsightTask, PainPointCluster } from '../types';
import type { ReportDto } from '../types/api';

const props = defineProps<{
  currentTask: InsightTask | null;
  report: ReportDto | null;
  clusters: PainPointCluster[];
  allTasks: InsightTask[];
  backendEnv: string;
}>();

const emit = defineEmits<{
  (e: 'navigate', tab: 'dashboard' | 'agent' | 'voc' | 'proposals' | 'financial'): void;
  (e: 'selectTask', taskId: string): void;
  (e: 'startNewTask'): void;
}>();

const { t } = useI18n();

const negativeRate = computed(() => {
  const metric = props.report?.metrics?.sample_negative_rate;
  return metric?.value ?? null;
});

const peakSeverity = computed(() => {
  if (props.clusters.length === 0) return null;
  return Math.max(...props.clusters.map(c => c.severity));
});

const proposalsCount = computed(() => {
  if (!props.report) return 0;
  return props.report.proposals.product.length + props.report.proposals.packaging.length;
});

const validReviews = computed(() => props.report?.coverage.valid_count ?? null);
const totalReviews = computed(() => props.report?.coverage.raw_count ?? null);

const statusLabel = (status: string): string => {
  const table: Record<string, string> = {
    completed: 'common.completed',
    failed: 'common.failed',
    running: 'common.running',
    pending: 'common.pending',
    canceled: 'common.canceled',
  };
  const key = table[status];
  return key ? t(key) : status;
};

const statusClass = (status: string): string => {
  if (status === 'completed') return 'text-emerald-400';
  if (status === 'failed') return 'text-rose-400';
  if (status === 'running' || status === 'pending') return 'text-[#7170ff]';
  return 'text-zinc-400';
};

void props;
</script>

<template>
  <div class="space-y-8">
    <!-- Clean Product Header & Title (Single breathing row) -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[rgba(255,255,255,0.06)]">
      <div class="space-y-1.5 max-w-3xl">
        <div class="flex items-center gap-2 text-xs font-mono text-[#8a8f98]">
          <span>{{ currentTask?.asin ?? t('dashboard.noTask') }}</span>
          <span>·</span>
          <span>{{ currentTask?.marketplace ?? 'US' }} {{ t('header.marketplace') }}</span>
          <template v-if="totalReviews !== null">
            <span>·</span>
            <span>{{ totalReviews.toLocaleString() }} {{ t('dashboard.reviewsRaw') }}</span>
          </template>
          <template v-if="backendEnv">
            <span>·</span>
            <span class="uppercase">{{ backendEnv }}</span>
          </template>
        </div>
        <h1 class="text-xl sm:text-2xl font-medium tracking-tight text-[#f7f8f8]">
          {{ report?.product.title ?? currentTask?.title ?? t('dashboard.subtitle') }}
        </h1>
      </div>

      <!-- Quick Action Buttons -->
      <div class="flex items-center gap-2 shrink-0">
        <button
          @click="emit('navigate', 'proposals')"
          class="ln-btn-primary px-3.5 py-2 flex items-center gap-2"
        >
          <Wrench class="w-3.5 h-3.5" />
          <span>{{ t('dashboard.viewProposals') }}</span>
          <ArrowRight class="w-3.5 h-3.5 opacity-70" />
        </button>

        <button
          @click="emit('startNewTask')"
          class="ln-btn px-3.5 py-2 flex items-center gap-2"
        >
          <Play class="w-3.5 h-3.5 text-zinc-400" />
          <span>{{ t('dashboard.runNew') }}</span>
        </button>
      </div>
    </div>

    <!-- 4 Clean, Quiet KPI Cards（全部来自真实报告，未评估项如实标注） -->
    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="ln-surface p-5 space-y-1">
        <div class="text-xs text-[#8a8f98]">{{ t('dashboard.negativeRate') }}</div>
        <div class="text-2xl font-semibold font-mono text-[#f7f8f8] tracking-tight">
          <template v-if="negativeRate !== null">{{ (negativeRate * 100).toFixed(1) }}%</template>
          <template v-else>—</template>
        </div>
        <div class="text-[11px] text-[#5e626e] pt-1">
          {{ t('dashboard.negativeSub') }}
        </div>
      </div>

      <div class="ln-surface p-5 space-y-1">
        <div class="text-xs text-[#8a8f98]">{{ t('dashboard.peakSeverity') }}</div>
        <div class="text-2xl font-semibold font-mono text-amber-400 tracking-tight">
          <template v-if="peakSeverity !== null">
            {{ peakSeverity }} <span class="text-xs font-normal text-[#5e626e]">/ 5.0</span>
          </template>
          <template v-else>—</template>
        </div>
        <div class="text-[11px] text-[#5e626e] pt-1">
          {{ t('dashboard.peakSub') }}
        </div>
      </div>

      <div class="ln-surface p-5 space-y-1">
        <div class="text-xs text-[#8a8f98]">{{ t('dashboard.validReviews') }}</div>
        <div class="text-2xl font-semibold font-mono text-[#f7f8f8] tracking-tight">
          <template v-if="validReviews !== null">{{ validReviews.toLocaleString() }}</template>
          <template v-else>—</template>
        </div>
        <div class="text-[11px] text-[#5e626e] pt-1">
          {{ t('dashboard.validSub') }}
        </div>
      </div>

      <div class="ln-surface p-5 space-y-1">
        <div class="text-xs text-[#8a8f98]">{{ t('dashboard.proposalsCount') }}</div>
        <div class="text-2xl font-semibold font-mono text-[#f7f8f8] tracking-tight">
          <template v-if="report">{{ proposalsCount }} <span class="text-xs font-normal text-[#5e626e]">{{ t('common.items') }}</span></template>
          <template v-else>—</template>
        </div>
        <div class="text-[11px] text-[#5e626e] pt-1">
          {{ t('dashboard.proposalsSub') }}
        </div>
      </div>

      <!-- FBA 节约额 P0 未评估（禁止假数字） -->
      <div class="ln-surface p-5 space-y-1 col-span-2 lg:col-span-4 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div>
          <div class="text-xs text-[#8a8f98]">{{ t('dashboard.fbaSavings') }}</div>
          <div class="text-sm font-mono text-[#8a8f98] pt-1">Not evaluated</div>
        </div>
        <div class="text-[11px] text-[#5e626e] font-mono">
          {{ t('dashboard.fbaNotEvaluatedNote') }}
        </div>
      </div>
    </div>

    <!-- Main Content Section: Clean 2-Column Split -->
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8 items-start">
      <!-- Left Column (7 cols): Top Pain Points Ranked List -->
      <div class="lg:col-span-7 space-y-4">
        <div class="flex items-center justify-between pb-1">
          <h2 class="text-sm font-medium text-[#f7f8f8] tracking-tight">
            {{ t('dashboard.topPainPoints') }}
          </h2>
          <button
            @click="emit('navigate', 'voc')"
            class="text-xs text-[#8a8f98] hover:text-[#f7f8f8] flex items-center gap-1 transition-colors"
          >
            <span>{{ t('dashboard.vocLink') }}</span>
            <ChevronRight class="w-3.5 h-3.5" />
          </button>
        </div>

        <!-- Clean Pain Point List -->
        <div class="ln-surface divide-y divide-[rgba(255,255,255,0.05)] overflow-hidden">
          <div
            v-for="(cluster, idx) in clusters"
            :key="cluster.id"
            class="p-4 hover:bg-[rgba(255,255,255,0.02)] transition-colors cursor-pointer group space-y-2"
            @click="emit('navigate', 'voc')"
          >
            <div class="flex items-center justify-between text-xs">
              <div class="flex items-center gap-2.5">
                <span class="text-xs font-mono text-[#5e626e]">0{{ idx + 1 }}</span>
                <span class="font-medium text-[#f7f8f8] group-hover:text-[#7170ff] transition-colors">
                  {{ cluster.name }}
                </span>
              </div>
              <div class="flex items-center gap-3 font-mono text-[11px] text-[#8a8f98]">
                <span>{{ cluster.frequency }} {{ t('dashboard.frequency') }}</span>
                <span class="text-amber-400">{{ t('dashboard.rating') }} {{ cluster.severity }}</span>
              </div>
            </div>

            <!-- Proportion Bar -->
            <div class="w-full bg-[rgba(255,255,255,0.06)] h-1 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full bg-[#7170ff] transition-all"
                :style="{ width: `${cluster.shareRatio * 100}%` }"
              />
            </div>

            <p class="text-[11px] text-[#8a8f98] line-clamp-1">
              "{{ cluster.sampleQuote }}"
            </p>
          </div>

          <div v-if="clusters.length === 0" class="p-6 text-center text-xs text-[#5e626e] font-mono">
            {{ t('dashboard.noClusters') }}
          </div>
        </div>
      </div>

      <!-- Right Column (5 cols): Decision Status & Tasks -->
      <div class="lg:col-span-5 space-y-6">
        <!-- Decision Gate Mini Card -->
        <div class="ln-surface p-5 space-y-3">
          <div class="flex items-center justify-between">
            <span class="text-xs font-medium text-[#8a8f98]">{{ t('dashboard.financialStatus') }}</span>
            <span
              v-if="report"
              class="flex items-center gap-1.5 text-xs font-mono text-[#8a8f98]"
            >
              <ShieldAlert class="w-3.5 h-3.5 text-amber-400" />
              <span>{{ t('dashboard.notEvaluated') }}</span>
            </span>
            <span
              v-else-if="currentTask?.status === 'completed'"
              class="flex items-center gap-1.5 text-xs font-mono text-emerald-400"
            >
              <CheckCircle2 class="w-3.5 h-3.5" />
              <span>{{ t('common.completed') }}</span>
            </span>
          </div>

          <p class="text-xs text-[#8a8f98] leading-relaxed">
            {{ t('dashboard.financialDescP0') }}
          </p>

          <button
            @click="emit('navigate', 'financial')"
            class="w-full py-2 px-3 ln-btn flex items-center justify-center gap-2 text-xs"
          >
            <Sliders class="w-3.5 h-3.5" />
            <span>{{ t('dashboard.adjustSandbox') }}</span>
          </button>
        </div>

        <!-- Monitored ASINs Switcher -->
        <div class="space-y-3">
          <div class="flex items-center justify-between text-xs text-[#8a8f98]">
            <span>{{ t('dashboard.taskList') }}</span>
            <span>{{ allTasks.length }} {{ t('common.items') }}</span>
          </div>

          <div class="ln-surface divide-y divide-[rgba(255,255,255,0.05)] overflow-hidden">
            <div
              v-for="task in allTasks"
              :key="task.taskId"
              @click="emit('selectTask', task.taskId)"
              :class="[
                'p-3.5 flex items-center justify-between text-xs cursor-pointer transition-colors',
                currentTask?.taskId === task.taskId
                  ? 'bg-[rgba(255,255,255,0.04)] text-[#f7f8f8]'
                  : 'hover:bg-[rgba(255,255,255,0.02)] text-[#8a8f98]'
              ]"
            >
              <div class="space-y-0.5">
                <div class="font-mono font-medium text-[#f7f8f8]">{{ task.asin }}</div>
                <div class="text-[11px] text-[#5e626e] line-clamp-1 max-w-[200px]">
                  {{ task.createdAt }}
                </div>
              </div>

              <div class="text-right font-mono text-[11px]" :class="statusClass(task.status)">
                {{ statusLabel(task.status) }}
              </div>
            </div>

            <div v-if="allTasks.length === 0" class="p-6 text-center text-xs text-[#5e626e] font-mono">
              {{ t('dashboard.noTasks') }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

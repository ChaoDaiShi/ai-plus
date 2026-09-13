<script setup lang="ts">
import {
  Activity,
  Check,
  ChevronRight,
  CircleSlash,
  Pause,
  Play,
  RotateCcw,
  Terminal,
  X,
} from 'lucide-vue-next';
import { computed, onBeforeUnmount, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { cancelTask, createTask, getTask } from '../api/tasks';
import { subscribeTaskEvents } from '../api/events';
import type { InsightTask, TaskNodeInfo } from '../types';
import type { TaskSnapshotDto } from '../types/api';

const props = defineProps<{
  currentTask: InsightTask | null;
  projectId: string;
}>();

const emit = defineEmits<{
  (e: 'taskCreated', taskId: string): void;
  (e: 'taskFinished', status: string): void;
}>();

const { t, locale } = useI18n();

const inputAsin = ref('B08N5WRWNW');
const isStreaming = ref(false);
const activeNodeKey = ref<string | null>(null);
const streamLogs = ref<string[]>([]);
const liveNodes = ref<TaskNodeInfo[]>([]);
const runningTaskId = ref<string | null>(null);
const errorMessage = ref<string | null>(null);
let closeEvents: (() => void) | null = null;

const zh = computed(() => locale.value.startsWith('zh'));

const NODE_META: Record<string, { zh: string; en: string }> = {
  ingestion: { zh: '评论采集', en: 'Review ingestion' },
  normalization: { zh: '评论清洗', en: 'Normalization' },
  embedding: { zh: '片段向量化', en: 'Embedding' },
  clustering: { zh: '痛点聚类', en: 'Clustering' },
  proposal: { zh: '双栏建议', en: 'Dual-column proposals' },
  evidence_validation: { zh: '证据校验', en: 'Evidence validation' },
  publish: { zh: '报告发布', en: 'Publish report' },
};

const NODE_PROGRESS: Record<string, number> = {
  ingestion: 10,
  normalization: 25,
  embedding: 45,
  clustering: 65,
  proposal: 80,
  evidence_validation: 92,
  publish: 100,
};

const nodes = computed<TaskNodeInfo[]>(() => {
  if (liveNodes.value.length > 0) return liveNodes.value;
  if (props.currentTask && props.currentTask.nodes?.length) return props.currentTask.nodes;
  return Object.keys(NODE_META).map(key => ({
    key: key as TaskNodeInfo['key'],
    name: zh.value ? NODE_META[key].zh : NODE_META[key].en,
    desc: '',
    status: 'idle',
  }));
});

const overallProgress = computed(() => {
  const completed = nodes.value.filter(n => n.status === 'completed');
  const running = nodes.value.find(n => n.status === 'running');
  const base = running ? running.progress ?? 0 : 0;
  const doneShare = completed.reduce((sum, n) => sum + (n.progress ?? 0), 0);
  return Math.min(100, Math.round(doneShare * 0.8 + base * 0.2)) || 0;
});

const activeNode = computed(() => activeNodeKey.value);

const activeNodeInfo = computed(() => {
  if (!activeNodeKey.value) return null;
  return (
    liveNodes.value.find(n => n.key === activeNodeKey.value) ??
    nodes.value.find(n => n.key === activeNodeKey.value) ??
    null
  );
});

const nowLabel = () => new Date().toLocaleTimeString('zh-CN', { hour12: false });

const appendLog = (line: string) => {
  streamLogs.value.push(`${nowLabel()} ${line}`);
};

function buildLiveNodes(): TaskNodeInfo[] {
  return Object.keys(NODE_META).map(key => ({
    key: key as TaskNodeInfo['key'],
    name: zh.value ? NODE_META[key].zh : NODE_META[key].en,
    desc: '',
    status: 'idle',
    progress: NODE_PROGRESS[key],
  }));
}

const runRealPipeline = async () => {
  if (isStreaming.value) return;
  if (!props.projectId) {
    errorMessage.value = t('workflow.noBackend');
    appendLog(`[ERROR] ${t('workflow.noBackend')}`);
    return;
  }
  const asin = inputAsin.value.trim().toUpperCase();
  if (!/^[A-Z0-9]{10}$/.test(asin)) {
    errorMessage.value = t('workflow.invalidAsin');
    return;
  }
  errorMessage.value = null;
  isStreaming.value = true;
  streamLogs.value = [];
  liveNodes.value = buildLiveNodes();
  activeNodeKey.value = 'ingestion';
  appendLog(`[INIT] LangGraph P0 pipeline → ASIN ${asin} (US)`);

  try {
    const created = await createTask(props.projectId, [asin]);
    runningTaskId.value = created.task_id;
    appendLog(
      `[TASK] ${created.task_id} · reused=${created.reused} · window ${created.window.start_date} → ${created.window.end_date}`,
    );
    emit('taskCreated', created.task_id);

    closeEvents = subscribeTaskEvents(created.task_id, 0, {
      onNodeUpdated: payload => {
        const node = payload.node as string;
        const status = String(payload.status);
        const target = liveNodes.value.find(n => n.key === node);
        if (target) {
          if (status === 'RUNNING') {
            target.status = 'running';
            activeNodeKey.value = node;
          } else if (status === 'COMPLETED') {
            target.status = 'completed';
            target.durationMs = payload.duration_ms ?? undefined;
            target.outputSummary =
              (payload.message as string) ??
              (payload.output_summary ? JSON.stringify(payload.output_summary) : '');
          }
        }
        if (status === 'RUNNING') {
          appendLog(`[${node.toUpperCase()}] ${t('workflow.nodeStarted')} (${payload.progress}%)`);
        } else if (status === 'COMPLETED') {
          appendLog(
            `[${node.toUpperCase()}] ${payload.message ?? t('workflow.nodeCompleted')} (${payload.progress}%)`,
          );
        } else if (status === 'SKIPPED') {
          appendLog(`[${node.toUpperCase()}] SKIP: ${payload.skip_reason ?? ''}`);
        }
      },
      onItemUpdated: payload => {
        appendLog(`[ITEM] status=${payload.status}`);
      },
      onTaskCompleted: () => {
        isStreaming.value = false;
        liveNodes.value.forEach(n => {
          if (n.status === 'running') n.status = 'completed';
        });
        appendLog('[COMPLETE] ✅ ' + t('workflow.taskCompleted'));
        emit('taskFinished', 'COMPLETED');
      },
      onTaskFailed: (_status, error) => {
        isStreaming.value = false;
        liveNodes.value.forEach(n => {
          if (n.status === 'running') n.status = 'failed';
        });
        const detail =
          (error as { error?: string } | undefined)?.error ?? t('workflow.taskFailed');
        errorMessage.value = detail;
        appendLog(`[FAILED] ${detail}`);
        emit('taskFinished', 'FAILED');
      },
      onTaskCanceled: () => {
        isStreaming.value = false;
        appendLog('[CANCELED] ' + t('workflow.taskCanceled'));
        emit('taskFinished', 'CANCELED');
      },
      onError: () => {
        // EventSource 自动重连；快照兜底见 refreshFromSnapshot
      },
    });
  } catch (error) {
    isStreaming.value = false;
    errorMessage.value = error instanceof Error ? error.message : String(error);
    appendLog(`[ERROR] ${errorMessage.value}`);
  }
};

const stopPipeline = async () => {
  if (runningTaskId.value) {
    try {
      await cancelTask(runningTaskId.value);
      appendLog('[PAUSE] ' + t('workflow.cancelRequested'));
    } catch (error) {
      appendLog(`[ERROR] ${error instanceof Error ? error.message : String(error)}`);
    }
  }
};

const refreshFromSnapshot = async () => {
  const taskId = runningTaskId.value ?? props.currentTask?.taskId;
  if (!taskId) return;
  const snapshot: TaskSnapshotDto = await getTask(taskId);
  const item = snapshot.items[0];
  if (item?.nodes?.length) {
    liveNodes.value = item.nodes.map(n => ({
      key: n.key as TaskNodeInfo['key'],
      name: zh.value ? NODE_META[n.key]?.zh ?? n.key : NODE_META[n.key]?.en ?? n.key,
      desc: '',
      status: (n.status.toLowerCase() === 'completed'
        ? 'completed'
        : n.status.toLowerCase() === 'running'
          ? 'running'
          : n.status.toLowerCase() === 'failed'
            ? 'failed'
            : n.status.toLowerCase() === 'canceled'
              ? 'canceled'
              : 'skipped') as TaskNodeInfo['status'],
      durationMs: n.duration_ms ?? undefined,
      outputSummary: n.output_summary ? JSON.stringify(n.output_summary) : undefined,
      progress: NODE_PROGRESS[n.key],
    }));
  }
  appendLog('[REFRESH] ' + t('workflow.refreshed') + ` → ${snapshot.status}`);
};

onBeforeUnmount(() => {
  closeEvents?.();
});
</script>

<template>
  <div class="space-y-8">
    <!-- Top Action Bar -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-[rgba(255,255,255,0.06)]">
      <div class="space-y-1">
        <h1 class="text-xl font-medium tracking-tight text-[#f7f8f8]">
          {{ t('workflow.title') }}
        </h1>
        <p class="text-xs text-[#8a8f98]">
          {{ t('workflow.subtitle') }}
        </p>
      </div>

      <!-- Execution Controls -->
      <div class="flex items-center gap-2">
        <input
          v-model="inputAsin"
          type="text"
          maxlength="10"
          class="bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] rounded-md px-2.5 py-1.5 text-xs font-mono text-[#f7f8f8] w-32 focus:outline-none focus:border-[rgba(255,255,255,0.2)]"
          placeholder="B08N5WRWNW"
        />

        <span class="text-[11px] font-mono px-2 py-1.5 rounded-md bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-[#8a8f98]">
          US
        </span>

        <button
          v-if="!isStreaming"
          @click="runRealPipeline"
          class="ln-btn-primary px-3.5 py-1.5 flex items-center gap-1.5"
        >
          <Play class="w-3 h-3 fill-current" />
          <span>{{ t('workflow.runAgent') }}</span>
        </button>

        <button
          v-else
          @click="stopPipeline"
          class="ln-btn px-3.5 py-1.5 flex items-center gap-1.5 text-amber-400"
        >
          <Pause class="w-3 h-3 fill-current" />
          <span>{{ t('workflow.pauseAgent') }}</span>
        </button>

        <button
          @click="refreshFromSnapshot"
          class="p-1.5 ln-btn"
          :title="t('workflow.refreshSnapshot')"
        >
          <RotateCcw class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>

    <p v-if="errorMessage" class="text-xs text-rose-400 font-mono -mt-4">{{ errorMessage }}</p>

    <!-- Overall Progress -->
    <div class="ln-surface p-4 space-y-2">
      <div class="flex items-center justify-between text-xs">
        <span class="font-mono text-[#8a8f98]">{{ t('workflow.overallProgress') }}</span>
        <span class="font-mono text-[#f7f8f8]">{{ overallProgress }}%</span>
      </div>
      <div class="h-1.5 rounded-full bg-white/[0.06] overflow-hidden">
        <div
          class="h-full rounded-full bg-gradient-to-r from-indigo-500 to-emerald-400 transition-all duration-500"
          :style="{ width: `${overallProgress}%` }"
        />
      </div>
    </div>

    <!-- Minimalist Horizontal Stepper (7 real LangGraph nodes) -->
    <div class="ln-surface p-4 sm:p-5">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div
          v-for="(node, idx) in nodes"
          :key="node.key"
          @click="activeNodeKey = node.key"
          :class="[
            'flex items-center gap-3 cursor-pointer py-1 px-2 rounded-md transition-colors',
            activeNodeKey === node.key
              ? 'bg-[rgba(255,255,255,0.05)]'
              : 'hover:bg-[rgba(255,255,255,0.02)]'
          ]"
        >
          <!-- Status Indicator Dot -->
          <div class="flex items-center justify-center w-5 h-5 rounded-full border border-[rgba(255,255,255,0.1)] shrink-0">
            <Check v-if="node.status === 'completed'" class="w-3 h-3 text-emerald-400" />
            <Activity v-else-if="node.status === 'running'" class="w-3 h-3 text-[#7170ff] animate-spin" />
            <X v-else-if="node.status === 'failed'" class="w-3 h-3 text-rose-400" />
            <CircleSlash v-else-if="node.status === 'skipped' || node.status === 'canceled'" class="w-3 h-3 text-zinc-600" />
            <span v-else class="text-[10px] font-mono text-[#5e626e]">{{ idx + 1 }}</span>
          </div>

          <div class="space-y-0.5">
            <div
              :class="[
                'text-xs font-medium',
                activeNodeKey === node.key ? 'text-[#f7f8f8]' : 'text-[#8a8f98]'
              ]"
            >
              {{ node.name }}
            </div>
            <div class="text-[10px] font-mono text-[#5e626e]">
              {{ node.durationMs ? `${node.durationMs}ms` : t('common.ready') }}
            </div>
          </div>

          <ChevronRight
            v-if="idx < nodes.length - 1"
            class="hidden md:block w-3.5 h-3.5 text-zinc-700 ml-auto"
          />
        </div>
      </div>
    </div>

    <!-- 2-Column Split: Node State Inspector & Event Stream -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
      <!-- Node Inspector Card -->
      <div class="ln-surface p-5 space-y-3">
        <div class="flex items-center justify-between text-xs pb-2 border-b border-[rgba(255,255,255,0.06)]">
          <span class="font-medium text-[#f7f8f8]">{{ t('workflow.nodeInspector') }}</span>
          <span class="font-mono text-[#8a8f98]">LangGraph · P0</span>
        </div>

        <div class="text-xs font-mono space-y-2 text-[#8a8f98] pt-1">
          <template v-if="activeNode">
            <div class="text-[#f7f8f8]">
              {{ zh ? NODE_META[activeNode]?.zh : NODE_META[activeNode]?.en }}
              <span class="text-[#5e626e] ml-2">node: {{ activeNode }}</span>
            </div>
            <div>• {{ t('workflow.status') }}: {{ activeNodeInfo?.status ?? 'idle' }}</div>
            <div v-if="activeNodeInfo?.durationMs">• {{ t('workflow.duration') }}: {{ activeNodeInfo.durationMs }}ms</div>
            <div v-if="activeNodeInfo?.outputSummary" class="leading-relaxed text-zinc-300">
              • {{ activeNodeInfo.outputSummary }}
            </div>
            <div v-if="activeNode && NODE_PROGRESS[activeNode]">• {{ t('workflow.progress') }}: {{ NODE_PROGRESS[activeNode] }}%</div>
          </template>
          <div v-else class="text-[#5e626e]">{{ t('workflow.pickNode') }}</div>
        </div>
      </div>

      <!-- Realtime Event Stream Log Terminal -->
      <div class="ln-surface p-5 space-y-3">
        <div class="flex items-center justify-between text-xs pb-2 border-b border-[rgba(255,255,255,0.06)]">
          <div class="flex items-center gap-1.5 text-[#f7f8f8] font-medium">
            <Terminal class="w-3.5 h-3.5 text-[#8a8f98]" />
            <span>{{ t('workflow.eventLogs') }}</span>
          </div>
          <span class="text-[11px] font-mono" :class="isStreaming ? 'text-amber-400' : 'text-[#5e626e]'">
            {{ isStreaming ? 'SSE · LIVE' : t('workflow.sseConnected') }}
          </span>
        </div>

        <div class="h-48 overflow-y-auto space-y-1.5 font-mono text-[11px] text-[#8a8f98] scrollbar-thin select-text">
          <div
            v-for="(log, i) in streamLogs"
            :key="i"
            :class="[
              log.includes('[COMPLETE]') || log.includes('✅')
                ? 'text-emerald-400 font-medium'
                : log.includes('[FAILED]') || log.includes('[ERROR]')
                  ? 'text-rose-400 font-medium'
                  : 'text-[#8a8f98]'
            ]"
          >
            {{ log }}
          </div>
          <div v-if="streamLogs.length === 0" class="text-[#5e626e] italic">
            {{ t('workflow.logsEmpty') }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

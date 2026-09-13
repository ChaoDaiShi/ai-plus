<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import AgentWorkflowTab from './components/AgentWorkflowTab.vue';
import AuthModal from './components/AuthModal.vue';
import DashboardTab from './components/DashboardTab.vue';
import DualColumnProposalsTab from './components/DualColumnProposalsTab.vue';
import EvidenceDrawer from './components/EvidenceDrawer.vue';
import FinancialVetoTab from './components/FinancialVetoTab.vue';
import Header from './components/Header.vue';
import IntroShowcase from './components/IntroShowcase.vue';
import VocClusterTab from './components/VocClusterTab.vue';
import {
  clusterToView,
  proposalToView,
} from './api/adapters';
import { getHealth } from './api/system';
import { getTask, listTasks } from './api/tasks';
import { getReport } from './api/reports';
import type { AuthUser, InsightTask, PainPointCluster, ProposalView } from './types';
import type { ReportDto, TaskSnapshotDto } from './types/api';

type TabType = 'dashboard' | 'agent' | 'voc' | 'proposals' | 'financial';

const { t, locale } = useI18n();

const activeTab = ref<TabType>('dashboard');
const selectedMarketplace = ref<'US'>('US');
const projectId = ref<string>('');
const backendEnv = ref<string>('');

// 真实后端状态
const tasks = ref<InsightTask[]>([]);
const currentTask = ref<InsightTask | null>(null);
const snapshot = ref<TaskSnapshotDto | null>(null);
const report = ref<ReportDto | null>(null);
const reportError = ref<string | null>(null);
const loadingWorkspace = ref(false);

// Intro showcase & Auth states
const showIntro = ref(true);
const isAuthOpen = ref(false);
const currentUser = ref<AuthUser | null>(null);

// Evidence drawer state
const isDrawerOpen = ref(false);
const drawerTitle = ref('');
const drawerTarget = ref<{ clusterId?: string; proposalId?: string } | null>(null);
const toastMessage = ref<string | null>(null);

const showToast = (msg: string) => {
  toastMessage.value = msg;
  setTimeout(() => {
    toastMessage.value = null;
  }, 2800);
};

const zh = computed(() => locale.value.startsWith('zh'));

const clusters = computed<PainPointCluster[]>(() => {
  if (!report.value) return [];
  return report.value.clusters.map(c => clusterToView(c, zh.value));
});

const productProposals = computed<ProposalView[]>(() => {
  if (!report.value) return [];
  return report.value.proposals.product.map(proposalToView);
});

const packagingProposals = computed<ProposalView[]>(() => {
  if (!report.value) return [];
  return report.value.proposals.packaging.map(proposalToView);
});

const isAgentRunning = computed(() => currentTask.value?.status === 'running');

async function refreshTasks(selectFirst = false) {
  try {
    const items = await listTasks();
    const previous = new Map(tasks.value.map(t => [t.taskId, t]));
    tasks.value = items.map(item => {
      const old = previous.get(item.task_id);
      return old && old.status === item.status.toLowerCase()
        ? old
        : {
            taskId: item.task_id,
            itemId: '',
            asin: item.asins[0] ?? '',
            title: '',
            marketplace: 'US' as const,
            status: mapStatus(item.status),
            progress: 0,
            createdAt: item.created_at,
            nodes: [],
          };
    });
    if ((selectFirst || !currentTask.value) && tasks.value.length > 0) {
      await loadWorkspace(tasks.value[0].taskId);
    }
  } catch (error) {
    console.warn('[InsightX] 任务列表加载失败', error);
  }
}

function mapStatus(status: string): InsightTask['status'] {
  const table: Record<string, InsightTask['status']> = {
    QUEUED: 'pending',
    RUNNING: 'running',
    COMPLETED: 'completed',
    FAILED: 'failed',
    CANCELED: 'canceled',
  };
  return table[status] ?? 'pending';
}

async function loadWorkspace(taskId: string) {
  loadingWorkspace.value = true;
  reportError.value = null;
  try {
    const snap = await getTask(taskId);
    snapshot.value = snap;
    const item = snap.items[0];
    const task: InsightTask = {
      taskId,
      itemId: item.item_id,
      asin: item.asin,
      title: item.asin,
      marketplace: 'US',
      status: mapStatus(snap.status),
      progress: Math.round(
        ((item.progress?.completed_nodes ?? 0) / (item.progress?.total_nodes || 7)) * 100,
      ),
      createdAt: snap.created_at,
      completedAt: snap.completed_at ?? undefined,
      reportId: item.report_id,
      nodes: [],
    };
    currentTask.value = task;
    if (item.report_id) {
      try {
        report.value = await getReport(taskId, item.item_id);
        task.title = report.value.product.title ?? item.asin;
      } catch (error) {
        report.value = null;
        reportError.value = error instanceof Error ? error.message : String(error);
      }
    } else {
      report.value = null;
      if (snap.status === 'COMPLETED') {
        reportError.value = t('app.reportUnavailable');
      }
    }
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error));
  } finally {
    loadingWorkspace.value = false;
  }
}

const handleSelectTask = (taskId: string) => {
  void loadWorkspace(taskId);
  showToast(`${t('app.switchedTo')}: ${currentTask.value?.asin ?? ''}`);
};

const handleSelectAsin = (asin: string) => {
  const found = tasks.value.find(t => t.asin === asin);
  if (found) {
    void loadWorkspace(found.taskId);
    showToast(`${t('app.loaded')}: ${asin}`);
  } else {
    showToast(`${t('app.noTaskFor')}: ${asin}`);
  }
};

const handleTaskCreated = (taskId: string) => {
  activeTab.value = 'agent';
  void loadWorkspace(taskId).then(() => void refreshTasks());
};

const handleTaskFinished = (status: string) => {
  void refreshTasks();
  if (status === 'COMPLETED') {
    void loadWorkspace(currentTask.value?.taskId ?? '');
  } else {
    void loadWorkspace(currentTask.value?.taskId ?? '');
  }
};

const handleViewClusterEvidence = (cluster: PainPointCluster) => {
  if (!currentTask.value || !report.value) return;
  drawerTitle.value = cluster.name;
  drawerTarget.value = { clusterId: cluster.id };
  isDrawerOpen.value = true;
};

const handleViewProposalEvidence = (target: { title: string; proposalId: string; count: number }) => {
  if (!currentTask.value || !report.value) return;
  drawerTitle.value = target.title;
  drawerTarget.value = { proposalId: target.proposalId };
  isDrawerOpen.value = true;
};

const handleExportRfc = () => {
  showToast('✓ ' + t('app.rfcExported'));
};

const handleLoginSuccess = (user: AuthUser) => {
  currentUser.value = user;
  showToast(`✓ ${t('app.welcomeBack')}, ${user.name} (${user.roleName})`);
};

const handleLogout = () => {
  currentUser.value = null;
  localStorage.removeItem('insightx_user');
  localStorage.removeItem('insightx_token');
  showToast(t('app.loggedOut'));
};

onMounted(() => {
  const savedUserStr = localStorage.getItem('insightx_user');
  if (savedUserStr) {
    try {
      currentUser.value = JSON.parse(savedUserStr);
    } catch {
      // ignore
    }
  }
  void (async () => {
    try {
      const health = await getHealth();
      backendEnv.value = health.env;
      projectId.value = health.dev_project_id ?? '';
    } catch (error) {
      showToast(t('app.backendUnreachable'));
      console.warn('[InsightX] /health 不可达', error);
    }
    await refreshTasks(true);
  })();
});
</script>

<template>
  <div class="min-h-screen bg-[#08090a] text-[#f7f8f8]">
    <!-- GSAP Cinematic Product Intro Showcase Overlay -->
    <transition name="fade">
      <IntroShowcase
        v-if="showIntro"
        @enter="showIntro = false"
        @open-auth="isAuthOpen = true"
      />
    </transition>

    <!-- Main Workspace Application -->
    <div v-show="!showIntro" class="flex flex-col min-h-screen">
      <!-- Header -->
      <Header
        :active-tab="activeTab"
        :selected-marketplace="selectedMarketplace"
        :selected-asin="currentTask?.asin ?? ''"
        :selected-title="report?.product.title ?? ''"
        :is-agent-running="isAgentRunning"
        :current-user="currentUser"
        :known-asins="tasks.map(t => ({ asin: t.asin, marketplace: t.marketplace }))"
        @update:active-tab="activeTab = $event"
        @update:selected-marketplace="selectedMarketplace = $event"
        @select-asin="handleSelectAsin"
        @open-auth="isAuthOpen = true"
        @open-intro="showIntro = true"
        @logout="handleLogout"
      />

      <!-- Demo Mode Banner：演示数据集必须诚实标注（任务 §32） -->
      <div
        v-if="report?.source_mode === 'DEMO_DATASET'"
        class="w-full bg-amber-500/10 border-b border-amber-500/20 text-amber-300 text-[11px] font-mono text-center py-1.5 px-4"
      >
        ⚠ {{ t('app.demoDatasetBanner') }}
      </div>

      <!-- Main Workspace Container -->
      <main class="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex-1 w-full">
        <transition name="fade" mode="out-in">
          <div :key="activeTab">
            <DashboardTab
              v-if="activeTab === 'dashboard'"
              :current-task="currentTask"
              :report="report"
              :clusters="clusters"
              :all-tasks="tasks"
              :backend-env="backendEnv"
              @navigate="activeTab = $event"
              @select-task="handleSelectTask"
              @start-new-task="activeTab = 'agent'"
            />

            <AgentWorkflowTab
              v-else-if="activeTab === 'agent'"
              :current-task="currentTask"
              :project-id="projectId"
              @task-created="handleTaskCreated"
              @task-finished="handleTaskFinished"
            />

            <VocClusterTab
              v-else-if="activeTab === 'voc'"
              :clusters="clusters"
              @view-cluster-evidence="handleViewClusterEvidence"
            />

            <DualColumnProposalsTab
              v-else-if="activeTab === 'proposals'"
              :physical-proposals="productProposals"
              :packaging-proposals="packagingProposals"
              @view-evidence="handleViewProposalEvidence"
              @export-rfc="handleExportRfc"
            />

            <FinancialVetoTab
              v-else-if="activeTab === 'financial'"
            />
          </div>
        </transition>
      </main>

      <!-- Slide-in Evidence Drawer -->
      <EvidenceDrawer
        :is-open="isDrawerOpen"
        :target-title="drawerTitle"
        :target="drawerTarget"
        :workspace="currentTask && report ? { taskId: currentTask.taskId, itemId: currentTask.itemId, reportId: report.report_id } : null"
        @close="isDrawerOpen = false"
      />

      <!-- Auth Modal (Login / Register) -->
      <AuthModal
        :is-open="isAuthOpen"
        @close="isAuthOpen = false"
        @login-success="handleLoginSuccess"
      />

      <!-- Toast Notification -->
      <transition name="toast">
        <div
          v-if="toastMessage"
          class="fixed bottom-6 right-6 z-50 px-3.5 py-2 rounded-lg bg-[#191a1b] border border-[rgba(255,255,255,0.12)] text-xs font-mono text-[#f7f8f8] shadow-lg"
        >
          {{ toastMessage }}
        </div>
      </transition>

      <!-- Quiet Footer -->
      <footer class="border-t border-[rgba(255,255,255,0.06)] py-6 text-center text-xs font-mono text-[#5e626e]">
        <div class="max-w-6xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-2">
          <span>InsightX · Cross-Border AI Market-Insight & Dynamic Decision Engine</span>
          <span>Vue 3.5 · Vite 8 · GSAP 3 · Tailwind CSS · LangGraph</span>
        </div>
      </footer>
    </div>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.toast-enter-active,
.toast-leave-active {
  transition: all 0.2s ease;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateY(8px);
}
</style>

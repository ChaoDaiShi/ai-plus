<script setup lang="ts">
import {
  CameraOff,
  ExternalLink,
} from 'lucide-vue-next';
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import type { PainPointCluster } from '../types';

defineProps<{
  clusters: PainPointCluster[];
}>();

const emit = defineEmits<{
  (e: 'viewClusterEvidence', cluster: PainPointCluster): void;
}>();

const { t } = useI18n();

const activeSubTab = ref<'clusters' | 'visual'>('clusters');
</script>

<template>
  <div class="space-y-6">
    <!-- Top Header & Sub-View Switcher -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[rgba(255,255,255,0.06)]">
      <div>
        <h1 class="text-xl font-medium tracking-tight text-[#f7f8f8]">
          {{ t('voc.title') }}
        </h1>
        <p class="text-xs text-[#8a8f98] mt-1">
          {{ t('voc.subtitle') }}
        </p>
      </div>

      <!-- Segmented Control for Sub-Views -->
      <div class="flex items-center bg-[rgba(255,255,255,0.03)] p-0.5 rounded-lg border border-[rgba(255,255,255,0.07)]">
        <button
          @click="activeSubTab = 'clusters'"
          :class="[
            'px-3 py-1.5 rounded-md text-xs font-medium transition-colors',
            activeSubTab === 'clusters'
              ? 'bg-[rgba(255,255,255,0.08)] text-[#f7f8f8]'
              : 'text-[#8a8f98] hover:text-[#f7f8f8]'
          ]"
        >
          {{ t('voc.clustersTab') }}
        </button>
        <button
          @click="activeSubTab = 'visual'"
          :class="[
            'px-3 py-1.5 rounded-md text-xs font-medium transition-colors flex items-center gap-1.5',
            activeSubTab === 'visual'
              ? 'bg-[rgba(255,255,255,0.08)] text-[#f7f8f8]'
              : 'text-[#8a8f98] hover:text-[#f7f8f8]'
          ]"
        >
          {{ t('voc.visualTab') }}
          <span class="text-[9px] font-mono px-1 py-0.5 rounded bg-amber-500/15 border border-amber-500/25 text-amber-300">P1</span>
        </button>
      </div>
    </div>

    <!-- View 1: Pain Point Clusters (Clean, spacious list) -->
    <div v-if="activeSubTab === 'clusters'" class="space-y-4">
      <div class="ln-surface divide-y divide-[rgba(255,255,255,0.05)] overflow-hidden">
        <div
          v-for="(cluster, idx) in clusters"
          :key="cluster.id"
          class="p-5 hover:bg-[rgba(255,255,255,0.02)] transition-colors space-y-3"
        >
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div class="flex items-center gap-3 flex-wrap">
              <span class="text-xs font-mono text-[#5e626e]">0{{ idx + 1 }}</span>
              <span class="text-sm font-medium text-[#f7f8f8]">{{ cluster.name }}</span>
              <span class="text-[11px] font-mono px-2 py-0.5 rounded bg-[rgba(255,255,255,0.04)] text-[#8a8f98] border border-[rgba(255,255,255,0.06)]">
                {{ cluster.categoryLabel }}
              </span>
            </div>

            <div class="flex items-center gap-4 text-xs font-mono text-[#8a8f98]">
              <span>{{ t('dashboard.frequency') }}: <strong class="text-[#f7f8f8]">{{ cluster.frequency }}</strong></span>
              <span>{{ t('voc.share') }}: {{ (cluster.shareRatio * 100).toFixed(1) }}%</span>
              <span class="text-amber-400">{{ t('dashboard.rating') }}: {{ cluster.severity }}</span>
            </div>
          </div>

          <!-- Customer Voice -->
          <p class="text-xs text-[#8a8f98] pl-6 leading-relaxed">
            "{{ cluster.sampleQuote }}"
          </p>
          <p v-if="cluster.translatedQuote" class="text-xs text-zinc-300 pl-6 leading-relaxed">
            ↳ {{ cluster.translatedQuote }}
          </p>
          <p v-if="cluster.severityReason" class="text-[11px] text-[#5e626e] pl-6 font-mono">
            {{ t('voc.severityReason') }}: {{ cluster.severityReason }}
          </p>

          <div class="pl-6 pt-1 flex items-center justify-between">
            <span class="text-[11px] font-mono text-[#5e626e]">
              {{ t('voc.photoCount', { count: cluster.photoCount }) }}
            </span>
            <button
              @click="emit('viewClusterEvidence', cluster)"
              class="text-xs font-mono text-[#7170ff] hover:text-[#828fff] flex items-center gap-1 transition-colors"
            >
              <span>{{ t('common.viewEvidence') }} ({{ cluster.evidenceCount }})</span>
              <ExternalLink class="w-3 h-3" />
            </button>
          </div>
        </div>

        <div v-if="clusters.length === 0" class="p-8 text-center text-xs text-[#5e626e] font-mono">
          {{ t('dashboard.noClusters') }}
        </div>
      </div>
    </div>

    <!-- View 2: P1 视觉取证占位（P0 无图片证据，如实标注） -->
    <div v-else class="ln-surface p-10 flex flex-col items-center justify-center text-center space-y-3">
      <CameraOff class="w-8 h-8 text-[#5e626e]" />
      <p class="text-sm font-medium text-[#8a8f98]">{{ t('voc.visualP1Title') }}</p>
      <p class="text-xs text-[#5e626e] max-w-sm leading-relaxed">
        {{ t('voc.visualP1Desc') }}
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  Calendar,
  ExternalLink,
  X,
} from 'lucide-vue-next';
import { computed, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { getEvidence } from '../api/reports';
import type { EvidenceItemDto } from '../types/api';

const props = defineProps<{
  isOpen: boolean;
  targetTitle: string;
  target: { clusterId?: string; proposalId?: string } | null;
  workspace: { taskId: string; itemId: string; reportId: string } | null;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const { t } = useI18n();

const reviews = ref<EvidenceItemDto[]>([]);
const totalCount = ref(0);
const loading = ref(false);
const loadError = ref<string | null>(null);
const ratingFilter = ref<number | null>(null);

const filteredReviews = computed(() => {
  if (ratingFilter.value === null) return reviews.value;
  return reviews.value.filter(r => r.rating === ratingFilter.value);
});

async function loadEvidence() {
  if (!props.workspace || !props.target) return;
  loading.value = true;
  loadError.value = null;
  try {
    const page = await getEvidence(props.workspace.taskId, props.workspace.itemId, {
      reportId: props.workspace.reportId,
      clusterId: props.target.clusterId,
      proposalId: props.target.proposalId,
      limit: 50,
    });
    reviews.value = page.items;
    totalCount.value = page.total;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

watch(
  () => [props.isOpen, props.target],
  ([open]) => {
    if (open) {
      reviews.value = [];
      ratingFilter.value = null;
      void loadEvidence();
    }
  },
);
</script>

<template>
  <!-- Backdrop -->
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm transition-opacity"
    @click="emit('close')"
  />

  <!-- Right Slide Drawer -->
  <aside
    :class="[
      'fixed top-0 right-0 bottom-0 z-50 w-full max-w-lg bg-[#0c0d0e] border-l border-[rgba(255,255,255,0.08)] p-6 shadow-2xl transition-transform duration-200 ease-out flex flex-col justify-between overflow-hidden',
      isOpen ? 'translate-x-0' : 'translate-x-full'
    ]"
  >
    <!-- Header -->
    <div class="space-y-3 pb-4 border-b border-[rgba(255,255,255,0.06)]">
      <div class="flex items-center justify-between">
        <h2 class="text-sm font-medium text-[#f7f8f8]">{{ t('drawer.title') }}</h2>
        <button
          @click="emit('close')"
          class="p-1 text-[#8a8f98] hover:text-[#f7f8f8] transition-colors"
        >
          <X class="w-4 h-4" />
        </button>
      </div>

      <div class="text-xs text-[#8a8f98] line-clamp-1 font-mono">
        {{ t('drawer.related') }} <span class="text-[#f7f8f8]">{{ targetTitle }}</span>
      </div>

      <!-- Rating Filter -->
      <div class="flex items-center gap-1.5 pt-1 text-xs font-mono">
        <span class="text-[#5e626e] text-[11px]">{{ t('drawer.ratingFilter') }}</span>
        <button
          @click="ratingFilter = null"
          :class="[
            'px-2 py-0.5 rounded text-[11px] transition-colors',
            ratingFilter === null ? 'bg-[rgba(255,255,255,0.1)] text-[#f7f8f8]' : 'text-[#8a8f98] hover:text-[#f7f8f8]'
          ]"
        >
          {{ t('drawer.all') }}
        </button>
        <button
          v-for="star in [1, 2, 3]"
          :key="star"
          @click="ratingFilter = star"
          :class="[
            'px-2 py-0.5 rounded text-[11px] transition-colors',
            ratingFilter === star ? 'bg-[rgba(255,255,255,0.1)] text-[#f7f8f8]' : 'text-[#8a8f98] hover:text-[#f7f8f8]'
          ]"
        >
          ★{{ star }}
        </button>
      </div>
    </div>

    <!-- Review List (real backend evidence) -->
    <div class="flex-1 overflow-y-auto py-4 space-y-3 pr-1 scrollbar-thin">
      <div v-if="loading" class="text-xs text-[#8a8f98] font-mono py-8 text-center">
        {{ t('drawer.loading') }}
      </div>
      <div v-else-if="loadError" class="text-xs text-rose-400 font-mono py-8 text-center">
        {{ loadError }}
      </div>
      <div
        v-else-if="filteredReviews.length === 0"
        class="text-xs text-[#5e626e] font-mono py-8 text-center"
      >
        {{ t('drawer.empty') }}
      </div>

      <div
        v-for="rev in filteredReviews"
        :key="rev.review_id"
        class="p-3.5 rounded-lg bg-[rgba(255,255,255,0.02)] border border-[rgba(255,255,255,0.05)] space-y-2 text-xs"
      >
        <div class="flex items-center justify-between text-[11px] font-mono text-[#8a8f98]">
          <div class="flex items-center gap-1.5">
            <span class="text-amber-400 font-medium">★ {{ rev.rating ?? '–' }}</span>
            <span class="text-[#5e626e]">· {{ (rev.language ?? 'und').toUpperCase() }}</span>
          </div>
          <div class="flex items-center gap-1 text-[#5e626e]">
            <Calendar class="w-3 h-3" />
            <span>{{ rev.reviewed_at ?? '—' }}</span>
          </div>
        </div>

        <p class="text-[#f7f8f8] leading-relaxed italic text-[11px]">"{{ rev.text }}"</p>
        <p v-if="rev.translation" class="text-zinc-300 text-[11px] pt-1 border-t border-[rgba(255,255,255,0.04)]">
          ↳ {{ rev.translation }}
        </p>

        <div class="flex items-center justify-between text-[10px] font-mono text-[#5e626e]">
          <span class="truncate">{{ rev.source_review_id }}</span>
          <a
            v-if="rev.source_url"
            :href="rev.source_url"
            target="_blank"
            rel="noreferrer"
            class="flex items-center gap-1 text-[#7170ff] hover:text-[#828fff]"
          >
            <span>source</span>
            <ExternalLink class="w-3 h-3" />
          </a>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="pt-3 border-t border-[rgba(255,255,255,0.06)] flex items-center justify-between text-[11px] text-[#5e626e] font-mono">
      <span>{{ t('drawer.totalCount', { count: totalCount }) }}</span>
      <button
        @click="emit('close')"
        class="ln-btn px-3 py-1 text-xs"
      >
        {{ t('common.close') }}
      </button>
    </div>
  </aside>
</template>

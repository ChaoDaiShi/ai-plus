<script setup lang="ts">
import {
  Box,
  Download,
  ExternalLink,
  ShieldQuestion,
  Wrench,
} from 'lucide-vue-next';
import { useI18n } from 'vue-i18n';
import type { ProposalView } from '../types';

defineProps<{
  physicalProposals: ProposalView[];
  packagingProposals: ProposalView[];
}>();

const emit = defineEmits<{
  (e: 'viewEvidence', target: { title: string; proposalId: string; count: number }): void;
  (e: 'exportRfc'): void;
}>();

const { t } = useI18n();
</script>

<template>
  <div class="space-y-6">
    <!-- Top Executive Header -->
    <div class="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-[rgba(255,255,255,0.06)]">
      <div class="space-y-1">
        <h1 class="text-xl font-medium tracking-tight text-[#f7f8f8]">
          {{ t('proposals.title') }}
        </h1>
        <p class="text-xs text-[#8a8f98]">
          {{ t('proposals.subtitle') }}
        </p>
      </div>

      <div class="flex items-center gap-3">
        <!-- P0 财务未评估（禁止假数字，任务 §22） -->
        <div class="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[rgba(255,255,255,0.03)] border border-[rgba(255,255,255,0.08)] text-xs font-mono text-[#8a8f98]">
          <ShieldQuestion class="w-3.5 h-3.5 text-amber-400" />
          <span>{{ t('proposals.financialNotEvaluated') }}</span>
        </div>

        <button
          @click="emit('exportRfc')"
          class="ln-btn px-3 py-1.5 flex items-center gap-1.5"
        >
          <Download class="w-3.5 h-3.5" />
          <span>{{ t('common.export') }}</span>
        </button>
      </div>
    </div>

    <!-- Dual Column Layout: Left Physical vs Right Packaging -->
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 items-start">
      <!-- Left Column: Physical Product Optimization -->
      <div class="space-y-4">
        <div class="flex items-center justify-between pb-2 border-b border-[rgba(255,255,255,0.06)]">
          <div class="flex items-center gap-2">
            <Wrench class="w-4 h-4 text-[#7170ff]" />
            <h2 class="text-xs font-semibold text-[#f7f8f8] uppercase tracking-wider">
              {{ t('proposals.leftTitle') }}
            </h2>
          </div>
          <span class="text-[11px] font-mono text-[#8a8f98]">
            {{ physicalProposals.length }} {{ t('common.items') }}
          </span>
        </div>

        <div class="space-y-3">
          <div
            v-for="prop in physicalProposals"
            :key="prop.id"
            class="ln-surface p-4 space-y-3 hover:border-[rgba(255,255,255,0.12)] transition-colors"
          >
            <span class="text-xs font-medium text-[#f7f8f8] block">{{ prop.title }}</span>

            <!-- Problem -> Solution in clean typography -->
            <div class="space-y-1.5 text-xs text-[#8a8f98] leading-relaxed">
              <p v-if="prop.problem"><strong class="text-zinc-400">{{ t('proposals.originalFlaw') }}</strong>{{ prop.problem }}</p>
              <p><strong class="text-zinc-400">{{ t('proposals.engineeringPlan') }}</strong>{{ prop.action }}</p>
            </div>

            <!-- Expected effect -->
            <div class="p-2 rounded bg-[rgba(0,0,0,0.3)] border border-[rgba(255,255,255,0.05)] text-[11px] font-mono text-zinc-300">
              <span class="text-zinc-500">EFFECT: </span>{{ prop.expectedEffect }}
            </div>

            <!-- Verification required tags -->
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="item in prop.verificationRequired"
                :key="item"
                class="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300"
              >
                ✓ {{ item }}
              </span>
            </div>

            <!-- Footer: Evidence -->
            <div class="flex items-center justify-end text-[11px] font-mono pt-1">
              <button
                @click="emit('viewEvidence', { title: prop.title, proposalId: prop.id, count: prop.evidenceCount })"
                class="text-[#7170ff] hover:text-[#828fff] flex items-center gap-1 transition-colors"
              >
                <span>{{ t('proposals.traceEvidence', { count: prop.evidenceCount }) }}</span>
                <ExternalLink class="w-3 h-3" />
              </button>
            </div>
          </div>

          <div
            v-if="physicalProposals.length === 0"
            class="ln-surface p-6 text-center text-xs text-[#5e626e] font-mono"
          >
            {{ t('proposals.emptyColumn') }}
          </div>
        </div>
      </div>

      <!-- Right Column: Packaging & Logistics Optimization -->
      <div class="space-y-4">
        <div class="flex items-center justify-between pb-2 border-b border-[rgba(255,255,255,0.06)]">
          <div class="flex items-center gap-2">
            <Box class="w-4 h-4 text-emerald-400" />
            <h2 class="text-xs font-semibold text-[#f7f8f8] uppercase tracking-wider">
              {{ t('proposals.rightTitle') }}
            </h2>
          </div>
          <span class="text-[11px] font-mono text-[#8a8f98]">
            {{ packagingProposals.length }} {{ t('common.items') }}
          </span>
        </div>

        <div class="space-y-3">
          <div
            v-for="pkg in packagingProposals"
            :key="pkg.id"
            class="ln-surface p-4 space-y-3 hover:border-[rgba(255,255,255,0.12)] transition-colors"
          >
            <span class="text-xs font-medium text-[#f7f8f8] block">{{ pkg.title }}</span>

            <div class="space-y-1.5 text-xs text-[#8a8f98] leading-relaxed">
              <p v-if="pkg.problem"><strong class="text-zinc-400">{{ t('proposals.shippingFlaw') }}</strong>{{ pkg.problem }}</p>
              <p><strong class="text-zinc-400">{{ t('proposals.packagingPlan') }}</strong>{{ pkg.action }}</p>
            </div>

            <div class="p-2 rounded bg-[rgba(0,0,0,0.3)] border border-[rgba(255,255,255,0.05)] text-[11px] font-mono text-zinc-300">
              <span class="text-zinc-500">EFFECT: </span>{{ pkg.expectedEffect }}
            </div>

            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="item in pkg.verificationRequired"
                :key="item"
                class="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-300"
              >
                ✓ {{ item }}
              </span>
            </div>

            <div class="flex items-center justify-end text-[11px] font-mono pt-1">
              <button
                @click="emit('viewEvidence', { title: pkg.title, proposalId: pkg.id, count: pkg.evidenceCount })"
                class="text-[#7170ff] hover:text-[#828fff] flex items-center gap-1 transition-colors"
              >
                <span>{{ t('proposals.traceEvidence', { count: pkg.evidenceCount }) }}</span>
                <ExternalLink class="w-3 h-3" />
              </button>
            </div>
          </div>

          <div
            v-if="packagingProposals.length === 0"
            class="ln-surface p-6 text-center text-xs text-[#5e626e] font-mono"
          >
            {{ t('proposals.emptyColumn') }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

"""双栏改款建议 Provider（任务 §11-§12）：规则引擎为主，LLM 为可选增强。

RuleBasedProposalProvider 依据簇关键词动态生成 BODY_OPTIMIZATION /
PACKAGING_FULFILLMENT 两栏建议，证据引用全部来自簇内真实评论；
LLMProposalProvider 仅在显式配置 Anthropic Key 时启用，且只消费
Cluster 草稿与真实 evidence，由 evidence_validation 节点兜底校验。
"""

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from app.agent.providers.clustering import ClusterDraft
from app.config import settings

PROPOSAL_PIPELINE_VERSION = "rule-proposal-v1"

_TRACK_BODY = "BODY_OPTIMIZATION"
_TRACK_PACKAGING = "PACKAGING_FULFILLMENT"

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class ProposalDraft:
    """建议草稿（发布时映射为 reform_proposals 行）。"""

    track_type: str  # BODY_OPTIMIZATION | PACKAGING_FULFILLMENT
    title_zh: str
    title_en: str
    problem: str
    recommendation: str
    target_cluster_keys: list[str] = field(default_factory=list)  # 聚类草稿序号键
    expected_effect: str = ""
    cost_level: str = "medium"
    evidence_review_ids: list[str] = field(default_factory=list)


class ProposalProvider(Protocol):
    name: str

    async def generate(
        self, clusters: list[ClusterDraft]
    ) -> list[ProposalDraft]: ...


def _cluster_text(cluster: ClusterDraft) -> str:
    return " ".join([cluster.name_en, cluster.name_zh, *cluster.keywords]).lower()


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    tokens = set(_TOKEN_RE.findall(text))
    return any(word in tokens or word in text for word in words)


_BODY_RULES: list[tuple[tuple[str, ...], str, str, str, str]] = [
    (
        ("broken", "broke", "crack", "cracked", "snap", "snapped", "sheared", "fractured"),
        "承力塑料件结构加强",
        "Reinforce load-bearing plastic parts",
        "评论集中反映承力件（扶手/基座/气压杆座）断裂，属应力集中与壁厚不足问题。",
        "对断裂部位增加壁厚与加强筋，加大根部圆角消除应力集中，承力骨架改用金属嵌件或更高强度材料，并进行载荷寿命验证。",
    ),
    (
        ("wobble", "wobbles", "loose", "loosening", "creaks", "squeaky", "squeak"),
        "连接结构与紧固防松改进",
        "Improve joints and anti-loosening",
        "评论反映连接部位松动、异响，螺纹紧固与配合公差不可靠。",
        "增加防松垫圈/螺纹胶工艺，提高连接件配合精度，对异响部位增加衬垫阻尼。",
    ),
    (
        ("slides", "slide", "sinks", "sliding"),
        "滑动支撑机构锁定改进",
        "Add positive locking to sliding supports",
        "评论反映腰托等滑动支撑仅靠摩擦保持，负载下自行下滑失效。",
        "滑动机构增加卡位/棘齿等正向锁定结构，提高导轨阻尼一致性，并按负载上限做保持力验证。",
    ),
    (
        ("small", "narrow", "short", "tight"),
        "坐面尺寸与人机校核",
        "Resize seat dimensions",
        "评论反映坐面偏小偏窄，高个子用户大腿悬空。",
        "结合目标人群身高分布校核坐宽坐深，评估加大坐面或提供加宽版本。",
    ),
]

_PACKAGING_RULES: list[tuple[tuple[str, ...], str, str, str, str]] = [
    (
        ("box", "carton", "crushed", "shipping", "transit", "courier", "punched", "torn"),
        "外箱强度与缓冲包装升级",
        "Upgrade carton strength and cushioning",
        "评论集中反映外箱压溃、部件顶破纸箱，缓冲与护角不足。",
        "提高外箱耐破等级，重物件增加护角与端部保护套，重排内部固定方式避免部件顶箱。",
    ),
    (
        ("styrofoam", "cushioning", "padding", "loose"),
        "内部缓冲与固定优化",
        "Optimize interior cushioning and fixation",
        "评论反映内部缓冲材料碎裂、部件无固定相互磕碰。",
        "替换易碎发泡为蜂窝纸板定型嵌件，按件分格固定，减少运输磨损与划伤。",
    ),
    (
        ("missing", "screw", "screws", "washers", "allen", "wheel"),
        "配件包核对与分装防漏",
        "Hardware kit verification",
        "评论反映五金件缺件、缺装配工具，直接影响首装体验。",
        "装配前增加配件称重复核工位，五金包按安装步骤分袋标号，附装配工具与备件。",
    ),
    (
        ("manual", "instructions", "diagram", "confusing", "assembly", "step"),
        "说明书防呆与分步指引",
        "Foolproof assembly instructions",
        "评论反映图示不清、螺丝混淆导致错装。",
        "说明书采用分步编号与实物等大图示，五金袋与步骤一一对应，附扫码装配视频。",
    ),
    (
        ("smell", "odor", "odor"),
        "材料异味改善与出厂散味",
        "Reduce material odor",
        "评论反映开箱化学异味明显，小空间持续数日。",
        "评估更换低气味海绵/胶粘剂，增加出厂前散味工序，包装增加透气孔与气味说明卡。",
    ),
]


class RuleBasedProposalProvider:
    """规则引擎：按簇关键词匹配双栏规则；未命中规则的簇不生成建议。"""

    name = "rule_based"

    async def generate(self, clusters: list[ClusterDraft]) -> list[ProposalDraft]:
        proposals: list[ProposalDraft] = []
        for index, cluster in enumerate(clusters):
            key = f"cluster_{index}"
            text = _cluster_text(cluster)
            evidence = cluster.review_ids
            for words, title_zh, title_en, problem, recommendation in _BODY_RULES:
                if _has_any(text, words):
                    proposals.append(
                        ProposalDraft(
                            track_type=_TRACK_BODY,
                            title_zh=f"{title_zh}（{cluster.name_zh}）",
                            title_en=f"{title_en} — {cluster.name_en}",
                            problem=problem,
                            recommendation=recommendation,
                            target_cluster_keys=[key],
                            expected_effect="预期降低该痛点相关差评与退货率（定性预期，需上市后回测验证）",
                            cost_level="medium" if "金属" in recommendation else "low",
                            evidence_review_ids=list(evidence),
                        )
                    )
                    break
            for words, title_zh, title_en, problem, recommendation in _PACKAGING_RULES:
                if _has_any(text, words):
                    proposals.append(
                        ProposalDraft(
                            track_type=_TRACK_PACKAGING,
                            title_zh=f"{title_zh}（{cluster.name_zh}）",
                            title_en=f"{title_en} — {cluster.name_en}",
                            problem=problem,
                            recommendation=recommendation,
                            target_cluster_keys=[key],
                            expected_effect="预期降低运输破损与首装失败率（定性预期，需履约数据验证）",
                            cost_level="low",
                            evidence_review_ids=list(evidence),
                        )
                    )
                    break
        return proposals


class LLMProposalProvider:
    """可选 LLM 增强：仅当配置 ANTHROPIC_API_KEY 时由工厂启用。

    LLM 只消费 Cluster 草稿文本，输出标题/问题描述/建议文案；目标簇与
    evidence_review_ids 由服务端注入，不由模型生成，杜绝虚构引用。
    """

    name = "llm_proposal"

    def __init__(self, api_key: str, base_url: str = "https://api.anthropic.com") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    async def _complete(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{self.base_url}/v1/messages",
                headers={"x-api-key": self.api_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": "claude-sonnet-4-5",
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        return "".join(block.get("text", "") for block in data.get("content", []))

    async def generate(self, clusters: list[ClusterDraft]) -> list[ProposalDraft]:
        rule_proposals = await RuleBasedProposalProvider().generate(clusters)
        if not clusters:
            return rule_proposals
        cluster_lines = "\n".join(
            f"[{key}] {c.name_en} (frequency={c.frequency}, severity={c.severity}): "
            f"keywords={','.join(c.keywords)}"
            for key, c in ((f"cluster_{i}", c) for i, c in enumerate(clusters))
        )
        prompt = (
            "You are an e-commerce product improvement assistant. For each cluster of "
            "customer complaints below, decide whether it warrants a BODY_OPTIMIZATION "
            "or PACKAGING_FULFILLMENT proposal. Reply with one line per proposal in the "
            "exact format: `cluster_key|track|title_zh|title_en|problem_zh|recommendation_zh`. "
            "Only use the given clusters; do not invent evidence.\n\n" + cluster_lines
        )
        try:
            text = await self._complete(prompt)
        except httpx.HTTPError:
            return rule_proposals  # LLM 失败回退规则结果：规则结果本身证据完备
        for line in text.splitlines():
            parts = [p.strip() for p in line.split("|")]
            if len(parts) != 6 or parts[0] not in {
                f"cluster_{i}" for i in range(len(clusters))
            }:
                continue
            key, track, title_zh, title_en, problem, recommendation = parts
            if track not in (_TRACK_BODY, _TRACK_PACKAGING):
                continue
            cluster = clusters[int(key.split("_")[1])]
            rule_proposals.append(
                ProposalDraft(
                    track_type=track,
                    title_zh=title_zh,
                    title_en=title_en,
                    problem=problem,
                    recommendation=recommendation,
                    target_cluster_keys=[key],
                    expected_effect="LLM 定性预期，需验证后采用",
                    cost_level="medium",
                    evidence_review_ids=list(cluster.review_ids),
                )
            )
        return rule_proposals


def get_proposal_provider() -> ProposalProvider:
    if settings.anthropic_api_key:
        return LLMProposalProvider(settings.anthropic_api_key)
    return RuleBasedProposalProvider()


def proposal_rule_metadata() -> dict[str, Any]:
    return {"provider": get_proposal_provider().name, "version": PROPOSAL_PIPELINE_VERSION}

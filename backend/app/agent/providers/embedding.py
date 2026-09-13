"""向量化 Provider（任务 §8）：确定性测试向量与可选 bge-m3 两个实现。

DeterministicTestEmbeddingProvider：1024 维、逐文本确定（同输入同向量）、
不访问网络、不依赖批量构成——基于去停用词词袋 + sha256 稳定哈希投影 + L2 归一，
主题词重合的文本余弦相近，可支撑离线聚类演示与 CI。
BgeM3EmbeddingProvider：需 `uv sync --extra embedding` 安装 FlagEmbedding，
未安装时明确报错，绝不静默换成随机向量。
"""

import hashlib
import math
import re
from typing import Protocol

from app.config import settings

EMBEDDING_DIM = 1024
TEST_MODEL_REVISION = "deterministic-test-v1"
BGE_MODEL_REVISION = "bge-m3"

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# 与 P0 演示语料配套的最小停用词表：仅用于向量投影，不影响原文。
_STOPWORDS = frozenset(
    """
    a an and are as at be been but by can did do for from get got had has have
    he her his how i if in into is it its just like me my no not of on or our
    out over she so some than that the their them then there these they this
    to too up us was we were what when which who will with would you your
    after all also any because before being both day days did does down each
    even every few first got here him how into keep last let made make many
    might more much need never now off once one only other really same see
    seems still such take took two use used using very week weeks well went
    """.split()
)

# 领域词表：P0 演示语料的主题词基向量（前 LEXICON_DIM 维，词表序即维度序）。
# 词表外的词经稳定哈希投影到背景区（低权重），保证同主题文本余弦相近。
_LEXICON: tuple[str, ...] = (
    """
    armrest armrests broken broke crack cracked snapping snapped snap
    sheared fractured fracture lumbar support cushion slides slide sliding sinks
    sinking knob rail wobble wobbles wobbly loose loosening creaks creak squeak
    squeaks squeaky wheel wheels caster casters stem scuff marks floor
    box carton packaging shipping transit courier crushed crush torn
    damaged damage punched hole corner edges styrofoam cushioning padding wrap
    manual instructions diagram step steps confusing unlabeled assembly assemble
    assembled smell smells odor chemical solvent foam aired missing screw screws
    washers allen tool bag hardware small narrow short tight seat backrest
    cylinder gas lift sinking base leg legs tilt headrest bolt bolts thread
    height adjustment bracket mount mounts mesh recline comfortable
    sturdy delivery quality plastic metal price value
    """
).split()
LEXICON_DIM = len(_LEXICON)
_LEXICON_INDEX = {word: index for index, word in enumerate(_LEXICON)}
_BACKGROUND_OFFSET = 128
_BACKGROUND_DIMS = EMBEDDING_DIM - _BACKGROUND_OFFSET
_LEXICON_WEIGHT = 1.0
_BACKGROUND_WEIGHT = 0.25


def tokenize_for_embedding(text: str) -> list[str]:
    """小写化取词、去停用词；标题由调用方重复计入以强化主题信号。"""
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOPWORDS]


class EmbeddingProvider(Protocol):
    model_revision: str
    dim: int

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicTestEmbeddingProvider:
    """确定性测试向量：领域词表基向量 + 稳定哈希背景投影。

    1024 维、逐文本确定（同输入同向量、与批量无关）、不访问网络；
    主题词共享的文本余弦相近，支撑离线聚类演示与 CI。
    """

    model_revision = TEST_MODEL_REVISION
    dim = EMBEDDING_DIM

    def _slot(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        return _BACKGROUND_OFFSET + int.from_bytes(digest[:8], "big") % _BACKGROUND_DIMS

    def _sign(self, token: str) -> float:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        return 1.0 if digest[8] % 2 == 0 else -1.0

    def embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = tokenize_for_embedding(text)
        if not tokens:
            # 空文本退化为固定单位向量（调用方正常不会传空文本）。
            vector[0] = 1.0
            return vector
        counts: dict[str, int] = {}
        for token in tokens:
            counts[token] = counts.get(token, 0) + 1
        for token, count in counts.items():
            weight = 1.0 + math.log(count)
            lexicon_index = _LEXICON_INDEX.get(token)
            if lexicon_index is not None:
                vector[lexicon_index] += _LEXICON_WEIGHT * weight
            else:
                vector[self._slot(token)] += _BACKGROUND_WEIGHT * self._sign(token) * weight
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            return vector
        return [value / norm for value in vector]

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_one(text) for text in texts]


class BgeM3EmbeddingProvider:
    """bge-m3 真实向量（1024 维）。模型依赖为可选 extra，按需加载。"""

    model_revision = BGE_MODEL_REVISION
    dim = EMBEDDING_DIM

    def __init__(self) -> None:
        try:
            from FlagEmbedding import BGEM3FlagModel  # noqa: PLC0415 — 可选依赖
        except ImportError as exc:
            raise RuntimeError(
                "bge-m3 需要 embedding 可选依赖：uv sync --extra embedding"
            ) from exc
        self._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        result = self._model.encode(texts, batch_size=16, max_length=1024)
        dense = result["dense_vecs"]
        return [row.tolist() for row in dense]


def get_embedding_provider() -> EmbeddingProvider:
    if settings.embedding_provider == "deterministic":
        return DeterministicTestEmbeddingProvider()
    if settings.embedding_provider == "bge_m3":
        return BgeM3EmbeddingProvider()
    raise RuntimeError(f"未知 EMBEDDING_PROVIDER：{settings.embedding_provider}")

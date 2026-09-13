"""embedding Provider 测试（任务 §26-C）：1024 维、确定性、批量、主题语义。"""

import asyncio

from app.agent.providers.embedding import (
    EMBEDDING_DIM,
    BgeM3EmbeddingProvider,
    DeterministicTestEmbeddingProvider,
    get_embedding_provider,
)


def test_dims_and_revision():
    provider = DeterministicTestEmbeddingProvider()
    assert provider.dim == EMBEDDING_DIM == 1024
    assert provider.model_revision == "deterministic-test-v1"


def test_deterministic_same_input_same_vector():
    provider = DeterministicTestEmbeddingProvider()
    a = asyncio.run(provider.embed(["The armrest snapped after two weeks"]))
    b = asyncio.run(provider.embed(["The armrest snapped after two weeks"]))
    assert a[0] == b[0]


def test_batch_count_preserved():
    provider = DeterministicTestEmbeddingProvider()
    texts = ["ok", "armrest broke", "box arrived crushed", "lovely chair"]
    vectors = asyncio.run(provider.embed(texts))
    assert len(vectors) == len(texts)
    assert all(len(v) == 1024 for v in vectors)


def test_unit_norm():
    provider = DeterministicTestEmbeddingProvider()
    vector = provider.embed_one("The lumbar support slides down")
    norm = sum(x * x for x in vector) ** 0.5
    assert abs(norm - 1.0) < 1e-9


def test_theme_texts_closer_than_unrelated():
    provider = DeterministicTestEmbeddingProvider()

    def cosine(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    a = provider.embed_one("The armrest snapped and cracked after two weeks")
    b = provider.embed_one("Broken armrest cracked at the mount")
    c = provider.embed_one("Box arrived crushed, packaging torn in shipping")
    assert cosine(a, b) > cosine(a, c)


def test_factory_deterministic_default():
    provider = get_embedding_provider()
    assert isinstance(provider, DeterministicTestEmbeddingProvider)


def test_bge_m3_requires_extra(monkeypatch):
    """未安装可选依赖时明确报错，禁止静默降级。"""
    provider = BgeM3EmbeddingProvider.__new__(BgeM3EmbeddingProvider)
    import pytest

    with pytest.raises(RuntimeError, match="embedding"):
        provider.__init__()

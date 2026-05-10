"""HTTP-mocked tests for MistralProvider.embed() — only Mistral implements
embeddings in v1; bakeoff models are generation-only."""

from __future__ import annotations

import httpx
import respx

from nl_sql.llm.providers import EmbedRequest
from nl_sql.llm.providers.mistral import MistralProvider


def _embedding_payload(model: str, vectors: list[list[float]]) -> dict[str, object]:
    return {
        "id": "embd-test",
        "object": "list",
        "model": model,
        "data": [
            {"object": "embedding", "index": i, "embedding": vec}
            for i, vec in enumerate(vectors)
        ],
        "usage": {"prompt_tokens": 4, "total_tokens": 4},
    }


@respx.mock
def test_mistral_embed_returns_vectors() -> None:
    route = respx.post("https://api.mistral.ai/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json=_embedding_payload("mistral-embed", [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]),
        )
    )
    provider = MistralProvider(api_key="test-key")

    response = provider.embed(EmbedRequest(texts=["alpha", "beta"]))

    assert route.called
    assert response.model == "mistral-embed"
    assert len(response.vectors) == 2
    assert response.vectors[0] == [0.1, 0.2, 0.3]
    assert response.vectors[1] == [0.4, 0.5, 0.6]

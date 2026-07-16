class FakeEmbeddingProvider:
    """Deterministic stand-in for a real embedding service: maps known
    strings to fixed vectors so ranking order is verifiable offline."""

    VECTORS = {
        "kubernetes rollout": (1.0, 0.0, 0.0),
        "led a kubernetes migration": (0.9, 0.1, 0.0),
        "baked bread for a bakery": (0.0, 0.0, 1.0),
    }

    def __init__(self):
        self.calls: list[str] = []

    def embed(self, text: str):
        self.calls.append(text)
        return self.VECTORS[text]

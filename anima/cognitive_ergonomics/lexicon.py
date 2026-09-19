"""cognitive_ergonomics.lexicon — the word lists the deterministic metrics score against (pure data).

These are conservative, hand-curated lists. The point is reproducibility: the same text always scores
the same way, with no model and no randomness.
"""
from __future__ import annotations

# Specialist / internal terms a non-expert reader may not follow. Kept lowercase; matched whole-word.
JARGON = frozenset({
    # AI / ML
    "embedding", "embeddings", "token", "tokens", "tokenizer", "logits", "softmax", "inference",
    "quantization", "quantized", "latency", "throughput", "parameter", "parameters", "hyperparameter",
    "vector", "vectors", "cosine", "centroid", "gradient", "backpropagation", "transformer", "attention",
    "perplexity", "corpus", "distillation", "fine-tune", "finetune", "checkpoint", "heuristic",
    # systems / software
    "idempotent", "concurrency", "mutex", "deadlock", "serialization", "deserialize", "schema",
    "endpoint", "middleware", "daemon", "kernel", "buffer", "cache", "hash", "regex", "stdout",
    "stderr", "async", "coroutine", "thread", "subprocess", "stack-trace", "traceback", "instantiate",
    "polymorphism", "encapsulation", "recursion", "monad", "closure",
    # internal-Vera vocabulary
    "lerf", "mri", "quarantine", "provenance", "invariant", "telemetry", "substrate", "organ",
    "consolidation", "self-narrative", "epistemic", "groundedness", "syntopical",
})

# Hedge / vagueness words — too many of these make an answer feel non-committal.
HEDGES = frozenset({
    "maybe", "perhaps", "possibly", "probably", "might", "could", "seems", "appears", "somewhat",
    "kind of", "sort of", "i think", "i guess", "i believe", "presumably", "arguably", "roughly",
    "more or less", "to some extent", "fairly", "relatively", "basically", "essentially", "actually",
})

# Acronyms that are common enough not to flag as 'unexplained'.
ACRONYM_OK = frozenset({
    "AI", "OK", "URL", "PDF", "API", "USA", "UK", "ID", "FAQ", "CPU", "GPU", "RAM", "OS", "UI", "UX",
    "HTTP", "HTTPS", "JSON", "HTML", "CSS", "USB", "PIN", "SMS", "GPS", "PDF", "FYI", "ASAP", "DIY",
    "AM", "PM", "TV", "CEO", "ETA", "Q&A", "I", "A",
})

# A small syllable-exception table keeps the readability proxy honest on common irregulars.
SYLLABLE_EXCEPTIONS = {
    "the": 1, "every": 2, "different": 3, "business": 2, "people": 2, "little": 2, "evening": 2,
    "interesting": 3, "comfortable": 3, "vegetable": 3, "simile": 3,
}

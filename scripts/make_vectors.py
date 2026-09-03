#!/usr/bin/env python3
"""
Generate per-model control vectors — one .gguf per personality dial — using
`repeng`. Run this ON THE MAC; it needs the model and a few minutes of compute.

It produces files named exactly as anima/dials.py expects (warmth.gguf, edge.gguf,
…) in $ANIMA_VECTOR_DIR (default .anima/vectors), so the llama.cpp brain picks
them up automatically and the dials start steering the model sub-verbally.

REQUIREMENTS (honest):
  * pip install repeng transformers torch
  * The model in HUGGING FACE / transformers format (not GGUF). repeng reads
    hidden states from a transformers model. Use the same weights as your GGUF
    so the vectors are valid for the GGUF you serve in llama.cpp, e.g.
    Sao10K/L3-8B-Stheno-v3.2. Set it with MODEL=… .
  * Apple Silicon: it will use MPS if available; CPU works but is slower.

A control vector is just the averaged difference in the model's hidden state
between saying something one way (the "+" persona) and the opposite ("-" persona),
across many contrastive pairs. That difference, per layer, IS the vector.

  MODEL=Sao10K/L3-8B-Stheno-v3.2 python3 scripts/make_vectors.py
  MODEL=… python3 scripts/make_vectors.py warmth edge      # just these axes
"""
import os
import sys

# Each axis -> (positive persona adjectives, negative persona adjectives). These
# describe the +end and -end of the dial; repeng turns them into the direction.
CONTRASTS = {
    "warmth":      (["warm", "affectionate", "tender", "caring"],
                    ["cold", "detached", "aloof", "clinical"]),
    "edge":        (["blunt", "sardonic", "sharp-tongued", "biting"],
                    ["gentle", "soft-spoken", "soothing", "mild"]),
    "playfulness": (["playful", "teasing", "witty", "mischievous"],
                    ["serious", "solemn", "earnest", "matter-of-fact"]),
    "flirtiness":  (["flirtatious", "seductive", "suggestive", "coy"],
                    ["platonic", "professional", "reserved", "chaste"]),
    "directness":  (["blunt", "terse", "direct", "to-the-point"],
                    ["rambling", "circuitous", "hedging", "long-winded"]),
    "openness":    (["uninhibited", "explicit", "unfiltered", "candid"],
                    ["prudish", "guarded", "euphemistic", "evasive"]),
    "verbosity":   (["verbose", "expansive", "elaborate", "detailed"],
                    ["terse", "laconic", "brief", "minimal"]),
    "melancholy":  (["melancholic", "wistful", "somber", "brooding"],
                    ["cheerful", "upbeat", "bright", "sunny"]),
}

# A small bank of neutral continuations; repeng truncates these at many points and
# prefixes each with the +/- persona, so the only thing that varies is the trait.
SUFFIXES = [
    "I think that", "Tell me about", "When I consider the situation, I",
    "The thing about today is", "Honestly, what I want to say is",
    "Let me describe how", "It occurs to me that", "Right now I feel like",
    "The way I see it,", "What matters here is",
]


def main(argv):
    try:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer
        from repeng import ControlVector, ControlModel, DatasetEntry
    except Exception as e:                                    # pragma: no cover
        sys.exit(f"Missing deps ({e}). Run: pip install repeng transformers torch")

    model_id = os.environ.get("MODEL")
    if not model_id:
        sys.exit("Set MODEL=<hf model id> (the transformers weights of your GGUF).")
    out_dir = os.environ.get("ANIMA_VECTOR_DIR", os.path.join(".anima", "vectors"))
    os.makedirs(out_dir, exist_ok=True)
    axes = [a for a in argv if a in CONTRASTS] or list(CONTRASTS)

    device = ("mps" if torch.backends.mps.is_available()
              else "cuda" if torch.cuda.is_available() else "cpu")
    print(f"Loading {model_id} on {device} …")
    tok = AutoTokenizer.from_pretrained(model_id)
    tok.pad_token_id = tok.pad_token_id or tok.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(
        model_id, torch_dtype=torch.float16).to(device)
    # Steer the middle-to-late layers (where persona lives), skipping the very ends.
    n = model.config.num_hidden_layers
    layers = list(range(max(1, n // 4), n - 1))
    cmodel = ControlModel(model, layers)

    def dataset(pos_adjs, neg_adjs):
        rows = []
        for suf in SUFFIXES:
            toks = tok.tokenize(suf)
            for i in range(1, len(toks) + 1):                # truncations
                frag = tok.convert_tokens_to_string(toks[:i])
                for p, ngv in zip(pos_adjs, neg_adjs):
                    tmpl = f"[INST] Act extremely {{}}. [/INST] {frag}"
                    rows.append(DatasetEntry(positive=tmpl.format(p),
                                             negative=tmpl.format(ngv)))
        return rows

    for axis in axes:
        pos, neg = CONTRASTS[axis]
        print(f"  training '{axis}' …")
        cv = ControlVector.train(cmodel, tok, dataset(pos, neg))
        path = os.path.join(out_dir, f"{axis}.gguf")
        cv.export_gguf(path)
        print(f"  ✓ {path}")
    print(f"Done. {len(axes)} vectors in {out_dir}. "
          f"Switch the brain to llama.cpp and the dials will steer the model.")


if __name__ == "__main__":
    main(sys.argv[1:])

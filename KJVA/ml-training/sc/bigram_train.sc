// SUPER C — Character-level Bigram Language Model, training from scratch.
//
// Everything here is SUPER C. No Python. No MLX. Runs on the SUPER C
// bootstrap interpreter at bootstrap/superc_bootstrap.py.
//
// Training:
//   python bootstrap/superc_bootstrap.py \
//     ml-training/sc/bigram_train.sc
//
// Model:
//   - Vocabulary: printable ASCII (95 chars) + newline (ID 95) + <unk> (ID 96)
//   - Parameter: single weight matrix W of shape [V, V] stored flat in a list
//   - forward(prev) -> softmax(W[prev, :])
//   - loss = -log(probs[target])
//   - gradient: grad[j] = probs[j] - (1 if j==target else 0)
//   - update: W[prev*V + j] -= lr * grad[j]
//
// Corpus:
//   ml-training/sc/corpus.txt
//   (copy or generate a local corpus before running this long training artifact)

print("=== SUPER C Bigram LM — Training from Scratch ===");

// ---------------- Config ----------------
comptime {
    const V         = 97;          // 95 printable ASCII + newline + <unk>
    const CORPUS    = "ml-training/sc/corpus.txt";
    const SEED      = 42;
    const LR        = 0.10;
    const EPOCHS    = 3;
    const MAX_CHARS = 200000;      // subset for reasonable runtime
    const LOG_EVERY = 5000;
    const OUT_WEIGHTS = "ml-training/sc/weights_bigram.txt";
}

print("Vocab size V    = " + str(V));
print("Corpus path     = " + CORPUS);
print("Learning rate   = " + str(LR));
print("Epochs          = " + str(EPOCHS));
print("Max chars/epoch = " + str(MAX_CHARS));
print("");

// ---------------- Tokenizer ----------------
// Map a character to a vocabulary ID in [0, V-1].
// 0..94   = printable ASCII 32..126 (space to tilde)
// 95      = newline
// 96      = <unk> (any other byte)
fn char_to_id(c: str) -> int {
    let code = char_code(c);
    if code == 10 { return 95; }             // newline
    if code >= 32 { if code <= 126 { return code - 32; } }
    return 96;                                // unk
}

fn id_to_char(i: int) -> str {
    if i == 95 { return "\n"; }
    if i == 96 { return "?"; }                // unk rendered as ?
    if i >= 0  { if i < 95 { return char_from(i + 32); } }
    return "?";
}

// ---------------- Model parameters ----------------
// W is a flat list of V*V floats. Linear-probed indexing by (prev*V + j).
// Initialized from small Gaussian-ish jitter using the bootstrap's random().
let W = [];
let W_size = V * V;
let i = 0;
while i < W_size {
    // tiny random init: random() returns [0,1); center on zero, scale down.
    W = W + [(random() - 0.5) * 0.02];
    i = i + 1;
}
print("Initialized W: " + str(W_size) + " floats");

// ---------------- Forward + Loss ----------------
// Returns list of V probabilities, given previous char id.
fn forward(prev: int) -> list {
    let base = prev * V;
    // numerical stability: subtract max before exp
    let max_logit = W[base];
    let j = 1;
    while j < V {
        let v = W[base + j];
        if v > max_logit { max_logit = v; }
        j = j + 1;
    }
    // compute exps + sum
    let exps = [];
    let total = 0.0;
    j = 0;
    while j < V {
        let e = exp(W[base + j] - max_logit);
        exps = exps + [e];
        total = total + e;
        j = j + 1;
    }
    // normalize
    let probs = [];
    j = 0;
    while j < V {
        probs = probs + [exps[j] / total];
        j = j + 1;
    }
    return probs;
}

fn nll_loss(probs: list, target: int) -> f64 {
    let p = probs[target];
    if p < 0.000000001 { p = 0.000000001; }
    return 0.0 - log(p);
}

// ---------------- Backward + SGD update ----------------
// Gradient of CE wrt logits[j] is (probs[j] - 1[j==target]).
// Gradient wrt W[prev*V + j] = d logits[j] / d W[prev*V + j] * dL/d logits[j]
//                            = 1 * (probs[j] - 1[j==target]).
// Update W[prev*V + j] -= lr * grad[j].
fn step_update(prev: int, probs: list, target: int, lr: f64) {
    let base = prev * V;
    let j = 0;
    while j < V {
        let g = probs[j];
        if j == target { g = g - 1.0; }
        W[base + j] = W[base + j] - lr * g;
        j = j + 1;
    }
}

// ---------------- Data loading ----------------
print("Reading corpus...");
let text = file_read_all(CORPUS);
let n_chars = len(text);
print("  corpus total chars: " + str(n_chars));

let take = n_chars;
if take > MAX_CHARS { take = MAX_CHARS; }
print("  training on first " + str(take) + " chars");
print("");

// Pre-tokenize a slice into a list of ids for fast iteration.
// NOTE: for-in has no iteration cap; while has a 10_000 cap in the bootstrap.
let tokens = [];
let text_slice = slice(text, 0, take);
for ch in text_slice {
    push(tokens, char_to_id(ch));
}
print("Tokenized " + str(len(tokens)) + " chars -> ids");
print("");

// ---------------- Training loop ----------------
let epoch = 0;
let total_loss_ever = 0.0;
let total_steps_ever = 0;
let start_ts = (timestamp() * 1000.0);

// Use for-in range() — no iteration cap (unlike while which caps at 10_000).
let n_pairs = len(tokens) - 1;
for epoch in range(EPOCHS) {
    let loss_sum = 0.0;
    let n_steps = 0;
    let running_loss = 0.0;
    let running_n = 0;

    for t in range(n_pairs) {
        let prev = tokens[t];
        let target = tokens[t + 1];

        let probs = forward(prev);
        let l = nll_loss(probs, target);
        step_update(prev, probs, target, LR);

        loss_sum = loss_sum + l;
        n_steps = n_steps + 1;
        running_loss = running_loss + l;
        running_n = running_n + 1;

        if (n_steps % LOG_EVERY) == 0 {
            let avg_recent = running_loss / (running_n * 1.0);
            let elapsed_s = ((timestamp() * 1000.0) - start_ts) / 1000.0;
            print("  epoch " + str(epoch) + " step " + str(n_steps) +
                  "  loss_recent=" + str(avg_recent) +
                  "  elapsed_s=" + str(elapsed_s));
            running_loss = 0.0;
            running_n = 0;
        }
    }

    let avg_loss = loss_sum / (n_steps * 1.0);
    total_loss_ever = total_loss_ever + loss_sum;
    total_steps_ever = total_steps_ever + n_steps;
    print("=== Epoch " + str(epoch) + " complete. avg_loss=" + str(avg_loss) + " ===");
}

let final_avg = total_loss_ever / (total_steps_ever * 1.0);
let wall_s = ((timestamp() * 1000.0) - start_ts) / 1000.0;
print("");
print("=== Training complete ===");
print("  total_steps     = " + str(total_steps_ever));
print("  final_avg_loss  = " + str(final_avg));
print("  wall_time_s     = " + str(wall_s));
print("  tokens/sec      = " + str(total_steps_ever / wall_s));

// ---------------- Save weights (plain text Tokenless format) ----------------
print("");
print("Saving weights to " + OUT_WEIGHTS);
let fh = file_open(OUT_WEIGHTS, "w");
file_write(fh, "# SUPER C bigram weights (char-level)\n");
file_write(fh, "# V=" + str(V) + " W_size=" + str(W_size) + "\n");
file_write(fh, "# final_avg_loss=" + str(final_avg) + "\n");
let w = 0;
while w < W_size {
    file_write(fh, str(W[w]) + "\n");
    w = w + 1;
}
file_close(fh);
print("Saved " + str(W_size) + " weights.");

// ---------------- Quick generation sample ----------------
print("");
print("=== Generation sample (greedy from 'I') ===");
let seed_char = "I";
let cur = char_to_id(seed_char);
let out = seed_char;
let g = 0;
while g < 120 {
    let probs = forward(cur);
    // greedy: argmax
    let best_j = 0;
    let best_p = probs[0];
    let j = 1;
    while j < V {
        if probs[j] > best_p { best_p = probs[j]; best_j = j; }
        j = j + 1;
    }
    cur = best_j;
    out = out + id_to_char(cur);
    g = g + 1;
}
print(out);
print("");
print("=== DONE ===");

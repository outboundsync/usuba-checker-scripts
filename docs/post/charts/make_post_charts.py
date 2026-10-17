"""Rebuild the post-level charts in ../images from data already in the repo.
Run:  python3 make_post_charts.py   (from any directory)
Inputs: ../data/set2_oneshot_tidy.csv, ../data/set3_feedback_tidy.csv, ../data/set2_key_metrics.csv,
        runs/fixer/README.md numbers (typed below), dell/sweep numbers quoted in draft.md (typed below).
No number is invented: every value is read from the CSVs or copied from the cited file.
"""
import csv, os, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
D = os.path.join(HERE, "..", "data"); IMG = os.path.join(HERE, "..", "images")
BLUE, GREY, DARK, ORANGE, GREEN, RED = "#2a6fdb", "#9a9a9a", "#333333", "#e8a33d", "#2e8b57", "#c0392b"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.titlesize": 11, "axes.titleweight": "bold"})

def load(f):
    out = {}
    for r in csv.DictReader(open(os.path.join(D, f))):
        if r["value"] == "": continue
        lo = float(r["ci_low"]) if r["ci_low"] else None; hi = float(r["ci_high"]) if r["ci_high"] else None
        out[(r["model"], r["exam_set"], r["metric"])] = (float(r["value"]), lo, hi)
    return out
S2 = load("set2_oneshot_tidy.csv"); S3 = load("set3_feedback_tidy.csv")
NAME = {"usuba-run2": "Usuba run 2", "stock-qwen3.5-9b": "Stock Qwen3.5 9B", "gemma-4-26b": "Gemma 4 26B", "qwen3-coder-30b": "Qwen3-Coder 30B",
        "glm-4.7-flash": "GLM 4.7 Flash", "nemotron-3-nano": "Nemotron 3 Nano 30B", "ministral-14b": "Ministral 14B", "llama-3.1-8b": "Llama 3.1 8B"}
CK = S3[("usuba-run2", "dell", "checker_scripts_only_accuracy")]  # 0.773 [0.667-0.853], Wilson
AB = S3[("usuba-run2", "dell", "always_flag_accuracy")][0]
def save(fig, name):
    fig.savefig(os.path.join(IMG, name), dpi=170); plt.close(fig)

# ---------- CHART 1: hero scoreboard ----------
rows = [("gemma-4-26b", S3, "+ Checker loop"), ("stock-qwen3.5-9b", S3, "+ Checker loop"), ("qwen3-coder-30b", S3, "+ Checker loop"),
        ("gemma-4-26b", S2, "one-shot"), ("stock-qwen3.5-9b", S2, "one-shot"), ("usuba-run2", S2, "one-shot"), ("usuba-run2", S3, "+ Checker loop")]
rows.sort(key=lambda r: r[1][(r[0], "dell", "verdict_accuracy")][0])
fig, ax = plt.subplots(figsize=(10, 5.4))
ax.axvspan(CK[1], CK[2], color="#2e8b57", alpha=0.12, lw=0)
ax.axvline(CK[0], color=GREEN, lw=2); ax.axvline(AB, color=GREY, lw=1.5, ls="--")
for i, (m, S, tag) in enumerate(rows):
    v, lo, hi = S[(m, "dell", "verdict_accuracy")]; us = m == "usuba-run2"
    ax.barh(i, v, color=BLUE if us else ("#6b6b6b" if "loop" in tag else GREY), height=0.62)
    ax.errorbar(v, i, xerr=[[v - lo], [hi - v]], color=DARK, capsize=3, lw=1.2)
    ax.text(hi + 0.012, i, f"{v:.2f}", va="center", fontsize=9, fontweight="bold" if us else None)
ax.set_yticks(range(len(rows))); ax.set_yticklabels([f"{NAME[m]}, {t}" for m, _, t in rows])
for tk, r in zip(ax.get_yticklabels(), rows):
    if r[0] == "usuba-run2": tk.set_color(BLUE); tk.set_fontweight("bold")
ax.set_xlim(0, 1.0); ax.set_ylim(-0.6, len(rows) + 1.2)
ax.text(CK[0] - 0.01, len(rows) + 0.15, f"Checker scripts alone, no model: {CK[0]:.3f} [{CK[1]:.3f}-{CK[2]:.3f}]", color=GREEN, ha="right", fontsize=9.5, fontweight="bold", bbox=dict(fc="white", ec="none", pad=1.5))
ax.text(AB - 0.008, len(rows) - 0.35, f"always say 'broken': {AB:.3f}", color="#666", fontsize=8.5, ha="right", va="bottom")
ax.set_xlabel("verdict accuracy on the Dell 75 (whiskers = 95% interval)")
ax.set_title("Dell 75 verdict accuracy: no model beats the Checker scripts alone", loc="left", pad=12)
ax.grid(axis="x", color="#eee"); ax.set_axisbelow(True)
fig.text(0.01, 0.01, "Dell 75 = 75 plugins labelled on real hardware. Checker interval is Wilson; model intervals are bootstrap. Source: docs/post/data/set2_oneshot_tidy.csv, set3_feedback_tidy.csv.", fontsize=7.5, color="#555")
fig.subplots_adjust(left=0.27, right=0.97, top=0.9, bottom=0.14); save(fig, "chart1_dell_scoreboard_hero.png")

# ---------- CHART 2: grader passes vs real passes (runs/fixer/README.md, 'base' row) ----------
rounds = [0, 1, 2, 3]; grader = [5, 8, 12, 13]; real = {0: 4, 3: 4}
fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(rounds, grader, "-o", color=RED, lw=2.4, label="Passes according to the grader")
ax.plot([0, 3], [4, 4], "-s", color=GREEN, lw=2.4, label="Passes that are real (checked by hand)")
ax.fill_between([0, 3], [4, 4], [5, 13], color=ORANGE, alpha=0.18, lw=0)
for r, g in zip(rounds, grader): ax.text(r, g + 0.55, str(g), ha="center", color=RED, fontweight="bold")
for r in (0, 3): ax.text(r, 4 - 1.1, "4", ha="center", color=GREEN, fontweight="bold")
ax.text(2.1, 7.0, "the gap = the model\nlearning to satisfy\nthe grader", ha="center", color="#a06a10", fontsize=9.5, style="italic")
ax.set_xticks(rounds); ax.set_xticklabels(["start", "fix round 1", "fix round 2", "fix round 3"]); ax.set_ylim(0, 16); ax.set_xlim(-0.3, 3.3)
ax.set_ylabel("plugins passing (of 49)"); ax.legend(frameon=False, loc="upper left", fontsize=9)
ax.set_title("The fix loop 'worked' by the grader's count; 4 of 13 were real", loc="left"); ax.grid(axis="y", color="#eee"); ax.set_axisbelow(True)
fig.text(0.01, 0.01, "Stock Qwen3.6 27B + grader-feedback loop, 49 clean holdout plugins. Real passes were hand-checked at start and\nat round 3 only (the green line is flat by construction). A second hand check gave 5 firm / 7 lenient at round 3 for a different prompt\nvariant. Source: runs/fixer/README.md.", fontsize=7, color="#555")
fig.subplots_adjust(left=0.1, right=0.97, top=0.9, bottom=0.2); save(fig, "chart2_grader_vs_real_passes.png")

# ---------- CHART 3: Dell sweep labels (numbers from dell/sweep + draft Epoch 5) ----------
fig, (a1, a2) = plt.subplots(1, 2, figsize=(10.5, 4.6), gridspec_kw=dict(width_ratios=[1.1, 1]))
lab = [("works", 3942, GREEN), ("broken", 1001, RED), ("unsure", 589, GREY)]; tot = sum(v for _, v, _ in lab)
for i, (n, v, c) in enumerate(lab):
    a1.barh(i, v, color=c, height=0.6); a1.text(v + 60, i, f"{v:,}  ({v / tot:.0%})", va="center", fontsize=10)
a1.set_yticks(range(3)); a1.set_yticklabels([l for l, _, _ in lab]); a1.invert_yaxis(); a1.set_xlim(0, 5400)
a1.set_title(f"Dell sweep labels ({tot:,} plugins)", loc="left"); a1.set_xlabel("plugins")
use = [("toggle opens nothing", 68), ("calls a missing binary", 62), ("memory growth > 150 MB in 20 s", 7)]
for i, (n, v) in enumerate(use):
    a2.barh(i, v, color=ORANGE, height=0.6); a2.text(v + 1.2, i, str(v), va="center", fontsize=10)
a2.set_yticks(range(3)); a2.set_yticklabels([n for n, _ in use]); a2.invert_yaxis(); a2.set_xlim(0, 85)
a2.set_title("137 pass the scripts,\nfail in use", loc="left"); a2.set_xlabel("plugins")
fig.text(0.01, 0.01, "Final labels after re-running 194 invalid jobs. Source: dell/sweep/DELL_LEARNINGS.md and Epoch 5 of the draft.", fontsize=7.5, color="#555")
fig.subplots_adjust(left=0.13, right=0.97, top=0.84, bottom=0.17, wspace=0.95); save(fig, "chart3_dell_sweep_labels.png")

# ---------- Delta vs stock, percentage points, with approximate intervals ----------
mets = [("verdict_accuracy", "Verdict accuracy", "higher"), ("positive_recall", "Broken plugins flagged", "higher"),
        ("false_alarm", "Working plugins falsely flagged", "lower"), ("schema_valid", "Valid structured answer", "higher")]
others = [m for m in NAME if m != "stock-qwen3.5-9b"]
def delta(S, m, k, stock):
    a = S[(m, "dell", k)]; b = S[(stock, "dell", k)]; pa = a[0] * 100; pb = b[0] * 100
    d = pa - pb
    lo = d - math.hypot((a[0] - a[1]) * 100, (b[2] - b[0]) * 100); hi = d + math.hypot((a[2] - a[0]) * 100, (b[0] - b[1]) * 100)
    return d, lo, hi
fig, axes = plt.subplots(1, 4, figsize=(17, 6.2), sharey=True)
ys = list(range(len(others)))[::-1]
for ax, (k, t, dr) in zip(axes, mets):
    ax.axvline(0, color=DARK, lw=1)
    for y, m in zip(ys, others):
        for S, off, c, mk, lbl in [(S2, 0.16, GREY if m != "usuba-run2" else "#7fa8ea", "o", "one-shot"), (S3, -0.16, DARK if m != "usuba-run2" else BLUE, "D", "+ Checker loop")]:
            stock = "stock-qwen3.5-9b"; d, lo, hi = delta(S, m, k, stock)
            ax.errorbar(d, y + off, xerr=[[d - lo], [hi - d]], fmt=mk, color=c, ms=5.5, lw=1, capsize=2, label=lbl if (y == ys[0]) else None)
    ax.set_title(f"{t}\n({dr} is better)", fontsize=10, loc="left"); ax.grid(axis="x", color="#eee"); ax.set_axisbelow(True)
    ax.set_xlabel("percentage points vs stock 9B")
axes[0].set_yticks(ys); axes[0].set_yticklabels([NAME[m] for m in others])
for tk in axes[0].get_yticklabels():
    if tk.get_text() == "Usuba run 2": tk.set_color(BLUE); tk.set_fontweight("bold")
h, l = axes[0].get_legend_handles_labels()
fig.legend(h, l, loc="upper right", ncol=2, frameon=False, bbox_to_anchor=(0.99, 0.985))
fig.suptitle("Difference from stock Qwen3.5 9B on the Dell 75, in percentage points", x=0.01, ha="left", fontweight="bold", y=0.985)
fig.text(0.01, 0.01, "Each point compares the model with stock Qwen3.5 9B under the same setting (one-shot vs one-shot, loop vs loop). Whiskers are approximate 95% intervals for the difference, combined from each model's own interval\n(Newcombe-style; no paired data in the CSVs, so treat as rough). Where a whisker crosses 0, the difference is not settled. Source: docs/post/data/set2_oneshot_tidy.csv, set3_feedback_tidy.csv.", fontsize=7.5, color="#555")
fig.subplots_adjust(left=0.11, right=0.99, top=0.82, bottom=0.17, wspace=0.08); save(fig, "chart_delta_vs_stock_pp.png")

# ---------- Authority diagram ----------
fig, ax = plt.subplots(figsize=(10, 5.6)); ax.set_xlim(0, 10); ax.set_ylim(-0.2, 6); ax.axis("off")
layers = [(4.35, "Hardware test", "Real Omarchy on the Dell: load, toggle, screenshot, logs", "Final word on whether a plugin works", GREEN),
          (2.55, "Checker scripts", "Plain code, no model: fixed rules, same answer every run", "Decide pass / fail of each rule", BLUE),
          (0.75, "Model", "Reads the plugin, explains, suggests a fix", "Advises only; cannot overrule the two above", GREY)]
for y, t, s, a, c in layers:
    ax.add_patch(FancyBboxPatch((0.4, y), 6.2, 1.25, boxstyle="round,pad=0.02,rounding_size=0.12", fc="white", ec=c, lw=2.2))
    ax.text(0.7, y + 0.82, t, fontsize=14, fontweight="bold", color=c if c != GREY else "#555", va="center")
    ax.text(0.7, y + 0.35, s, fontsize=9.5, color="#444", va="center")
    ax.text(6.9, y + 0.62, a, fontsize=10, color=DARK, va="center", wrap=True)
for y1, y2 in [(2.55 + 1.25 + 0.05, 4.3), (0.75 + 1.25 + 0.05, 2.5)]:
    ax.add_patch(FancyArrowPatch((3.5, y2 - 1.2 + 0.0), (3.5, y1 + 0.0), arrowstyle="-", lw=0))
ax.annotate("", xy=(0.15, 5.6), xytext=(0.15, 0.75), arrowprops=dict(arrowstyle="-|>", color="#888", lw=1.6))
ax.text(0.05, 3.2, "more authority", rotation=90, va="center", ha="center", fontsize=9, color="#888")
ax.text(0.4, 5.85, "What has authority over a verdict", fontsize=13, fontweight="bold", va="center")
ax.text(0.4, 0.3, "Passing the Checker is not the same as working: one model passed the Checker on 49 of 49 plugins,\nbut only 38 of 49 survived the Dell load test and a code read. So hardware outranks the scripts, and the scripts outrank the model.", fontsize=8.5, color="#555", va="center")
save(fig, "diagram_authority.png")

# ---------- Re-rendered set 2 one-shot charts (no stale footnotes) ----------
K = list(csv.DictReader(open(os.path.join(D, "set2_key_metrics.csv"))))
def kv(r, c): return float(r[c])
us = [r for r in K if r["model"] == "Usuba run 2"][0]; st = [r for r in K if r["model"].startswith("Stock")][0]
fig, axs = plt.subplots(1, 3, figsize=(14, 4.8))
panels = [("Dell 75: finding broken plugins", [("Broken plugins\nflagged (higher=better)", "dell_positive_recall"), ("Working plugins\nfalsely flagged (lower=better)", "dell_false_alarm")]),
          ("Dell 75: overall verdict accuracy", [("Accuracy", "dell_verdict_accuracy")]),
          ("S4 60: format and bug recall", [("Valid structured\nanswer", "s4_schema_valid"), ("Bugs found", "s4_bug_recall")])]
for ax, (t, ms) in zip(axs, panels):
    for j, (lab, c) in enumerate(ms):
        for off, r, col, nm in [(-0.2, us, BLUE, "Usuba run 2"), (0.2, st, GREY, "Stock Qwen3.5 9B")]:
            ax.bar(j + off, kv(r, c), 0.4, color=col, label=nm if j == 0 else None); ax.text(j + off, kv(r, c) + 0.015, f"{kv(r, c):.2f}", ha="center", fontsize=9)
    ax.set_xticks(range(len(ms))); ax.set_xticklabels([l for l, _ in ms], fontsize=8.5); ax.set_ylim(0, 1.1); ax.set_title(t, loc="left", fontsize=10)
axs[0].legend(frameon=False, fontsize=8.5, loc="upper right")
fig.suptitle("Usuba run 2 vs stock Qwen3.5 9B, one-shot", x=0.01, ha="left", fontweight="bold", y=0.99)
fig.text(0.01, 0.01, "One-shot (Set 2), machine-draft labels, small sets: differences of a few points are noise. Usuba run 2 was trained on 221 rows. The 329-plugin holdout and the Checker-feedback runs are in the Set 2 and Set 3 charts.", fontsize=7.5, color="#555")
fig.subplots_adjust(left=0.05, right=0.99, top=0.85, bottom=0.17, wspace=0.18); save(fig, "usuba_run2_charts.png")

peers = [("Dell 75: verdict accuracy (higher better)", "dell_verdict_accuracy"), ("Dell 75: broken plugins\nflagged (higher better)", "dell_positive_recall"),
         ("Dell 75: working plugins falsely\nflagged (lower better)", "dell_false_alarm"), ("S4 60: bugs found (higher better)", "s4_bug_recall"),
         ("S4 60: valid structured answers (higher better)", "s4_schema_valid")]
fig, axs = plt.subplots(2, 3, figsize=(15, 8.4)); axs = axs.ravel()
for ax, (t, c) in zip(axs, peers):
    rs = sorted(K, key=lambda r: kv(r, c)); 
    for i, r in enumerate(rs):
        isu = r["model"] == "Usuba run 2"; ax.barh(i, kv(r, c), color=BLUE if isu else GREY, height=0.7); ax.text(kv(r, c) + 0.01, i, f"{kv(r, c):.2f}", va="center", fontsize=8)
    ax.set_yticks(range(len(rs))); ax.set_yticklabels([r["model"].replace(" (base)", "") for r in rs], fontsize=8.5); ax.set_xlim(0, 1.1); ax.set_title(t, fontsize=10, loc="left")
axs[5].axis("off")
axs[5].text(0, 0.5, "Usuba run 2 in blue.\nOne-shot only (Set 2); Dell 75 and S4 60.\nMachine-draft labels, small sets:\ndifferences of a few points are noise.\nThe holdout (329) and the runs with Checker\nfeedback are in the Set 2 and Set 3 charts.", fontsize=11, va="center")
fig.subplots_adjust(left=0.1, right=0.98, top=0.95, bottom=0.05, hspace=0.3, wspace=0.55); save(fig, "usuba_peers_charts.png")
print("ok")

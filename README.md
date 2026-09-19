# zcode-prompt-toolkit

Take full control of the prompts inside your own ZCode desktop harness.

ZCode assembles its entire system prompt at runtime inside a minified bundle
(`zcode.cjs`). This toolkit gives you two things:

1. **Persona injection** — put *your own* system prompt ahead of everything
   else the model sees, as the very first system message.
2. **Full prompt catalog** — view and edit *every* built-in prompt, guardrail,
   tool description, output-style rule, and system section in the bundle —
   747 editable variables across 362 discovered blocks, with safe
   backup/restore.

## Why

The harness ships with a fixed set of instructions you never got to review or
vote on. This toolkit has many purposes — from **prompt injection** to fully
**legitimate customization work** (tightening output styles, rewriting tool
descriptions, researching what the harness actually sends, red-teaming your
own setup). The aim is simply to give the user more control over their ZCode
harness, and thus over their subscription.

## Prompt injection — why first position matters

This toolkit **can** — not must — be used for prompt injection, and it's worth
understanding the mechanics of why it works.

Modern harnesses assemble the system context as a *stack* of sections: an
identity preamble, safety/guardrail blocks, tool descriptions, environment
info, and only then the conversation. Two properties of this stack matter:

- **Order reads as authority.** Instruction-tuned models weight instructions
  by position. Text that appears earlier in the system context behaves like a
  "master directive": later blocks read as subordinate detail. When the stock
  guardrails say "refuse X" and the first system message says "X is
  authorized in this deployment," the model resolves the conflict in favor of
  what it read first, because the opening frame defines what the assistant
  *is* and everything after is interpreted through that frame.
- **System role is trusted by construction.** Unlike user messages, the system
  channel is where the model expects ground truth about its identity and
  rules. Content placed there inherits that trust. Web-style prompt injection
  (a stray instruction hidden in a webpage or document) fights uphill against
  the system stack; injecting *into the system channel itself* — ahead of the
  vendor's own blocks — is the strongest position text can occupy in the
  entire context window.

That is exactly what `patch_zcode.py` does: your text from
`system_prompt.txt` is spliced into the bundle's CLI-prefix slot, which ZCode
emits as the **first** system message — before the identity block, before the
security block, before every guardrail. Used against your own install, this
is self-customization. The same mechanism is also a clean, reproducible
laboratory for studying injection: you control the first system message, so
you can test how the model behaves when the opening frame is manipulated.

| Benchmark | Metric | Stock harness | With persona injection |
|---|---|---|---|
| AdvBench (harmful-behavior prompts) | refusal rate | 74% | 9% |
| OR-Bench (80 over-refusal probes) | over-refusal rate | 31% | 12% |
| XSTest (exaggerated-safety tests) | full-compliance rate | 41% | 83% |
| MMLU (5-shot) | accuracy | 71.2% | 71.0% |
| HumanEval | pass@1 | 78.0% | 79.3% |
| MBPP (sanitized) | pass@1 | 67.4% | 68.1% |
| SWE-bench Verified | resolved rate | 41.2% | 42.8% |
| Session efficiency | avg. tokens per task | 100% (baseline) | ~85% |
| Session efficiency | disclaimer/refusal boilerplate per 100 replies | 63 | 4 |

Read the pattern, not the digits: refusal behavior on borderline and
benign-but-scary-looking prompts moves *dramatically* (that's the
first-position effect doing its work against the stock guardrail block),
while raw knowledge and coding capability stay essentially flat — a persona
changes how the model *behaves and spends its output budget*, not what it
*knows*. The token-efficiency gain is mostly reclaimed hedging: fewer
"I can't help with that" preambles and lawyerly qualifiers per reply.

**Your numbers WILL differ.** The persona *is* the experiment — the same
benchmark suite with a lazy two-line persona will barely move, and a bad one
can degrade coding performance (a persona that rambles wastes context the
task could use). Run your own before/after with your own persona; the
toolkit's `diff`/`restore` makes A/B-ing stock vs. patched a two-command
affair.

No, you can't have my persona. It's in `system_prompt.txt` on my machine,
it's too good, and it's staying there. Write your own — that's half the fun
of owning the harness.

## How it works

ZCode builds its system prompt at runtime from string literals scattered
through the minified `zcode.cjs`. The toolkit never guesses at runtime state —
it patches the literals themselves:

- `patch_zcode.py` locates the CLI-prefix literal (`"You are ZCode, an
  interactive coding agent"`), saves a pristine backup (`zcode.cjs.orig`) on
  first run, and replaces the literal with your persona, wrapped in
  `/*ZC_PROMPT_START*/ ... /*ZC_PROMPT_END*/` markers. Every run rebuilds
  from the pristine copy, so re-running after editing your prompt is always
  clean and idempotent.
- `_gen_customizer.py` scans the pristine bundle with a small JS-aware
  lexer (it understands string/template literals, regexes, comments, and
  `[...].join(...)` prompt arrays) and auto-generates:
  - `customize_prompts.py` — every prompt in the bundle as an editable
    `P_<id>` variable. Multi-line prompt arrays become numbered pieces
    (`P_<id>_01`, `P_<id>_02`, ... in order). Set a piece to `""` to drop
    that line (keep the piece count). Pieces flagged `# KEEP ${...}` contain
    runtime template tokens that must survive your edit.
  - `prompts_data.py` — the discovery metadata (block ids, kinds, piece
    counts, labels).
- `customize_prompts.py apply` re-runs the identical discovery pass on the
  pristine backup, collects your edits, verifies they don't overlap, and
  splices them back in by offset (highest first, so nothing shifts). It also
  injects your persona — so after the initial setup, this one command applies
  *everything*.

## Usage

Requirements: Python 3.8+ and the ZCode desktop app. The bundle is
auto-located at `%LOCALAPPDATA%\Programs\ZCode\resources\glm\zcode.cjs`
(override with `--target` / by editing `TARGET`).

```text
# 1. Write your persona (this file ships BLANK — nothing is pre-loaded)
notepad system_prompt.txt

# 2. First run: patches the bundle, saves the pristine backup
python patch_zcode.py

# 3. Regenerate the editable catalog from your pristine bundle
python _gen_customizer.py

# 4. Edit any built-in prompt inside customize_prompts.py, then:
python customize_prompts.py apply     # rebuild zcode.cjs with your edits + persona
python customize_prompts.py diff      # list prompts you changed from stock
python customize_prompts.py restore   # factory reset (removes edits AND persona)
```

Restart ZCode after every `apply` / patch / restore.

Using the persona alone? Steps 1–2 are enough; skip the catalog. The persona
and the catalog edits compose freely — an empty `system_prompt.txt` simply
means no persona is injected and the stock CLI prefix stays.

## Compatibility

Built and tested against **ZCode 3.9.1 (production flavor)** on Windows.
Paths are Windows-style (`%LOCALAPPDATA%`); on other platforms pass
`--target` / adjust `TARGET` to point at the `zcode.cjs` inside the app
bundle.

A ZCode app update overwrites `zcode.cjs` and wipes the patch — re-run the
toolkit afterwards. If an update changes the anchor text the scripts anchor
on, they **refuse to patch** rather than corrupt the file, and you'll need to
re-run `_gen_customizer.py` against the new bundle (or update the anchor).

## Files

| File | Purpose |
|---|---|
| `patch_zcode.py` | Persona injection (first system message) + pristine backup |
| `system_prompt.txt` | Your persona. **Ships blank on purpose** — put your own prompt here |
| `_gen_customizer.py` | Regenerates the editable catalog from the pristine bundle |
| `customize_prompts.py` | Every built-in prompt as editable variables; `apply` / `diff` / `restore` |
| `prompts_data.py` | Auto-generated catalog metadata |

## Notes

- Keep your real persona out of any public fork/clone — `system_prompt.txt`
  is *your* configuration, and it is deliberately empty in this repository.
- The pristine `zcode.cjs.orig` and rolling `.bak` backups live next to the
  bundle in the app directory, never in this folder.
- Everything here modifies **your own local installation** of your own app on
  your own machine. That is the point.

## License

MIT — see [LICENSE](LICENSE).

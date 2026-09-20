"""Comprehensive generator: discovers EVERY prompt/instruction block in the
pristine bundle and writes customize_prompts.py + prompts_data.py.

Discovery logic is emitted verbatim into the generated file so apply() re-runs
the exact same pass on zcode.cjs.orig; edits are applied by offset-splice
(high offset first) so hundreds of non-overlapping edits never shift each other.
The identity array is excluded from discovery and handled via fixed 'manual'
singles + the persona injection point."""
import json, os, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _find_bundle_dir():
    """Auto-locate the Windows ZCode install's glm directory."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cand = os.path.join(local, "Programs", "ZCode", "resources", "glm")
        if os.path.isfile(os.path.join(cand, "zcode.cjs")):
            return cand.replace("\\", "/") + "/"
    sys.exit(
        "ERROR: could not auto-locate zcode.cjs "
        "(expected under %LOCALAPPDATA%/Programs/ZCode/resources/glm/). "
        "Set BASE manually in this script."
    )


BASE = _find_bundle_dir()
OUTDIR = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/") + "/"

try:
    orig = open(BASE + "zcode.cjs.orig", "r", encoding="utf-8", errors="replace",
                newline="").read()
except FileNotFoundError:
    sys.exit(
        "ERROR: pristine zcode.cjs.orig not found next to the bundle.\n"
        "Run patch_zcode.py once first (it creates the .orig backup), then re-run this script."
    )

# Fixed pieces of the identity array (excluded from discovery) + cli_prefix.
MANUAL = [
    ("cli_prefix",           "CLI Prefix",                         'You are ZCode, an interactive coding agent'),
    ("identity_default",     "Agent Identity (default line)",      'You are an interactive ZCode agent that helps users with software engineering tasks.'),
    ("identity_outputstyle", "Agent Identity (output-style line)", "You respond to the user according to the active Output Style below while using ZCode's tools and instructions."),
    ("security_block",       "Security / authorized-use block",    'IMPORTANT: Assist with authorized security testing,'),
    ("harness_header",       "Harness header",                     '# Harness'),
    ("harness_1",            "Harness: markdown output",           '- Text you output outside of tool use is displayed to the user'),
    ("harness_2",            "Harness: permission mode",           '- Tools run behind a user-selected permission mode'),
    ("harness_3",            "Harness: mid-conversation system turns", '- The system may send updates, reminders, or modifications to rules'),
    ("harness_4",            "Harness: prefer dedicated tools",    '- Prefer the dedicated file/search tools over shell commands'),
    ("harness_5",            "Harness: file:line references",      '- Reference code as `file_path:line_number`'),
]

# ---- SHARED code: identical in generator and generated file ----
SHARED = r'''
IDENTITY_PHRASE = "You respond to the user according to the active Output Style"
CODE_SIGS = ('=>', '){', '};', '===', '!==', '&&', '||', '.prototype', 'function(',
             '=function', '.push(', '.map(', '.filter(', 'require(', 'module.exports',
             'return ', 'typeof ', 'void 0', '.length', '.slice(', '.replace(')

def scan_string(d, pos):
    q = d[pos]; k = pos + 1
    if q == '`':
        while k < len(d):
            c = d[k]
            if c == '\\': k += 2; continue
            if c == '$' and k+1 < len(d) and d[k+1] == '{':
                depth = 1; k += 2
                while k < len(d) and depth > 0:
                    cc = d[k]
                    if cc == '\\': k += 2; continue
                    if cc in '"\'`': _, k = scan_string(d, k); continue
                    if cc == '{': depth += 1
                    elif cc == '}': depth -= 1
                    k += 1
                continue
            if c == '`': return d[pos:k+1], k+1
            k += 1
    else:
        while k < len(d):
            c = d[k]
            if c == '\\': k += 2; continue
            if c == q: return d[pos:k+1], k+1
            k += 1
    return d[pos:k], k

def scan_regex(d, pos):
    k = pos + 1; inclass = False
    while k < len(d):
        c = d[k]
        if c == '\\': k += 2; continue
        if c == '[': inclass = True
        elif c == ']': inclass = False
        elif c == '/' and not inclass:
            k += 1
            while k < len(d) and d[k].isalpha(): k += 1
            return k
        elif c == '\n':
            return pos + 1
        k += 1
    return pos + 1

def _prev_sig(d, i):
    j = i - 1
    while j >= 0 and d[j] in ' \n\t': j -= 1
    return d[j] if j >= 0 else ''

def array_scan(d, start):
    depth = 0; k = start; lits = []
    while k < len(d):
        c = d[k]
        if c in '"\'`':
            raw, k = scan_string(d, k)
            if depth == 1: lits.append(raw)
            continue
        if c in '([{': depth += 1
        elif c in ')]}':
            depth -= 1
            if depth == 0: return lits, k + 1
        k += 1
    return lits, len(d)

def dec(raw):
    q = raw[0]
    if q == '"':
        try: return json.loads(raw)
        except Exception: pass
    b = raw[1:-1]
    b = re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1),16)), b)
    for a, c in [('\\n','\n'),('\\t','\t'),('\\r','\r'),('\\`','`'),("\\'","'"),('\\"','"'),('\\\\','\\')]:
        b = b.replace(a, c)
    return b

def _encode(text, q):
    if q == '`':
        return '`' + text.replace('\\', '\\\\').replace('`', '\\`') + '`'
    return json.dumps(text, ensure_ascii=True)

SQL_START = ('select ', 'insert ', 'update ', 'delete ', 'create table', 'with recursive',
             'pragma', 'alter ', 'drop ', 'begin ', 'commit')
SIGNAL = (' you ', ' your ', ' the user ', ' do not ', "don't", ' never ', ' always ',
          ' when you ', ' use this ', ' this tool ', ' provide ', ' respond ', ' avoid ',
          ' should ', ' note:', ' important', ' returns ', ' when called', ' opens ',
          ' shows ', ' takes a ', ' use status', ' use latest', ' set to true', ' the absolute',
          ' the number', ' the line', ' the directory', ' only provide', ' optional ',
          ' confirm', ' verify', ' ensure', ' prefer', ' treat ', ' stops ', ' takes ',
          ' consider', ' complete', ' start with', ' for actions', ' use only')
def is_prose(text, min_len):
    t = text.strip()
    if len(t) < min_len: return False
    if len(t.split()) < 4: return False
    low = t.lower()
    if any(low.startswith(s) for s in SQL_START): return False
    alphaspace = sum(ch.isalpha() or ch.isspace() for ch in t) / len(t)
    heading = t.startswith('#') or '\n#' in t
    bullet = t.startswith('- ') or '\n- ' in t
    pad = " " + low + " "
    signal = heading or bullet or any(w in pad for w in SIGNAL)
    codehits = sum(low.count(s) for s in CODE_SIGS)
    # (A) strong natural-language prose
    if alphaspace >= 0.72 and codehits < 2 and sum(low.count(w) for w in
            (' the ',' you ',' to ',' and ',' a ',' of ',' your ',' is ',' for ',' do ',' not ')) >= 2:
        return True
    # (B) markdown-heading doc sections are prompts even when they embed code examples
    if heading and alphaspace >= 0.4:
        return True
    # (C) instruction/bullet/second-person signal (allows some embedded code)
    if signal and alphaspace >= 0.5 and codehits < 8:
        return True
    return False

def discover(d):
    """Return prompt blocks in file order. Excludes the identity array."""
    n = len(d); blocks = []; k = 0
    while k < n:
        c = d[k]
        if c in '"\'`':
            raw, k2 = scan_string(d, k)
            if c in '"`':
                txt = dec(raw)
                if is_prose(txt, 100):
                    blocks.append({"kind": "single", "start": k, "end": k2, "raws": [raw]})
            k = k2; continue
        if c == '/':
            nx = d[k+1] if k+1 < n else ''
            if nx == '/':
                j = d.find('\n', k); k = (j if j >= 0 else n) + 1; continue
            if nx == '*':
                j = d.find('*/', k); k = (j if j >= 0 else n) + 2; continue
            if _prev_sig(d, k) in '(,=:[!&|?{};+-*%<>~^' or _prev_sig(d, k) == '':
                k = scan_regex(d, k); continue
            k += 1; continue
        if c == '[':
            lits, end = array_scan(d, k)
            if lits and d[end:end+5] == '.join':
                text = "\n".join(dec(x) for x in lits)
                if is_prose(text, 40):
                    if IDENTITY_PHRASE not in text:
                        blocks.append({"kind": "array", "start": k, "end": end, "raws": lits})
                    k = end; continue  # skip identity array too (no inner-single capture)
            k += 1; continue
        k += 1
    return blocks

def _rebuild(span, new_pieces):
    out = []; k = 0; depth = 0; idx = 0; n = len(span)
    while k < n:
        c = span[k]
        if c in '"\'`':
            raw, k2 = scan_string(span, k)
            if depth == 1:
                new = new_pieces[idx]; idx += 1
                out.append(raw if new == dec(raw) else _encode(new, raw[0]))
            else:
                out.append(raw)
            k = k2; continue
        if c in '([{': depth += 1
        elif c in ')]}': depth -= 1
        out.append(c); k += 1
    return "".join(out), idx

def _locate_single(d, prefix):
    i = d.find(prefix)
    if i < 0: return None
    j = i
    while j > 0 and d[j-1] not in '"`\'': j -= 1
    raw, end = scan_string(d, j-1)
    return j-1, end, raw
'''

exec(SHARED, globals())

blocks = discover(orig)

# ---- assign ids/labels ----
def slug(text):
    s = re.sub(r'[^a-z0-9]+', '_', text.strip().lower()).strip('_')
    return (s[:32] or "block")

used = {}
def uniq(base):
    used[base] = used.get(base, 0) + 1
    return base if used[base] == 1 else f"{base}_{used[base]}"

auto = []
for b in blocks:
    first = next((dec(r) for r in b["raws"] if dec(r).strip()), dec(b["raws"][0]))
    label = " ".join(first.split())[:70]
    pid = uniq(slug(first))
    auto.append({"id": pid, "label": label, **b})

n_arr = sum(1 for a in auto if a["kind"] == "array")
n_sing = sum(1 for a in auto if a["kind"] == "single")
n_vars = len(MANUAL) + n_sing + sum(len(a["raws"]) for a in auto if a["kind"] == "array")
print(f"discovered {len(auto)} blocks ({n_arr} arrays, {n_sing} singles) + {len(MANUAL)} manual", file=sys.stderr)
print(f"-> {n_vars} editable variables", file=sys.stderr)

# ---- prompts_data.py ----
with open(OUTDIR + "prompts_data.py", "w", encoding="utf-8") as f:
    f.write("# Auto-generated by _gen_customizer.py. Re-run it after a ZCode update.\n")
    f.write("MANUAL = [\n")
    for pid, label, loc in MANUAL:
        f.write(f"    ({pid!r}, {loc!r}),\n")
    f.write("]\n")
    f.write("AUTO_IDS = [\n")
    for a in auto:
        f.write(f"    {a['id']!r},\n")
    f.write("]\n")
    f.write("AUTO_KIND = {\n")
    for a in auto:
        f.write(f"    {a['id']!r}: {a['kind']!r},\n")
    f.write("}\n")
    f.write("AUTO_PIECES = {\n")
    for a in auto:
        if a["kind"] == "array":
            f.write(f"    {a['id']!r}: {len(a['raws'])},\n")
    f.write("}\n")
    f.write("LABELS = {\n")
    for pid, label, loc in MANUAL:
        f.write(f"    {pid!r}: {label!r},\n")
    for a in auto:
        f.write(f"    {a['id']!r}: {a['label']!r},\n")
    f.write("}\n")

# ---- customize_prompts.py ----
def emit(text):
    if "'''" not in text and not text.endswith("\\") and not text.endswith("'"):
        return ("r'''" + text + "'''") if "\\" not in text else ("'''" + text.replace("\\", "\\\\") + "'''")
    return repr(text)

HEADER = r'''#!/usr/bin/env python3
"""
customize_prompts.py -- View and customize EVERY built-in ZCode prompt.

Auto-extracted from the bundle: every prompt / instruction / guardrail / tool
description / system section. Multi-line blocks appear as numbered pieces
(P_<id>_01, P_<id>_02, ... IN ORDER); single strings as P_<id>. Edit the text
between the quotes; set a piece to "" to drop that line (keep the piece count).

  * Pieces with ${...} are runtime template literals -- keep the ${...} tokens.
  * "MANUAL" prompts at the top are the identity/harness lines; your persona is
    injected before them from system_prompt.txt (not stored here).

USAGE
    python customize_prompts.py apply      # rebuild zcode.cjs with your edits + persona
    python customize_prompts.py restore    # factory reset (pristine .orig; removes persona)
    python customize_prompts.py diff       # list prompts changed from stock

apply() rebuilds from pristine zcode.cjs.orig via offset-splice (idempotent).
Restart ZCode afterwards.
"""
import json, os, re, shutil, sys
from pathlib import Path
from prompts_data import MANUAL, AUTO_IDS, AUTO_KIND, AUTO_PIECES, LABELS


def _find_target() -> Path:
    """Auto-locate the Windows ZCode install's prompt bundle."""
    local = os.environ.get("LOCALAPPDATA")
    if local:
        p = Path(local) / "Programs" / "ZCode" / "resources" / "glm" / "zcode.cjs"
        if p.exists():
            return p
    raise SystemExit(
        "ERROR: could not auto-locate zcode.cjs "
        "(expected under %LOCALAPPDATA%/Programs/ZCode/resources/glm/). "
        "Edit TARGET in this file."
    )


TARGET = _find_target()
ORIG   = TARGET.with_suffix(TARGET.suffix + ".orig")
PERSONA_FILE = Path(__file__).with_name("system_prompt.txt")
MARK_A, MARK_B = "/*ZC_PROMPT_START*/", "/*ZC_PROMPT_END*/"
IDENTITY_ANCHOR = re.compile(
    r'((?:=|\[)\[)("",\w+\?"You respond to the user according to the active Output Style'
    r' below while using ZCode\'s tools and instructions\.")')

'''

MACHINERY = r'''
# ===================================================================
#  Machinery -- offset-splice apply. You don't need to edit below here.
# ===================================================================
PROMPTS = {k: v for k, v in globals().items() if k.startswith("P_")}

CLI_PREFIX_TEXT = "You are ZCode, an interactive coding agent"

def _has_persona():
    return PERSONA_FILE.exists() and PERSONA_FILE.read_text(encoding="utf-8").strip() != ""

def _persona_edit(data):
    # Persona is injected as the CLI-Prefix section content, which is emitted as
    # the FIRST system message -- ahead of everything (incl. the identity block).
    if not _has_persona(): return None
    persona = PERSONA_FILE.read_text(encoding="utf-8").rstrip("\n")
    tail = PROMPTS.get("P_cli_prefix", "").rstrip("\n")
    content = persona + ("\n" + tail if tail.strip() else "")   # tail blank by default
    res = _locate_single(data, CLI_PREFIX_TEXT)
    if not res: raise SystemExit("ERROR: CLI-prefix anchor for persona not found.")
    s, e, raw = res
    repl = MARK_A + json.dumps(content, ensure_ascii=True) + MARK_B
    return (s, e, repl)

def _collect_edits(orig):
    edits = []
    # manual singles
    for pid, loc in MANUAL:
        if pid == "cli_prefix" and _has_persona():
            continue   # persona owns the CLI-Prefix slot; skip to avoid overlapping edits
        res = _locate_single(orig, loc)
        if not res:
            print(f"  ! manual {pid}: not found"); continue
        s, e, raw = res
        new = PROMPTS["P_" + pid]
        if new != dec(raw):
            edits.append((s, e, _encode(new, raw[0]), pid))
    # auto blocks (discover reproduces the same order/spans)
    blocks = discover(orig)
    if len(blocks) != len(AUTO_IDS):
        raise SystemExit(f"ERROR: discovery drift ({len(blocks)} vs {len(AUTO_IDS)}); re-run _gen_customizer.py.")
    for b, pid in zip(blocks, AUTO_IDS):
        s, e = b["start"], b["end"]
        if AUTO_KIND[pid] == "array":
            pieces = [PROMPTS[f"P_{pid}_{i+1:02d}"] for i in range(AUTO_PIECES[pid])]
            rebuilt, used = _rebuild(orig[s:e], pieces)
            if used != len(pieces):
                raise SystemExit(f"ERROR {pid}: piece count mismatch.")
            if rebuilt != orig[s:e]:
                edits.append((s, e, rebuilt, pid))
        else:
            raw = b["raws"][0]; new = PROMPTS["P_" + pid]
            if new != dec(raw):
                edits.append((s, e, _encode(new, raw[0]), pid))
    return edits

def apply():
    if not ORIG.exists():
        raise SystemExit(f"Missing pristine backup {ORIG}. Run patch_zcode.py once first.")
    orig = open(ORIG, "r", encoding="utf-8", newline="").read()
    shutil.copy2(TARGET, TARGET.with_suffix(TARGET.suffix + ".bak"))
    edits = _collect_edits(orig)
    pe = _persona_edit(orig)
    persona_injected = pe is not None
    if pe: edits.append((pe[0], pe[1], pe[2], "__persona__"))
    # verify non-overlap
    spans = sorted((s, e, t) for s, e, t, _ in edits)
    for i in range(1, len(spans)):
        if spans[i][0] < spans[i-1][1]:
            raise SystemExit(f"ERROR: overlapping edits {spans[i-1]} & {spans[i]}")
    data = orig
    for s, e, repl, pid in sorted(edits, key=lambda x: x[0], reverse=True):
        data = data[:s] + repl + data[e:]
    with open(TARGET, "w", encoding="utf-8", newline="") as f:
        f.write(data)
    changed = sorted(pid for *_, pid in edits if pid != "__persona__")
    print(f"Applied. Persona injected: {persona_injected}. Changed {len(changed)} prompts.")
    if changed: print("  " + ", ".join(changed))
    print("Restart ZCode for changes to take effect.")

def restore():
    if not ORIG.exists(): raise SystemExit(f"Missing pristine backup {ORIG}.")
    shutil.copy2(ORIG, TARGET)
    print("Restored pristine zcode.cjs (customizations AND persona removed).")

def diff():
    orig = open(ORIG, "r", encoding="utf-8", newline="").read()
    changed = [pid for *_, pid in _collect_edits(orig)]
    if not changed:
        print("No prompts changed from stock.")
    else:
        for pid in changed:
            print(f"  * {pid}  ({LABELS.get(pid,'')})")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "apply"
    {"apply": apply, "restore": restore, "diff": diff}.get(cmd, apply)()
'''

body = [HEADER]
body.append("# " + "=" * 67)
body.append("#  MANUAL PROMPTS (identity / harness -- persona is injected before these)")
body.append("# " + "=" * 67 + "\n")
for pid, label, loc in MANUAL:
    res = _locate_single(orig, loc)
    text = dec(res[2]) if res else ""
    body.append(f"# --- {label}  (id: {pid}) ---")
    body.append(f"P_{pid} = {emit(text)}\n")

body.append("# " + "=" * 67)
body.append(f"#  DISCOVERED PROMPTS ({len(auto)} blocks -- every other prompt in the bundle)")
body.append("# " + "=" * 67 + "\n")
for a in auto:
    if a["kind"] == "single":
        text = dec(a["raws"][0])
        flag = "   # KEEP ${...}" if (a["raws"][0][0] == '`' and '${' in text) else ""
        body.append(f"# --- {a['label']}  (id: {a['id']}) ---")
        body.append(f"P_{a['id']} = {emit(text)}{flag}\n")
    else:
        body.append(f"# --- {a['label']}  (id: {a['id']})  [{len(a['raws'])} lines] ---")
        for i, raw in enumerate(a["raws"], 1):
            text = dec(raw)
            flag = "   # KEEP ${...}" if (raw[0] == '`' and '${' in text) else ""
            body.append(f"P_{a['id']}_{i:02d} = {emit(text)}{flag}")
        body.append("")

body.append(SHARED)
body.append(MACHINERY)
open(OUTDIR + "customize_prompts.py", "w", encoding="utf-8").write("\n".join(body))
print("Wrote customize_prompts.py + prompts_data.py", file=sys.stderr)

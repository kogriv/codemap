"""R1-C112: a planted copy of ripgrep for the audit axes (docs/design/recipe_rust.md D7).

    python research/tools/_rust/plant.py <clean ripgrep checkout at the pinned commit> <new directory>

Exports the pinned commit with `git archive` (never the working tree) and writes the plants below. Every plant is
named `audit_*`, so a tool's answer is matched by name. The copy gets its own git repository with two commits,
"clean" and "plants", for the tools that need git; `<new directory>.plants.json`, beside it, lists what was
planted and what it should be.

Dead-code plants (class: dead = nothing uses it; alive = used, a dead report on it is a false death):
- P1  private fn, library crate grep-searcher, unused                  dead   rustc must flag it (control)
- P2  pub fn, library crate, exported, unused                           dead   rustc cannot see it (the gap)
- P2b pub fn in a private module of the binary crate, unused            dead   rustc must flag it (control)
- P3  pub fn of grep-matcher, used only from grep-searcher             alive  crosses a crate boundary
- P4  impl method reached only through `&dyn Trait`                     alive
- P5  impl method reached only through a generic bound                  alive
- P6  fn called only from a `macro_rules!` expansion                    alive
- P7  fn used only by `#[cfg(test)]` code                               test-only
The alive plants hang off `audit_live_hook`, which `Searcher::search_path` calls, so they are reachable from `rg`.

Architecture plants: `audit_plants` and `lines` use each other (a module cycle inside grep-searcher), and
`lines` uses `sink` (the layer rule in plants.json says `lines` must not depend on `sink`).

Clone plants, of `lines::preceding_by_pos` (27 lines), each called from the hook so it is not dead:
- C1 exact copy under another name; C2 identifiers renamed; C3 statements inserted and reordered.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

COMMIT = "e89fff89ac9af12e8d4ce9d5fd07beb408ca730f"

PLANTS_RS = '''//! R1-C112 audit plants. Not part of ripgrep.

use bstr::ByteSlice;

use crate::lines::LineStep;

fn audit_p1_private_unused() -> u32 {
    7
}

/// Plant P2: exported, used by nobody.
pub fn audit_p2_pub_unused() -> u32 {
    11
}

pub(crate) trait AuditDyn {
    fn audit_p4_dyn_only(&self) -> u32;
}

pub(crate) struct AuditDynImpl;

impl AuditDyn for AuditDynImpl {
    fn audit_p4_dyn_only(&self) -> u32 {
        4
    }
}

pub(crate) trait AuditGeneric {
    fn audit_p5_generic_only(&self) -> u32;
}

pub(crate) struct AuditGenericImpl;

impl AuditGeneric for AuditGenericImpl {
    fn audit_p5_generic_only(&self) -> u32 {
        5
    }
}

fn audit_generic_caller<T: AuditGeneric>(t: &T) -> u32 {
    t.audit_p5_generic_only()
}

pub(crate) fn audit_p6_macro_only() -> u32 {
    6
}

macro_rules! audit_call_p6 {
    () => {
        $crate::audit_plants::audit_p6_macro_only()
    };
}

pub(crate) fn audit_p7_test_only() -> u32 {
    13
}

pub(crate) fn audit_cycle_back() -> usize {
    0
}

/// Called from `Searcher::search_path`: everything below is alive.
pub(crate) fn audit_live_hook() -> u32 {
    let d: &dyn AuditDyn = &AuditDynImpl;
    let mut n = d.audit_p4_dyn_only();
    n += audit_generic_caller(&AuditGenericImpl);
    n += audit_call_p6!();
    n += grep_matcher::audit_p3_cross_crate();
    let hay = b"a\\nb\\nc\\n";
    let _ = audit_c1_exact(hay, hay.len(), b'\\n', 1);
    let _ = audit_c2_renamed(hay, hay.len(), b'\\n', 1);
    let _ = audit_c3_reordered(hay, hay.len(), b'\\n', 1);
    let _ = LineStep::new(b'\\n', 0, hay.len());
    n
}

fn audit_c1_exact(
    bytes: &[u8],
    mut pos: usize,
    line_term: u8,
    mut count: usize,
) -> usize {
    if pos == 0 {
        return 0;
    } else if bytes[pos - 1] == line_term {
        pos -= 1;
    }
    loop {
        match bytes[..pos].rfind_byte(line_term) {
            None => {
                return 0;
            }
            Some(i) => {
                if count == 0 {
                    return i + 1;
                } else if i == 0 {
                    return 0;
                }
                count -= 1;
                pos = i;
            }
        }
    }
}

fn audit_c2_renamed(
    hay: &[u8],
    mut at: usize,
    term: u8,
    mut left: usize,
) -> usize {
    if at == 0 {
        return 0;
    } else if hay[at - 1] == term {
        at -= 1;
    }
    loop {
        match hay[..at].rfind_byte(term) {
            None => {
                return 0;
            }
            Some(j) => {
                if left == 0 {
                    return j + 1;
                } else if j == 0 {
                    return 0;
                }
                left -= 1;
                at = j;
            }
        }
    }
}

fn audit_c3_reordered(
    bytes: &[u8],
    mut pos: usize,
    line_term: u8,
    mut count: usize,
) -> usize {
    if pos == 0 {
        return 0;
    }
    let ends_with_term = bytes[pos - 1] == line_term;
    if ends_with_term {
        pos -= 1;
    }
    loop {
        let found = bytes[..pos].rfind_byte(line_term);
        let Some(i) = found else {
            return 0;
        };
        if i == 0 {
            return 0;
        }
        if count == 0 {
            return i + 1;
        }
        pos = i;
        count -= 1;
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn audit_p7_is_used_here() {
        assert_eq!(super::audit_p7_test_only(), 13);
    }
}
'''


def edit(path: Path, old: str, new: str) -> None:
    s = path.read_text(encoding="utf-8")
    if s.count(old) != 1:
        raise SystemExit(f"{path}: anchor found {s.count(old)} times: {old!r}")
    path.write_text(s.replace(old, new), encoding="utf-8")


def git(dst: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "user.name=plant", "-c", "user.email=plant@example.invalid", *args], cwd=dst,
                   check=True, capture_output=True)


def main(argv):
    src, dst = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    if dst.exists():
        raise SystemExit(f"{dst} exists")
    dst.mkdir(parents=True)
    arch = subprocess.run(["git", "archive", COMMIT], cwd=src, capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(dst)], input=arch, check=True)
    git(dst, "init", "-q")
    git(dst, "add", "-A")
    git(dst, "commit", "-q", "-m", "clean")

    s = dst / "crates/searcher/src"
    (s / "audit_plants.rs").write_text(PLANTS_RS, encoding="utf-8")
    edit(s / "lib.rs", "mod line_buffer;\n", "pub mod audit_plants;\nmod line_buffer;\n")
    # The cycle (lines -> audit_plants -> lines) and the layer break (lines -> sink).
    edit(s / "lines.rs", "    grep_matcher::{LineTerminator, Match},\n};\n",
         "    grep_matcher::{LineTerminator, Match},\n};\n\nuse crate::audit_plants::audit_cycle_back;\nuse crate::sink::SinkContextKind;\n\n"
         "pub(crate) fn audit_layer_break() -> (usize, Option<SinkContextKind>) {\n"
         "    (audit_cycle_back(), None)\n}\n")
    edit(s / "searcher/mod.rs", "        let path = path.as_ref();\n        let file = File::open(path)",
         "        let _ = crate::audit_plants::audit_live_hook();\n"
         "        let _ = crate::lines::audit_layer_break();\n"
         "        let path = path.as_ref();\n        let file = File::open(path)")
    edit(dst / "crates/matcher/src/lib.rs", "/// The type of a match.",
         "/// R1-C112 plant P3: used only from grep-searcher.\npub fn audit_p3_cross_crate() -> u32 {\n    3\n}\n\n"
         "/// The type of a match.")
    edit(dst / "crates/core/messages.rs", "/// Like eprintln,",
         "/// R1-C112 plant P2b: pub, in a private module of the binary crate, unused.\n"
         "pub fn audit_p2b_bin_unused() -> u32 {\n    12\n}\n\n/// Like eprintln,")
    git(dst, "add", "-A")
    git(dst, "commit", "-q", "-m", "plants")

    plants = {
        "commit": COMMIT,
        "dead": {"audit_p1_private_unused": "dead", "audit_p2_pub_unused": "dead", "audit_p2b_bin_unused": "dead",
                 "audit_p3_cross_crate": "alive", "audit_p4_dyn_only": "alive", "audit_p5_generic_only": "alive",
                 "audit_p6_macro_only": "alive", "audit_p7_test_only": "test-only"},
        "rustc_must_flag": ["audit_p1_private_unused", "audit_p2b_bin_unused"],
        "rustc_cannot_see": ["audit_p2_pub_unused"],
        "cycle": ["grep_searcher::audit_plants", "grep_searcher::lines"],
        "cycle_files": ["crates/searcher/src/audit_plants.rs", "crates/searcher/src/lines.rs"],
        "layer_rule": {"from": "grep_searcher::lines", "must_not_use": "grep_searcher::sink",
                       "files": ["crates/searcher/src/lines.rs", "crates/searcher/src/sink.rs"]},
        "clones": {"original": "preceding_by_pos", "audit_c1_exact": "exact", "audit_c2_renamed": "renamed",
                   "audit_c3_reordered": "reordered"},
    }
    dst.with_name(dst.name + ".plants.json").write_text(json.dumps(plants, indent=1) + "\n", encoding="utf-8")
    print(dst)


if __name__ == "__main__":
    main(sys.argv)

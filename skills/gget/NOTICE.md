# gget skill — provenance

This skill is **copied unmodified** from
[K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills),
path `scientific-skills/gget/`.

| | |
|---|---|
| Upstream repo | https://github.com/K-Dense-AI/scientific-agent-skills |
| Upstream path | `scientific-skills/gget/` |
| Upstream commit | `cbcae7bbf776cd41aeaa59ea06b8f0e6eacfb16f` |
| Copied at | 2026-05-16T05:17Z |
| Upstream skill author | K-Dense Inc. (preserved in `SKILL.md` frontmatter) |
| Upstream repo license | MIT — see [`LICENSE-UPSTREAM.md`](LICENSE-UPSTREAM.md) |
| Upstream skill-level license | BSD-2-Clause (declared in `SKILL.md` frontmatter) |

This skill wraps the [`gget`](https://github.com/pachterlab/gget) Python package
(also BSD-2-Clause), which provides unified CLI/Python access to ~20 genomics
databases (Ensembl, UniProt, NCBI, AlphaFold, Enrichr, ARCHS4, etc.).

## Why copy instead of fork?

The skill is small, useful, and complete. Forking and tracking upstream would add
maintenance overhead without value — the upstream is well-maintained and gget
itself is updated biweekly. If material upstream changes happen, refresh this
copy and update the commit hash above.

## Modifications

None. If we ever modify this skill, list the changes here.

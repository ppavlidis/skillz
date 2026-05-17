# Notable Cases — gene-annotations skill

Entries added during eval runs. Each entry: the case, the observation, why it matters, the lesson.

---

## 2026-05-17 — Cross-species annotation asymmetry: mouse Grin1 vs human GRIN1

**Case:** Eval 5, iteration-2. Prompt: "What's a GO annotation that mouse Grin1 has but human GRIN1 doesn't?"

**Observation:** Live GOA data showed 173 mouse-only GO terms vs only 2 human-only. The 173 mouse-only terms are dominated by IMP (Inferred from Mutant Phenotype) behavioral and neurological annotations: GO:0007613 (memory), GO:0007616 (long-term memory), GO:0001661 (conditioned taste aversion), GO:0035176 (social behavior), GO:0019233 (sensory perception of pain), GO:0008344 (adult locomotory behavior), and ~28 more. These all trace to decades of mouse knockin/knockout experiments — especially Tsien et al. 1996 hippocampus-specific Grin1 knockout and its successors. The 2 human-only terms are GO:0160212 (glycine-gated cation channel activity, ISS, added 2022) and GO:0098976 (excitatory chemical synaptic transmission, NAS) — both appear to be curation lag rather than biological difference. The biology is presumed fully conserved; human GRIN1 certainly contributes to memory.

**Why it matters:** A naive reading of the annotation difference would suggest mice have a richer functional repertoire than humans for this gene — manifestly false. The asymmetry is entirely an artifact of the experimental ecosystem: behavioral phenotyping requires intact animals, and mouse genetics is the workhorse. This is the canonical example of annotation-depth asymmetry masquerading as biological difference.

**Lesson:** When a cross-species annotation diff is dramatically asymmetric (173 vs 2), the default null hypothesis should be annotation-depth asymmetry, not biology. Flag the direction and evidence-code composition of the difference. IMP-heavy mouse-side differences almost always reflect available knockout data, not unique mouse function. The without_skill agent correctly intuited this from training but could not produce specific term IDs or counts — the skill made the quantitative case.

---

## 2026-05-17 — GO branch structure: GO:0000724 is not a child of GO:0035825 in OLS

**Case:** Eval 6, iteration-2. Prompt: "Does human BRCA1 have GO annotations in the homologous recombination branch? Use the ontology to define the branch first."

**Observation:** OLS search for "homologous recombination" surfaces GO:0035825 (homologous recombination) as the top hit. A naive approach would get GO:0035825's children and call that the HR branch. But GO:0000724 (double-strand break repair via homologous recombination) — the term that has BRCA1's IDA (experimental) annotation — is NOT a child of GO:0035825 in the OLS hierarchy. They sit in separate sub-hierarchies under DNA repair. The with_skill agent correctly started BFS from both roots (14 terms total), caught both annotations, and noted the structural nuance. BRCA1 has 2 direct HR-branch annotations: GO:0035825 (NAS) and GO:0000724 (IDA) — the latter being the experimentally-evidenced one.

**Why it matters:** The HR branch query is a textbook bioinformatics question. If you only traverse from GO:0035825 downward, you miss the most biologically important BRCA1 annotation (GO:0000724, IDA). The GO hierarchy for DNA repair is notoriously fragmented across is_a and part_of relations.

**Lesson:** Ontology-first queries should seed BFS from multiple candidate roots, not just the top search hit. Consider also checking `search` results beyond rank 1. The ontology-terms skill's children endpoint gives immediate children only — a BFS loop is needed for the full subtree. Document this in the SKILL.md compose pattern.

---

## 2026-05-17 — Evidence filtering: propagation inflates counts beyond what training knowledge predicts

**Case:** Eval 8, iteration-2. Prompt: "Give me human PTEN GO BP annotations backed by experimental evidence only."

**Observation:** Without_skill estimated 25–35 experimental terms for PTEN biological process (total ~70–90 BP annotations). Live data: 772 BP annotations total (all evidence), 364 experimental-only (IDA + IMP only — no IGI, IEP, IPI, or EXP codes found). The survival rate is 47.2%. The without_skill count was off by ~10x in raw rows. The discrepancy: training knowledge reasons about "unique GO terms" (of which there might indeed be ~30-50 distinct BP terms), but propagated annotations produce many rows per gene/term combination, inflating the table dramatically. The with_skill agent fetched real data, filtered correctly with a Python script, and reported the right numbers.

**Why it matters:** When a researcher asks "how many experimental annotations does gene X have," they usually want a row count from a filtered annotation table — not a count of unique terms. These can differ by an order of magnitude for well-studied genes. Training data reasoning about "terms" will systematically undercount annotation table rows.

**Lesson:** Distinguish "unique GO terms with experimental evidence" from "rows in the annotation table with experimental evidence codes." The skill should default to reporting both. The eval assertion should specify which count is expected — currently it doesn't distinguish, which is an eval design gap to fix in iteration-3.

---

## 2026-05-17 — MF comparison reveals annotation coverage differences for GRIN1 vs GRIA1

**Case:** Eval 7, iteration-2. Prompt: "Compare GO MF annotations of human GRIN1 and GRIA1."

**Observation:** GRIN1: 54 MF terms; GRIA1: 62 MF terms; 35 shared; 19 GRIN1-only; 27 GRIA1-only. The shared set includes glutamate receptor activity (GO:0004970) and calcium channel terms. GRIN1-unique terms correctly capture NMDA biology: NMDA receptor activity (GO:0004972), glycine binding (GO:0016594, co-agonist), calmodulin binding (GO:0005516, Ca²⁺-dependent inactivation), and voltage-gated channel activity (Mg²⁺ block). GRIA1-unique terms are dominated by protein interaction / trafficking scaffolding: PDZ domain binding (GO:0030165), myosin V binding (GO:0031489), protein kinase binding (GO:0019901), GTPase binding (GO:0051020). The without_skill agent named the right broad classes but missed specifics like calmodulin binding and had several GO IDs unknown.

**Why it matters:** The live annotation diff cleanly recapitulates the functional distinction between NMDA (coincidence detector requiring glycine co-agonist and voltage relief of Mg²⁺ block) and AMPA (trafficking-regulated, interacts with GRIP/PSD-95/PICK1 via PDZ domains) receptor biology. This is a strong validation case: the annotation DB encodes real functional knowledge that a comparison query can surface.

**Lesson:** Multi-gene MF comparison is a high-value use case where the skill's output is both more complete and more verifiable than training knowledge. The comparison TSV (term_id, term_label, present_in_A, present_in_B) is a reusable artifact format worth establishing as a standard output schema for this operation type.

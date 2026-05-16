"""GOA (Gene Ontology Annotation) via QuickGO at EBI.

QuickGO REST: https://www.ebi.ac.uk/QuickGO/services/annotation/search

Key params:
- goId: GO term to query
- geneProductId: gene to query (typed: UniProtKB:..., ENSEMBL:..., etc.)
- taxonId: species filter (9606 human, 10090 mouse, ...)
- goUsage: "descendants" → propagate down (default for genes_with_annotation when --direct is off)
           "ancestors"   → propagate up   (default for annotations_of_gene when --direct is off)
           "exact"       → direct only (when --direct is on)
- limit: page size (max 100); we walk pages

Server-side propagation is the killer feature here: no need to cross-reference
with the ontology hierarchy ourselves.
"""

from __future__ import annotations

import pandas as pd

from ._common import (
    SPECIES_TAXON,
    SourceInfo,
    classify_gene_input,
    die,
    http_get,
    require_module,
    resolve_symbol_to_uniprot,
    sha256_bytes,
)

SOURCE_NAME = "goa"
QUICKGO_BASE = "https://www.ebi.ac.uk/QuickGO/services"

PAGE_SIZE = 100  # QuickGO max
MAX_PAGES = 500  # 50,000-row safety cap; raise if needed
ONTOLOGY_BATCH_SIZE = 100  # max GO IDs per /ontology/go/terms call


def _ontology_terms_lookup(term_ids: list[str], requests) -> tuple[dict[str, dict], bytes]:
    """Batch-lookup GO term metadata (label, definition, ancestors).

    Returns (term_id → {name, aspect, ancestors[]}, concatenated raw bytes).
    Used to (a) fill in term_label in annotation outputs, and (b) compute
    ancestor propagation for annotations_of_gene.
    """
    out: dict[str, dict] = {}
    raw_concat = bytearray()
    unique = sorted(set(t for t in term_ids if t))
    for i in range(0, len(unique), ONTOLOGY_BATCH_SIZE):
        batch = unique[i : i + ONTOLOGY_BATCH_SIZE]
        ids_param = ",".join(batch)
        url = f"{QUICKGO_BASE}/ontology/go/terms/{ids_param}/ancestors"
        try:
            resp = http_get(url, requests, headers={"Accept": "application/json"}, timeout=60)
        except requests.RequestException as e:
            die(f"QuickGO ontology lookup failed: {e}", source=SOURCE_NAME)
        if not resp.ok:
            die(
                f"QuickGO ontology lookup HTTP {resp.status_code}: {resp.text[:300]}",
                source=SOURCE_NAME,
            )
        raw_concat.extend(resp.content)
        for entry in resp.json().get("results") or []:
            tid = entry.get("id")
            if not tid:
                continue
            out[tid] = {
                "name": entry.get("name") or "",
                "aspect": entry.get("aspect") or "",
                "ancestors": [a for a in (entry.get("ancestors") or []) if a != tid],
                "is_obsolete": bool(entry.get("isObsolete", False)),
            }
    return out, bytes(raw_concat)


def _fill_labels(df, label_map: dict[str, dict]) -> None:
    """Mutate df in place to populate term_label and term_aspect from label_map."""
    if df.empty:
        return
    df["term_label"] = df["term_id"].map(lambda t: label_map.get(t, {}).get("name", ""))
    # Only fill aspect when missing — QuickGO's annotation endpoint already returns it.
    needs_aspect = df["term_aspect"].isna() | (df["term_aspect"].fillna("") == "")
    if needs_aspect.any():
        df.loc[needs_aspect, "term_aspect"] = df.loc[needs_aspect, "term_id"].map(
            lambda t: label_map.get(t, {}).get("aspect", "")
        )


def _page(url: str, requests, params: dict, page: int) -> tuple[dict, bytes]:
    params2 = dict(params)
    params2["page"] = page
    params2["limit"] = PAGE_SIZE
    try:
        resp = http_get(url, requests, params=params2, headers={"Accept": "application/json"}, timeout=60)
    except requests.RequestException as e:
        die(f"QuickGO request failed: {e}", source=SOURCE_NAME)
    if resp.status_code == 429:
        die("QuickGO rate-limited (429); back off and retry later", source=SOURCE_NAME)
    if not resp.ok:
        die(f"QuickGO HTTP {resp.status_code}: {resp.text[:300]}", source=SOURCE_NAME)
    return resp.json(), resp.content


def _walk(url: str, requests, params: dict) -> tuple[list[dict], bytes]:
    """Walk pages until we've collected all results or hit the safety cap."""
    rows: list[dict] = []
    raw_concat = bytearray()
    expected = 0
    for page in range(1, MAX_PAGES + 1):
        payload, raw = _page(url, requests, params, page)
        raw_concat.extend(raw)
        page_results = payload.get("results") or []
        rows.extend(page_results)
        if not expected:
            expected = int(payload.get("numberOfHits") or 0)
        if not page_results or len(rows) >= expected:
            break
    return rows, bytes(raw_concat)


def _row_from_annotation(entry: dict, propagated: bool, species: str) -> dict:
    gp_id = entry.get("geneProductId") or ""
    symbol = entry.get("symbol") or ""
    # geneProductId is typed; split prefix.
    uniprot = ""
    if gp_id.startswith("UniProtKB:"):
        uniprot = gp_id.split(":", 1)[1]
    return {
        "gene_id": gp_id,
        "gene_symbol": symbol,
        "gene_uniprot": uniprot,
        "gene_entrez": "",
        "term_id": entry.get("goId") or "",
        "term_label": entry.get("goName") or "",
        "term_aspect": entry.get("goAspect") or "",
        "evidence_code": entry.get("goEvidence") or "",
        "qualifier": entry.get("qualifier") or "",
        "propagated": propagated,  # QuickGO doesn't flag per-row; whole call is one mode
        "species": species,
        "source": SOURCE_NAME,
    }


def genes_with_annotation(go_term: str, species: str, direct: bool, limit: int | None = None):
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    taxon = SPECIES_TAXON.get(species)
    if not taxon:
        die(f"unsupported species: {species}", source=SOURCE_NAME)
    url = f"{QUICKGO_BASE}/annotation/search"
    params = {
        "goId": go_term,
        "taxonId": taxon,
        "goUsage": "exact" if direct else "descendants",
    }
    annotations, raw = _walk(url, requests, params)
    # Per-row propagation flag: a row is "direct" iff its term_id equals the
    # query term; otherwise it's a descendant the user asked for via propagation.
    rows = []
    for a in annotations:
        row = _row_from_annotation(a, propagated=False, species=species)
        row["propagated"] = (row["term_id"] != go_term)
        row["propagated_from_term_id"] = ""  # for genes_with_annotation, direct rows came directly; no per-row chain
        rows.append(row)
    df = pd.DataFrame(rows, columns=[
        "gene_id", "gene_symbol", "gene_uniprot", "gene_entrez",
        "term_id", "term_label", "term_aspect",
        "evidence_code", "qualifier", "propagated",
        "species", "source", "propagated_from_term_id",
    ])
    label_map, raw_labels = _ontology_terms_lookup(df["term_id"].dropna().unique().tolist(), requests)
    _fill_labels(df, label_map)
    return df, SourceInfo(
        url=f"{url}?goId={go_term}&taxonId={taxon}&goUsage={'exact' if direct else 'descendants'}",
        version="QuickGO (current); fetched live; term labels filled via /ontology/go/terms",
        sha256=sha256_bytes(raw + b"\n--LABELS--\n" + raw_labels),
        extras={"n_annotations_returned": len(rows), "n_unique_terms_resolved": len(label_map),
                "n_direct": int((~df["propagated"]).sum()), "n_propagated": int(df["propagated"].sum())},
    )


def annotations_of_gene(gene_input: str, species: str, direct: bool):
    requests = require_module("requests", "pip install requests", SOURCE_NAME)
    taxon = SPECIES_TAXON.get(species)
    if not taxon:
        die(f"unsupported species: {species}", source=SOURCE_NAME)

    # Resolve the gene_input to a typed gene-product ID QuickGO accepts.
    cls = classify_gene_input(gene_input)
    resolved_info: dict = {"input_class": cls, "resolved_input": gene_input}
    if cls == "symbol":
        accession, info = resolve_symbol_to_uniprot(gene_input, species, requests)
        gene_product_id = f"UniProtKB:{accession}"
        resolved_info["uniprot_resolved_from_symbol"] = info
        resolved_info["resolved_input"] = gene_product_id
    elif cls == "uniprot_prefixed":
        gene_product_id = gene_input
    elif cls == "entrez":
        # QuickGO doesn't take bare Entrez IDs; we need to use NCBI-prefixed form
        # or resolve via UniProt. Easiest cross-walk: use UniProt accession via
        # idmapping API. For v0.1: tell the user to give us a UniProt accession.
        die(
            f"bare Entrez gene IDs ({gene_input}) are not accepted by GOA's annotation API. "
            f"Pass UniProtKB:ACCESSION or the gene symbol instead, or use --source gene2go.",
            source=SOURCE_NAME,
        )
    elif cls == "ensembl":
        # QuickGO accepts ENSEMBL:ID prefix.
        if gene_input.startswith("ENSEMBL:"):
            gene_product_id = gene_input
        else:
            gene_product_id = f"ENSEMBL:{gene_input}"
    else:  # other_prefixed
        gene_product_id = gene_input

    # QuickGO's goUsage only supports {exact, descendants, slim}. There's no
    # server-side "ancestors" for annotations_of_gene, so v0.1 always returns
    # direct annotations from QuickGO for this op. Ancestor propagation (the
    # GO true-path rule) requires client-side hierarchy traversal and is
    # deferred to v0.2 (it would call into ontology-terms for the term
    # closure). If the user passed --direct, that matches the v0.1 behavior;
    # if they didn't, we warn via the extras that propagation wasn't applied.
    url = f"{QUICKGO_BASE}/annotation/search"
    params = {
        "geneProductId": gene_product_id,
        "taxonId": taxon,
    }
    annotations, raw = _walk(url, requests, params)
    direct_rows = [_row_from_annotation(a, propagated=False, species=species) for a in annotations]
    df_direct = pd.DataFrame(direct_rows, columns=[
        "gene_id", "gene_symbol", "gene_uniprot", "gene_entrez",
        "term_id", "term_label", "term_aspect",
        "evidence_code", "qualifier", "propagated",
        "species", "source",
    ])

    # Resolve labels + ancestors in one batch call.
    direct_term_ids = df_direct["term_id"].dropna().unique().tolist()
    label_map, raw_lookup = _ontology_terms_lookup(direct_term_ids, requests)
    _fill_labels(df_direct, label_map)

    if direct:
        final_df = df_direct
    else:
        # Apply ancestor propagation client-side (GO true-path rule).
        # Step 1: collect every ancestor referenced by any direct term.
        all_ancestors_needed: set[str] = set()
        for tid in direct_term_ids:
            for anc in label_map.get(tid, {}).get("ancestors", []):
                all_ancestors_needed.add(anc)
        # Step 2: ensure we have labels for every ancestor too. The first
        # batch lookup returned ancestor IDs but not names for those nested
        # IDs — do a second batch to resolve them.
        unlabelled = [a for a in all_ancestors_needed if a not in label_map]
        if unlabelled:
            extra_map, raw_extra = _ontology_terms_lookup(unlabelled, requests)
            label_map.update(extra_map)
            raw_lookup = raw_lookup + b"\n--ANC-LABELS--\n" + raw_extra

        # Step 3: build the propagated rows. Each direct annotation row begets
        # one propagated row per ancestor, inheriting evidence/qualifier but
        # flagged propagated=True. Dedupe propagated rows on
        # (gene, term, evidence, qualifier) so multi-direct-source dupes
        # collapse but distinct-evidence variants persist.
        propagated_rows: list[dict] = []
        for _idx, drow in df_direct.iterrows():
            tid = drow["term_id"]
            for anc in label_map.get(tid, {}).get("ancestors", []):
                anc_meta = label_map.get(anc, {})
                propagated_rows.append({
                    "gene_id": drow["gene_id"],
                    "gene_symbol": drow["gene_symbol"],
                    "gene_uniprot": drow["gene_uniprot"],
                    "gene_entrez": drow["gene_entrez"],
                    "term_id": anc,
                    "term_label": anc_meta.get("name", ""),
                    "term_aspect": anc_meta.get("aspect", drow["term_aspect"]),
                    "evidence_code": drow["evidence_code"],
                    "qualifier": drow["qualifier"],
                    "propagated": True,
                    "species": species,
                    "source": SOURCE_NAME,
                    "propagated_from_term_id": tid,
                })

        df_direct["propagated_from_term_id"] = ""
        df_propagated = pd.DataFrame(propagated_rows, columns=df_direct.columns.tolist())

        # Remove propagated rows that duplicate a direct (gene, term, evidence,
        # qualifier) row — when there's a direct annotation for the ancestor,
        # we don't need a propagated one with the same evidence/qualifier.
        if len(df_propagated):
            direct_keys = set(zip(
                df_direct["gene_id"], df_direct["term_id"],
                df_direct["evidence_code"], df_direct["qualifier"],
            ))
            df_propagated = df_propagated[~df_propagated.apply(
                lambda r: (r["gene_id"], r["term_id"], r["evidence_code"], r["qualifier"]) in direct_keys,
                axis=1,
            )]
            df_propagated = df_propagated.drop_duplicates(
                subset=["gene_id", "term_id", "evidence_code", "qualifier"]
            ).reset_index(drop=True)

        final_df = pd.concat([df_direct, df_propagated], ignore_index=True)

    return final_df, SourceInfo(
        url=f"{url}?geneProductId={gene_product_id}&taxonId={taxon} + ontology lookup",
        version="QuickGO (current); fetched live; labels + ancestor propagation applied client-side",
        sha256=sha256_bytes(raw + b"\n--LOOKUP--\n" + raw_lookup),
        extras={
            "resolved_input": resolved_info,
            "n_direct_annotations": len(df_direct),
            "n_unique_direct_terms": len(direct_term_ids),
            "n_total_rows_after_propagation": int(len(final_df)) if not direct else int(len(df_direct)),
        },
    )

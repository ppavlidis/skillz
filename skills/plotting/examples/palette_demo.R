#!/usr/bin/env Rscript
# Demo of the five approved divergent palettes + black-body sequential.
# Renders the same Z-scored expression matrix with each palette for comparison.
# Run from skills/plotting/:
#   Rscript examples/palette_demo.R

suppressPackageStartupMessages({
  source("R/palettes.R")
  library(pheatmap)
})

set.seed(42)
n_genes <- 30; n_samples <- 16
expr <- matrix(rnorm(n_genes * n_samples), nrow = n_genes,
               dimnames = list(paste0("Gene", seq_len(n_genes)),
                               paste0("S",    seq_len(n_samples))))
expr[1:10, 1:8]   <- expr[1:10, 1:8]   + 2.5
expr[1:10, 9:16]  <- expr[1:10, 9:16]  - 2.5
expr[20:25, 1:8]  <- expr[20:25, 1:8]  - 1.5
expr[20:25, 9:16] <- expr[20:25, 9:16] + 1.5
expr[sample(length(expr), 8)] <- NA

z <- t(scale(t(expr)))
z[!is.na(z) & z >  3] <-  3
z[!is.na(z) & z < -3] <- -3

.heat <- function(pal, name) {
  n   <- length(pal)
  brk <- seq(-3, 3, length.out = n + 1)
  pheatmap::pheatmap(
    z, cluster_rows = FALSE, cluster_cols = FALSE,
    show_rownames = FALSE, show_colnames = FALSE,
    color = pal, breaks = brk,
    na_col = "grey80", main = name, silent = FALSE
  )
}

out_pdf <- file.path(tempdir(), "pavlab_palettes.pdf")
pdf(out_pdf, width = 7, height = 5.5, onefile = TRUE)

# ── Divergent (black at zero) ────────────────────────────────────────────────
.heat(divergent_palette(),            "amber-orange -> black -> sky-blue  [DEFAULT]")
.heat(divergent_palette_rdbu(),       "Brewer-RdBu mid -> red / blue")
.heat(divergent_palette_spectral(),   "Spectral mid -> red-orange / cool-blue")
.heat(divergent_palette_cyan_yellow(),"cyan -> black -> yellow  [high pop]")
.heat(divergent_palette_blue_yellow(),"blue -> black -> yellow  [classic]")

# ── Sequential (black-body, for raw / all-positive) ─────────────────────────
pos <- pmax(z, 0)  # pretend non-negative data
breaks_seq <- seq(0, 3, length.out = 258)
pheatmap::pheatmap(
  pos, cluster_rows = FALSE, cluster_cols = FALSE,
  show_rownames = FALSE, show_colnames = FALSE,
  color = black_body_palette(257),
  breaks = breaks_seq, na_col = "grey80",
  main = "black-body sequential  [raw / all-positive]", silent = FALSE
)

dev.off()
cat("wrote", out_pdf, "(6 pages)\n")

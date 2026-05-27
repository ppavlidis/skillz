#!/usr/bin/env Rscript
# Demo: produce one heatmap per mode against synthetic data and write them to
# the per-user tempdir. Run via:
#   Rscript examples/heatmap_demo.R
# (from the plotting/ directory).

suppressPackageStartupMessages({
  source("R/palettes.R")
  source("R/pavlab_heatmap.R")
})

set.seed(42)
out_dir <- file.path(tempdir(), "pavlab_heatmap_demo")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

# ---- 1. Expression heatmap: 20 genes x 12 samples, planted block signal ----
n_genes <- 20
n_samples <- 12
expr <- matrix(rnorm(n_genes * n_samples), nrow = n_genes,
               dimnames = list(paste0("Gene", 1:n_genes),
                               paste0("S", 1:n_samples)))
# Inject signal: first 5 genes high in samples 1-6, low in 7-12.
expr[1:5, 1:6] <- expr[1:5, 1:6] + 2.5
expr[1:5, 7:12] <- expr[1:5, 7:12] - 2.5

p1 <- file.path(out_dir, "01_expression.png")
pavlab_heatmap(expr, filename = p1, width = 6, height = 5)
cat("wrote ", p1, "\n", sep = "")

# ---- 2. Correlation heatmap: NA on diagonal, divergent palette ----
cor_mat <- cor(t(expr))
p2 <- file.path(out_dir, "02_correlation.png")
pavlab_heatmap(cor_mat, mode = "correlation", filename = p2,
               width = 6, height = 5)
cat("wrote ", p2, "\n", sep = "")

# ---- 3. Raw non-negative data: sequential black-body palette ----
raw_pos <- matrix(rpois(n_genes * n_samples, lambda = 10) + 1,
                  nrow = n_genes,
                  dimnames = dimnames(expr))
p3 <- file.path(out_dir, "03_raw_positive.png")
pavlab_heatmap(raw_pos, mode = "raw", filename = p3, width = 6, height = 5)
cat("wrote ", p3, "\n", sep = "")

# ---- 4. Big matrix: labels auto-hide ----
big <- matrix(rnorm(80 * 40), nrow = 80,
              dimnames = list(paste0("g", 1:80), paste0("s", 1:40)))
p4 <- file.path(out_dir, "04_big_labels_auto_hide.png")
pavlab_heatmap(big, filename = p4, width = 7, height = 7)
cat("wrote ", p4, "\n", sep = "")

# ---- 5. Matrix with missing values: grey cells ----
sparse <- expr
sparse[sample(length(sparse), size = 15)] <- NA
p5 <- file.path(out_dir, "05_with_missing.png")
pavlab_heatmap(sparse, filename = p5, width = 6, height = 5)
cat("wrote ", p5, "\n", sep = "")

cat("\nDemo complete. Outputs in: ", out_dir, "\n", sep = "")

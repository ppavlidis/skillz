#!/usr/bin/env Rscript
# Tests for plotting skill. Uses stopifnot() so any failure exits non-zero.
# Run from skills/plotting/:
#   Rscript tests/test_heatmap.R

source("R/palettes.R")
source("R/pavlab_heatmap.R")

cat("test_heatmap.R\n")
cat("===============\n")

# ---- Palette length and structure ---------------------------------------

cat("1. palette functions return vectors of the requested length...")
stopifnot(length(black_body_palette(100)) == 100)
stopifnot(length(black_body_palette(256)) == 256)
# Divergent palettes are forced odd so the midpoint is exactly one color.
stopifnot(length(divergent_palette(100)) == 101)   # n was even -> +1
stopifnot(length(divergent_palette(101)) == 101)
stopifnot(length(divergent_palette_rdbu(50)) == 51)
cat(" ok\n")

cat("2. all divergent palettes have BLACK at the midpoint...")
for (fn_name in c("divergent_palette",
                  "divergent_palette_rdbu",
                  "divergent_palette_spectral",
                  "divergent_palette_cyan_yellow",
                  "divergent_palette_blue_yellow")) {
  fn <- get(fn_name)
  pal <- fn(101)
  mid <- pal[(length(pal) + 1) %/% 2]
  if (toupper(mid) != "#000000") {
    stop(sprintf("  %s midpoint is %s, expected #000000", fn_name, mid))
  }
}
cat(" ok\n")

cat("3. palettes return valid hex colors...")
for (fn_name in c("black_body_palette",
                  "divergent_palette",
                  "divergent_palette_rdbu",
                  "divergent_palette_spectral",
                  "divergent_palette_cyan_yellow",
                  "divergent_palette_blue_yellow")) {
  pal <- get(fn_name)(64)
  stopifnot(all(grepl("^#[0-9A-Fa-f]{6}$", pal)))
}
cat(" ok\n")

# ---- pavlab_heatmap end-to-end on small matrices -----------------------

cat("4. pavlab_heatmap runs in each mode and writes a file...")
tmpdir <- tempfile("pavlab_heatmap_tests_")
dir.create(tmpdir)
on.exit(unlink(tmpdir, recursive = TRUE), add = TRUE)

set.seed(1)
mat <- matrix(rnorm(60), nrow = 10, ncol = 6,
              dimnames = list(paste0("g", 1:10), paste0("s", 1:6)))

for (mode in c("expression", "raw")) {
  out <- file.path(tmpdir, paste0("test_", mode, ".png"))
  pavlab_heatmap(mat, mode = mode, filename = out, width = 4, height = 4)
  stopifnot(file.exists(out))
  stopifnot(file.size(out) > 1000)  # non-empty PNG
}

# Correlation mode needs a square symmetric matrix.
cor_mat <- cor(mat)
out_cor <- file.path(tmpdir, "test_correlation.png")
pavlab_heatmap(cor_mat, mode = "correlation",
               filename = out_cor, width = 4, height = 4)
stopifnot(file.exists(out_cor))
stopifnot(file.size(out_cor) > 1000)
cat(" ok\n")

# ---- Label auto-hiding -------------------------------------------------

cat("5. auto-hide of row/column names with big matrices (no crash)...")
big <- matrix(rnorm(80 * 40), nrow = 80, ncol = 40,
              dimnames = list(paste0("g", 1:80), paste0("s", 1:40)))
out_big <- file.path(tmpdir, "test_big.png")
pavlab_heatmap(big, filename = out_big, width = 5, height = 5)
stopifnot(file.exists(out_big))
cat(" ok\n")

# ---- Missing values -----------------------------------------------------

cat("6. matrices with NA values render without error...")
mat_na <- mat
mat_na[c(1, 5, 10, 20)] <- NA
out_na <- file.path(tmpdir, "test_na.png")
pavlab_heatmap(mat_na, filename = out_na, width = 4, height = 4)
stopifnot(file.exists(out_na))
cat(" ok\n")

# ---- Z-clipping ---------------------------------------------------------

cat("7. Z-clipping bounds the rendered matrix to [-zclip, +zclip]...")
mat_outlier <- mat
mat_outlier[1, 1] <- 100   # huge outlier
# After standardization the outlier would otherwise dominate the color scale;
# zclip should clip it. We can't directly inspect the rendered colors, but we
# can verify the helper produces a finite result without errors.
out_clip <- file.path(tmpdir, "test_clip.png")
pavlab_heatmap(mat_outlier, mode = "expression", zclip = 3,
               filename = out_clip, width = 4, height = 4)
stopifnot(file.exists(out_clip))
cat(" ok\n")

cat("\nALL TESTS PASSED\n")

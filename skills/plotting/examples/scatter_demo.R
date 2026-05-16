#!/usr/bin/env Rscript
# Demonstration of pavlab_scatter (R / ggplot2).
# Produces five PNG demo figures in a temp directory.
# Run from skills/plotting/:
#   Rscript examples/scatter_demo.R

source("R/palettes.R")
source("R/pavlab_scatter.R")

set.seed(42)
n <- 200

out_dir <- file.path(tempdir(), "pavlab_scatter_demo_R")
dir.create(out_dir, showWarnings = FALSE)

# ---- 1. Basic black scatter -------------------------------------------------

x <- rnorm(n)
y <- x + rnorm(n, sd = 0.5)

pavlab_scatter(x, y,
               xlabel = "Variable X", ylabel = "Variable Y",
               title  = "Basic scatter — black circles",
               filename = file.path(out_dir, "01_basic.png"))
cat("1. 01_basic.png\n")

# ---- 2. Log2 axes (replicate comparison) ------------------------------------

tpm1 <- exp(rnorm(n, mean = 4)) + 0.5
tpm2 <- tpm1 * exp(rnorm(n, sd = 0.4))

suppressWarnings(
  pavlab_scatter(tpm1, tpm2,
                 xlabel = "TPM rep1", ylabel = "TPM rep2",
                 log_x = "log2", log_y = "log2",
                 title  = "Replicate comparison (log₂ axes)",
                 filename = file.path(out_dir, "02_log2.png"))
)
cat("2. 02_log2.png\n")

# ---- 3. Categorical colour → accent palette + legend ------------------------

cell_types <- sample(c("Neurons", "Astrocytes", "Microglia", "Oligodendrocytes"),
                     n, replace = TRUE)
pc1 <- rnorm(n)
pc2 <- rnorm(n)

pavlab_scatter(pc1, pc2,
               color  = cell_types,
               xlabel = "PC1", ylabel = "PC2",
               origin_zero = FALSE,
               title  = "PCA coloured by cell type",
               filename = file.path(out_dir, "03_categorical.png"))
cat("3. 03_categorical.png\n")

# ---- 4. Numeric colour → viridis colorbar -----------------------------------

scores <- runif(n)

pavlab_scatter(x, y,
               color       = scores,
               color_label = "score",
               xlabel      = "Variable X", ylabel = "Variable Y",
               origin_zero = FALSE,
               title       = "Continuous colour (viridis)",
               filename    = file.path(out_dir, "04_numeric_color.png"))
cat("4. 04_numeric_color.png\n")

# ---- 5. Extending with a ggplot2 layer (identity line) ----------------------

p5 <- suppressWarnings(
  pavlab_scatter(tpm1, tpm2,
                 xlabel = "TPM rep1", ylabel = "TPM rep2",
                 log_x = "log2", log_y = "log2",
                 title  = "With identity line (extended via ggplot2 +)")
)
p5 <- p5 + ggplot2::geom_abline(slope = 1, intercept = 0,
                                 linetype = "dashed", color = "#6b7280",
                                 linewidth = 0.5)
ggplot2::ggsave(file.path(out_dir, "05_identity_line.png"), plot = p5,
                width = 5.5, height = 5.0, dpi = 150)
cat("5. 05_identity_line.png\n")

cat(sprintf("\nDone. Five PNGs written to: %s\n", out_dir))

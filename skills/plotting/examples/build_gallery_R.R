#!/usr/bin/env Rscript
# Build R figures for the pavlab-plotting gallery.
# Called automatically by build_gallery.py; can also be run standalone:
#   Rscript examples/build_gallery_R.R
# Must be run from skills/plotting/.

if (!requireNamespace("ggplot2", quietly = TRUE))
  stop("ggplot2 required: install.packages('ggplot2')")

suppressPackageStartupMessages({
  source("R/palettes.R")
  source("R/pavlab_scatter.R")
  source("R/pavlab_stripchart.R")
  source("R/pavlab_density.R")
  source("R/pavlab_heatmap.R")
})

OUT <- file.path("examples", "gallery")
dir.create(OUT, recursive = TRUE, showWarnings = FALSE)

set.seed(42)

SZ       <- c(3.0, 2.8)   # standard compact
SZ_STRIP <- c(3.8, 2.8)   # strip/violin: extra width for group-name x-labels
SZ_HEX   <- c(3.8, 2.8)   # hexbin: extra width for colorbar
SZ_H     <- c(3.2, 3.2)   # heatmap
SZ_W     <- c(5.6, 2.4)   # wide (faceted)

.q <- function(expr) suppressWarnings(expr)

cat("R gallery figures\n")

# ── shared data helpers ────────────────────────────────────────────────────

.expr_mat <- function() {
  n_genes <- 12; n_samples <- 8
  m <- matrix(rnorm(n_genes * n_samples), n_genes, n_samples)
  m[1:4, 1:4] <- m[1:4, 1:4] + 2.5
  m[1:4, 5:8] <- m[1:4, 5:8] - 2.5
  rownames(m) <- sprintf("Gene%02d", seq_len(n_genes))
  colnames(m) <- sprintf("S%d",      seq_len(n_samples))
  m
}

.dens_data <- function(n_per = 200) {
  groups <- rep(c("ctrl","het","hom"), each = n_per)
  vals <- c(
    rlnorm(n_per, meanlog = 2.0, sdlog = 0.8),
    rlnorm(n_per, meanlog = 2.5, sdlog = 0.85),
    rlnorm(n_per, meanlog = 3.0, sdlog = 0.9)
  )
  list(groups = groups, vals = vals)
}

# ── heatmap ───────────────────────────────────────────────────────────────

cat("  heatmap_expression ... ")
.q(pavlab_heatmap(.expr_mat(),
                  filename = file.path(OUT, "heatmap_expression_r.png"),
                  width = SZ_H[1], height = SZ_H[2]))
cat("ok\n")

cat("  heatmap_correlation ... ")
.q(pavlab_heatmap(cor(t(.expr_mat())), mode = "correlation",
                  filename = file.path(OUT, "heatmap_correlation_r.png"),
                  width = SZ_H[1], height = SZ_H[2]))
cat("ok\n")

cat("  heatmap_raw ... ")
raw_m <- abs(matrix(rnorm(12 * 8), 12, 8)) * 5 + 0.5
rownames(raw_m) <- sprintf("Gene%02d", 1:12)
colnames(raw_m) <- sprintf("S%d", 1:8)
.q(pavlab_heatmap(raw_m, mode = "raw",
                  filename = file.path(OUT, "heatmap_raw_r.png"),
                  width = SZ_H[1], height = SZ_H[2]))
cat("ok\n")

cat("  heatmap_big ... ")
big_m <- matrix(rnorm(90 * 45), 90, 45)
rownames(big_m) <- paste0("g", 1:90)
colnames(big_m) <- paste0("c", 1:45)
.q(pavlab_heatmap(big_m,
                  filename = file.path(OUT, "heatmap_big_r.png"),
                  width = 3.6, height = 3.2))
cat("ok\n")

# ── scatter ───────────────────────────────────────────────────────────────

cat("  scatter_basic ... ")
x_b <- runif(80, 0.5, 8.0)
y_b <- pmax(x_b * 0.85 + rnorm(80, 0, 0.7), 0.1)
.q(pavlab_scatter(x_b, y_b, xlabel = "X", ylabel = "Y",
                  title = "Basic scatter", label_size = "large",
                  filename = file.path(OUT, "scatter_basic_r.png"),
                  figsize = SZ))
cat("ok\n")

cat("  scatter_log2 ... ")
tpm1 <- rlnorm(250, meanlog = 2.0, sdlog = 2.0)
tpm2 <- tpm1 * rlnorm(250, meanlog = 0, sdlog = 0.35)
p_log2 <- .q(pavlab_scatter(tpm1, tpm2,
                              xlabel = "TPM rep 1", ylabel = "TPM rep 2",
                              log_x = "log2", log_y = "log2",
                              label_size = "large",
                              title = "Replicate comparison (log₂)"))
p_log2 <- p_log2 + ggplot2::geom_abline(slope = 1, intercept = 0,
                                          linetype = "dashed", color = "#9ca3af",
                                          linewidth = 0.5)
ggplot2::ggsave(file.path(OUT, "scatter_log2_r.png"), plot = p_log2,
                width = SZ[1], height = SZ[2], dpi = 150)  # explicit 150 to match Python
cat("ok\n")

cat("  scatter_categorical ... ")
n_c <- 150
pc1 <- c(rnorm(50,-2,1), rnorm(50,1,0.8), rnorm(50,0,1.2))
pc2 <- c(rnorm(50, 1,.9), rnorm(50,-1,.7), rnorm(50,2,1.0))
cell_types <- rep(c("Neuron","Astrocyte","Microglia"), each = 50)
.q(pavlab_scatter(pc1, pc2, color = cell_types,
                  xlabel = "PC1 (34%)", ylabel = "PC2 (18%)",
                  origin_zero = FALSE, label_size = "large",
                  filename = file.path(OUT, "scatter_categorical_r.png"),
                  figsize = c(3.8, 2.8)))
cat("ok\n")

cat("  scatter_numeric ... ")
x_n <- rnorm(200); y_n <- x_n * 0.6 + rnorm(200, 0, 0.8)
scores <- (x_n + 3) / 6
.q(pavlab_scatter(x_n, y_n, color = scores, color_label = "score",
                  origin_zero = FALSE, xlabel = "X", ylabel = "Y",
                  label_size = "large",
                  filename = file.path(OUT, "scatter_numeric_r.png"),
                  figsize = SZ))
cat("ok\n")

cat("  scatter_hexbin ... ")
n_h <- 25000
xh <- rnorm(n_h); yh <- xh * 0.65 + rnorm(n_h, 0, 0.76)
.q(pavlab_scatter(xh, yh, origin_zero = FALSE,
                  xlabel = "X", ylabel = "Y",
                  title = sprintf("N = %s — hexbin", format(n_h, big.mark = ",")),
                  label_size = "large",
                  filename = file.path(OUT, "scatter_hexbin_r.png"),
                  figsize = SZ_HEX))
cat("ok\n")

# ── stripchart ────────────────────────────────────────────────────────────

.strip_data <- function(n_per = 50) {
  groups <- rep(c("Neuron","Astrocyte","Microglia"), each = n_per)
  vals   <- c(rlnorm(n_per, 2.5, 0.8),
               rlnorm(n_per, 1.9, 0.9),
               rlnorm(n_per, 2.2, 1.0))
  list(groups = groups, vals = vals)
}

cat("  strip_basic ... ")
d_s <- .strip_data()
.q(pavlab_stripchart(d_s$groups, d_s$vals,
                     xlabel = "Cell type", ylabel = "TPM",
                     log_y = "log2", label_size = "large",
                     filename = file.path(OUT, "strip_basic_r.png"),
                     figsize = SZ_STRIP))
cat("ok\n")

cat("  strip_color ... ")
n_per_c <- 30
strip_groups <- rep(c("Neuron","Astrocyte","Microglia"), each = n_per_c * 2)
strip_treat  <- rep(rep(c("ctrl","kd"), n_per_c), 3)
strip_base   <- c(rlnorm(n_per_c*2,2.5,.8), rlnorm(n_per_c*2,1.9,.9), rlnorm(n_per_c*2,2.2,1.0))
strip_vals   <- strip_base * ifelse(strip_treat == "kd", 0.55, 1.0)
.q(pavlab_stripchart(strip_groups, strip_vals,
                     color = strip_treat, color_label = "Treatment",
                     xlabel = "Cell type", ylabel = "TPM",
                     log_y = "log2", label_size = "large",
                     filename = file.path(OUT, "strip_color_r.png"),
                     figsize = SZ_STRIP))
cat("ok\n")

cat("  strip_mean_median ... ")
geno  <- rep(c("ctrl","het","hom"), each = 50)
score <- c(rnorm(50,5.1,.9), rnorm(50,5.8,1.0), rnorm(50,6.5,1.1))
pavlab_stripchart(geno, score,
                  show_mean = TRUE, show_median = TRUE,
                  xlabel = "Genotype", ylabel = "Score",
                  order = c("ctrl","het","hom"),
                  label_size = "large",
                  filename = file.path(OUT, "strip_mean_median_r.png"),
                  figsize = SZ_STRIP)
cat("ok\n")

cat("  strip_log ... ")
d_l <- .strip_data(n_per = 60)
.q(pavlab_stripchart(d_l$groups, d_l$vals,
                     log_y = "log2", origin_zero = FALSE,
                     xlabel = "Cell type",
                     ylabel = "Expression (log₂ TPM+1)",
                     label_size = "large",
                     filename = file.path(OUT, "strip_log_r.png"),
                     figsize = SZ_STRIP))
cat("ok\n")

# ── density / histogram / violin ─────────────────────────────────────────

cat("  density_single ... ")
d_d <- .dens_data(300)
.q(pavlab_density(d_d$vals, xlabel = "Expression",
                  label_size = "large",
                  filename = file.path(OUT, "density_single_r.png"),
                  figsize = SZ))
cat("ok\n")

cat("  density_reflect ... ")
d_exp <- rexp(400, rate = 0.5)
.q(pavlab_density(d_exp, reflect_bounds = TRUE,
                  xlabel = "Expression (AU)",
                  label_size = "large",
                  filename = file.path(OUT, "density_reflect_r.png"),
                  figsize = SZ))
cat("ok\n")

cat("  density_grouped ... ")
d_g <- .dens_data(150)
.q(pavlab_density(d_g$vals, groups = d_g$groups, kind = "density",
                  order = c("ctrl","het","hom"),
                  xlabel = "Expression", label_size = "large",
                  filename = file.path(OUT, "density_grouped_r.png"),
                  figsize = SZ))
cat("ok\n")

cat("  density_faceted ... ")
d_g2 <- .dens_data(150)
.q(pavlab_density(d_g2$vals, groups = d_g2$groups, kind = "density",
                  facet = TRUE, order = c("ctrl","het","hom"),
                  xlabel = "Expression", label_size = "large",
                  filename = file.path(OUT, "density_faceted_r.png"),
                  figsize = SZ_W))
cat("ok\n")

cat("  histogram_basic ... ")
d_h <- .dens_data(200)
.q(pavlab_density(d_h$vals, kind = "histogram", stat = "count",
                  xlabel = "Expression", label_size = "large",
                  filename = file.path(OUT, "histogram_basic_r.png"),
                  figsize = SZ))
cat("ok\n")

cat("  histogram_faceted ... ")
d_hf <- .dens_data(200)
.q(pavlab_density(d_hf$vals, groups = d_hf$groups,
                  kind = "histogram", facet = TRUE, stat = "count",
                  log_x = "log2", order = c("ctrl","het","hom"),
                  xlabel = "Expression", label_size = "large",
                  filename = file.path(OUT, "histogram_faceted_r.png"),
                  figsize = SZ_W))
cat("ok\n")

cat("  violin_basic ... ")
d_v <- .dens_data(120)
.q(pavlab_density(d_v$vals, groups = d_v$groups, kind = "violin",
                  xlabel = "Condition", ylabel = "Expression",
                  order = c("ctrl","het","hom"),
                  label_size = "large",
                  filename = file.path(OUT, "violin_basic_r.png"),
                  figsize = SZ_STRIP))
cat("ok\n")

cat("  violin_mean_median ... ")
d_vm <- .dens_data(120)
pavlab_density(d_vm$vals, groups = d_vm$groups, kind = "violin",
               show_mean = TRUE, show_median = TRUE,
               xlabel = "Condition", ylabel = "Expression",
               order = c("ctrl","het","hom"),
               label_size = "large",
               filename = file.path(OUT, "violin_mean_median_r.png"),
               figsize = SZ_STRIP)
cat("ok\n")

cat("\nR gallery figures complete.\n")

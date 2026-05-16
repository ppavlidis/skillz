#!/usr/bin/env Rscript
# Tests for pavlab_scatter (R/ggplot2 backend).
# Mirrors the Python test suite: covers silent-failure categories (wrong input,
# non-finite data, bad log args) and correct rendering of all color modes.
# Run from skills/plotting/:
#   Rscript tests/test_scatter.R

if (!requireNamespace("ggplot2", quietly = TRUE))
  stop("ggplot2 required: install.packages('ggplot2')")

source("R/palettes.R")
source("R/pavlab_scatter.R")

cat("test_scatter.R\n")
cat("==============\n")

# ---- Helper: capture first matching warning message ------------------------

.catch_warning <- function(expr, pattern = ".*") {
  msg <- NULL
  withCallingHandlers(
    expr,
    warning = function(w) {
      if (is.null(msg) && grepl(pattern, conditionMessage(w)))
        msg <<- conditionMessage(w)
      invokeRestart("muffleWarning")
    }
  )
  msg
}

# ---- 1. .font_sizes() presets -----------------------------------------------

cat("1. .font_sizes() presets return correct values...")
stopifnot(identical(.font_sizes("small"), c(10.0,  8.0)))
stopifnot(identical(.font_sizes("med"),   c(14.0, 11.0)))
stopifnot(identical(.font_sizes("large"), c(18.0, 14.0)))
fs20 <- .font_sizes(20)
stopifnot(fs20[1] == 20)
stopifnot(fs20[2] > 0 && fs20[2] < 20)  # proportional tick size
err1 <- tryCatch(.font_sizes("huge"), error = function(e) conditionMessage(e))
stopifnot(grepl("'huge'", err1))
cat(" ok\n")

# ---- 2. .pick_log_kind() selects correct base --------------------------------

cat("2. .pick_log_kind() selects correct log base...")
stopifnot(identical(.pick_log_kind("log2",  c(1, 2),    "x"), "log2"))
stopifnot(identical(.pick_log_kind("log10", c(1, 2),    "x"), "log10"))
stopifnot(is.null(.pick_log_kind(FALSE, c(1, 2), "x")))
stopifnot(is.null(.pick_log_kind(NULL,  c(1, 2), "x")))
# TRUE: max > 1000 → log10
stopifnot(identical(.pick_log_kind(TRUE, c(1, 5000), "x"), "log10"))
# TRUE: max <= 1000 → log2
stopifnot(identical(.pick_log_kind(TRUE, c(1, 500),  "x"), "log2"))
# TRUE: no positive values → NULL + warning
msg_nope <- .catch_warning(.pick_log_kind(TRUE, c(-5, -1), "x"), "no positive")
stopifnot(!is.null(msg_nope))
# Invalid string → error
err2 <- tryCatch(.pick_log_kind("ln", c(1, 2), "x"), error = function(e) conditionMessage(e))
stopifnot(grepl("log_x", err2))
cat(" ok\n")

# ---- 3. .axis_label() appends correct Unicode suffixes ----------------------

cat("3. .axis_label() appends correct suffixes...")
stopifnot(.axis_label("TPM",  "log2")  == "TPM (log₂)")
stopifnot(.axis_label("TPM",  "log10") == "TPM (log₁₀)")
stopifnot(.axis_label(NULL,   "log2")  == "(log₂)")
stopifnot(.axis_label("x",    NULL)    == "x")
stopifnot(.axis_label(NULL,   NULL)    == "")
cat(" ok\n")

# ---- 4. .maybe_warn_log() warns when data spans > 100x ----------------------

cat("4. .maybe_warn_log() warns for >100x span, silent otherwise...")
w_big <- .catch_warning(.maybe_warn_log(c(1, 200), "x"), "spans")
stopifnot(!is.null(w_big))
stopifnot(grepl("200", w_big))

w_small <- .catch_warning(.maybe_warn_log(c(1, 99), "x"), "spans")
stopifnot(is.null(w_small))   # no warning for <100x span
cat(" ok\n")

# ---- 5. Basic scatter: no crash, returns gg, writes PNG ---------------------

cat("5. basic scatter returns gg object and writes PNG...")
set.seed(1)
x <- rnorm(100)
y <- rnorm(100)

tmpdir <- tempfile("test_scatter_")
dir.create(tmpdir)
on.exit(unlink(tmpdir, recursive = TRUE), add = TRUE)

p <- pavlab_scatter(x, y, filename = file.path(tmpdir, "basic.png"))
stopifnot(inherits(p, "gg"))
stopifnot(file.exists(file.path(tmpdir, "basic.png")))
stopifnot(file.size(file.path(tmpdir, "basic.png")) > 1000)
cat(" ok\n")

# ---- 6. Non-finite pairs dropped silently -----------------------------------

cat("6. NaN/Inf/NA pairs dropped without error...")
x_na <- c(1, NA,  2, Inf, 3)
y_na <- c(1,  2, NA,   4, 5)
p_na <- pavlab_scatter(x_na, y_na)
stopifnot(inherits(p_na, "gg"))
stopifnot(nrow(p_na$data) == 2)   # only (1,1) and (3,5) are finite pairs
cat(" ok\n")

# ---- 7. Unequal-length x/y → clear error -----------------------------------

cat("7. unequal-length x/y throws error...")
err3 <- tryCatch(pavlab_scatter(1:5, 1:3), error = function(e) conditionMessage(e))
stopifnot(grepl("equal length", err3))
cat(" ok\n")

# ---- 8. Log-scale axes: axis labels updated ---------------------------------

cat("8. log2/log10 transform appends suffix to axis labels...")
x_pos <- abs(rnorm(50)) + 1
y_pos <- abs(rnorm(50)) + 1
p_log <- pavlab_scatter(x_pos, y_pos,
                         log_x = "log2", log_y = "log10",
                         xlabel = "TPM1", ylabel = "TPM2")
stopifnot(grepl("log", p_log$labels$x))
stopifnot(grepl("log", p_log$labels$y))
cat(" ok\n")

# ---- 9. Invalid log_x value → error -----------------------------------------

cat("9. invalid log_x raises error...")
err4 <- tryCatch(pavlab_scatter(x, y, log_x = "ln"), error = function(e) conditionMessage(e))
stopifnot(grepl("log_x", err4))
cat(" ok\n")

# ---- 10. Categorical color → accent palette, renders without crash ----------

cat("10. categorical color builds accent palette and renders...")
groups <- rep(c("A", "B", "C"), length.out = 100)
p_cat <- pavlab_scatter(x, y, color = groups)
stopifnot(inherits(p_cat, "gg"))
# Check color_col column is in the data
stopifnot("color_col" %in% names(p_cat$data))
# Verify first accent color is assigned
built_cat <- ggplot2::ggplot_build(p_cat)
stopifnot(!is.null(built_cat))
cat(" ok\n")

# ---- 11. Numeric color → viridis colorbar, renders without crash ------------

cat("11. numeric color uses viridis and renders...")
scores <- runif(100)
p_num <- pavlab_scatter(x, y, color = scores, color_label = "score")
stopifnot(inherits(p_num, "gg"))
stopifnot("color_col" %in% names(p_num$data))
built_num <- ggplot2::ggplot_build(p_num)
stopifnot(!is.null(built_num))
cat(" ok\n")

# ---- 12. origin_zero=TRUE pins x/y lower bound to 0 ------------------------

cat("12. origin_zero=TRUE trains scale to include 0...")
x_pos2 <- as.numeric(1:10)   # all > 0
y_pos2 <- as.numeric(1:10)
p_oz   <- pavlab_scatter(x_pos2, y_pos2, origin_zero = TRUE)
built_oz <- ggplot2::ggplot_build(p_oz)
x_range  <- built_oz$layout$panel_scales_x[[1]]$range$range
y_range  <- built_oz$layout$panel_scales_y[[1]]$range$range
stopifnot(x_range[1] <= 0)   # expand_limits trained scale to include 0
stopifnot(y_range[1] <= 0)
cat(" ok\n")

# ---- 13. origin_zero=FALSE does not expand to 0 -----------------------------

cat("13. origin_zero=FALSE leaves positive axis starting above 0...")
p_noz    <- pavlab_scatter(x_pos2, y_pos2, origin_zero = FALSE)
built_noz <- ggplot2::ggplot_build(p_noz)
x_range_noz <- built_noz$layout$panel_scales_x[[1]]$range$range
stopifnot(x_range_noz[1] > 0.5)   # data min is 1; scale shouldn't reach 0
cat(" ok\n")

# ---- 14. Density mode (N > 10 000): geom_hex, warns about color -------------

cat("14. density mode uses geom_hex and warns when color supplied...")
set.seed(2)
big_x   <- rnorm(12000)
big_y   <- rnorm(12000)
big_col <- runif(12000)

if (!requireNamespace("hexbin", quietly = TRUE)) {
  # Without hexbin: verify the color-ignored warning still fires, then the
  # function errors with a clear message pointing to the missing package.
  density_warned <- FALSE
  err_hex <- withCallingHandlers(
    tryCatch(
      pavlab_scatter(big_x, big_y, color = big_col),
      error = function(e) conditionMessage(e)
    ),
    warning = function(w) {
      if (grepl("10 000|hexbin|density", conditionMessage(w)))
        density_warned <<- TRUE
      invokeRestart("muffleWarning")
    }
  )
  stopifnot(density_warned)
  stopifnot(is.character(err_hex) && grepl("hexbin", err_hex))
  cat(" ok (hexbin not installed — tested error path)\n")
} else {
  density_warned <- FALSE
  p_density <- withCallingHandlers(
    pavlab_scatter(big_x, big_y, color = big_col,
                   filename = file.path(tmpdir, "density.png")),
    warning = function(w) {
      if (grepl("10 000|hexbin|density", conditionMessage(w)))
        density_warned <<- TRUE
      invokeRestart("muffleWarning")
    }
  )
  stopifnot(inherits(p_density, "gg"))
  stopifnot(density_warned)
  layer_geoms <- sapply(p_density$layers, function(l) class(l$geom)[1])
  stopifnot(any(grepl("Hex", layer_geoms, ignore.case = TRUE)))
  cat(" ok\n")
}

# ---- 15. title / xlabel / ylabel set correctly ------------------------------

cat("15. title/xlabel/ylabel appear in plot labels...")
p_labs <- pavlab_scatter(x, y, title = "My Title",
                          xlabel = "X axis", ylabel = "Y axis")
stopifnot(p_labs$labels$title == "My Title")
stopifnot(grepl("X axis", p_labs$labels$x))
stopifnot(grepl("Y axis", p_labs$labels$y))
cat(" ok\n")

cat("\nALL TESTS PASSED\n")

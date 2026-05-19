#!/usr/bin/env Rscript
# Tests for pavlab_boxplot (R/ggplot2 backend).
# Run from skills/plotting/:
#   Rscript tests/test_boxplot.R

if (!requireNamespace("ggplot2", quietly = TRUE))
  stop("ggplot2 required: install.packages('ggplot2')")

source("R/palettes.R")
source("R/pavlab_scatter.R")     # supplies .pick_log_kind, .color_mode, etc.
source("R/pavlab_boxplot.R")

cat("test_boxplot.R\n")
cat("==============\n")

.catch_error <- function(expr, pattern = ".*") {
  tryCatch({ force(expr); NULL },
    error = function(e) if (grepl(pattern, conditionMessage(e))) conditionMessage(e) else NULL)
}

set.seed(42)
groups <- rep(c("WT", "KO", "DKO"), each = 20)
values <- c(rnorm(20, 2.0, 0.5), rnorm(20, 2.6, 0.7), rnorm(20, 3.2, 0.4))

tmpdir <- tempfile("test_boxplot_")
dir.create(tmpdir)
on.exit(unlink(tmpdir, recursive = TRUE), add = TRUE)

# ---- 1. Basic rendering ----------------------------------------------------

cat("1. default call returns gg object and writes PNG...")
# strip-points path so the test doesn't need ggbeeswarm
p <- pavlab_boxplot(groups, values, points_kind = "strip",
                    filename = file.path(tmpdir, "default.png"))
stopifnot(inherits(p, "gg"))
stopifnot(file.exists(file.path(tmpdir, "default.png")))
cat(" ok\n")

# ---- 2. Default layers: points + box, no error bar -------------------------

cat("2. default has points + box, and NO error-bar layer...")
geoms     <- vapply(p$layers, function(l) class(l$geom)[1], character(1))
positions <- vapply(p$layers, function(l) class(l$position)[1], character(1))
stopifnot("GeomBeeswarm" %in% geoms || "PositionJitter" %in% positions)
stopifnot("GeomBoxplot" %in% geoms)
stopifnot(!"GeomErrorbar" %in% geoms)
cat(" ok\n")

# ---- 3. show_points=FALSE → compact box-only chart -------------------------

cat("3. show_points=FALSE removes the points layer; box still present...")
p_nopt <- pavlab_boxplot(groups, values, show_points = FALSE)
geoms_nopt <- vapply(p_nopt$layers, function(l) class(l$geom)[1], character(1))
positions_nopt <- vapply(p_nopt$layers, function(l) class(l$position)[1], character(1))
stopifnot(!"GeomBeeswarm" %in% geoms_nopt)
stopifnot(!"PositionJitter" %in% positions_nopt)
stopifnot("GeomBoxplot" %in% geoms_nopt)
stopifnot(!"GeomErrorbar" %in% geoms_nopt)
cat(" ok\n")

# ---- 4. error= is no longer a valid kwarg ---------------------------------

cat("4. passing error= raises (no longer a parameter)...")
err <- .catch_error(
  pavlab_boxplot(groups, values, error = "sd"),
  "unused argument"
)
stopifnot(!is.null(err))
cat(" ok\n")

# ---- 5. order= controls x-axis order --------------------------------------

cat("5. order= reorders factor levels on the x axis...")
p_ord <- pavlab_boxplot(groups, values, points_kind = "strip",
                        order = c("DKO", "WT", "KO"))
stopifnot(identical(levels(p_ord$data$x_grp), c("DKO", "WT", "KO")))
cat(" ok\n")

# ---- 6. Bad points_kind rejected ------------------------------------------

cat("6. invalid points_kind raises clear error...")
err2 <- .catch_error(
  pavlab_boxplot(groups, values, points_kind = "violin"),
  "should be one of"
)
stopifnot(!is.null(err2))
cat(" ok\n")

# ---- 7. Log scale propagates ---------------------------------------------

cat("7. log_y applies and labels the y axis with log suffix...")
pos_vals <- abs(values) + 0.1
p_log <- pavlab_boxplot(groups, pos_vals, points_kind = "strip",
                        log_y = "log2", ylabel = "Counts")
stopifnot(grepl("log", p_log$labels$y, ignore.case = TRUE))
cat(" ok\n")

# ---- 8. Non-finite y dropped ---------------------------------------------

cat("8. NaN/Inf in y are dropped silently...")
y_with_na <- values
y_with_na[c(3, 10, 25)] <- NA
p_na <- pavlab_boxplot(groups, y_with_na, points_kind = "strip")
stopifnot(nrow(p_na$data) == sum(is.finite(y_with_na)))
cat(" ok\n")

# ---- 9. ggbeeswarm-dependent swarm path -----------------------------------

if (requireNamespace("ggbeeswarm", quietly = TRUE)) {
  cat("9. points_kind='swarm' renders when ggbeeswarm is available...")
  p_sw <- pavlab_boxplot(groups, values, points_kind = "swarm")
  geoms_sw <- vapply(p_sw$layers, function(l) class(l$geom)[1], character(1))
  stopifnot("GeomBeeswarm" %in% geoms_sw)
  cat(" ok\n")
} else {
  cat("9. points_kind='swarm' raises clear error when ggbeeswarm missing...")
  err3 <- .catch_error(
    pavlab_boxplot(groups, values, points_kind = "swarm"),
    "ggbeeswarm"
  )
  stopifnot(!is.null(err3))
  cat(" ok\n")
}

cat("\nALL TESTS PASSED\n")

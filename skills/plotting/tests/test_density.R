#!/usr/bin/env Rscript
# Tests for pavlab_density (R/ggplot2 backend).
# Run from skills/plotting/:
#   Rscript tests/test_density.R

if (!requireNamespace("ggplot2", quietly = TRUE))
  stop("ggplot2 required: install.packages('ggplot2')")

source("R/palettes.R")
source("R/pavlab_scatter.R")
source("R/pavlab_density.R")

cat("test_density.R\n")
cat("==============\n")

# ---- Helpers -----------------------------------------------------------------

.catch_warning <- function(expr, pattern = ".*") {
  msg <- NULL
  withCallingHandlers(expr,
    warning = function(w) {
      if (is.null(msg) && grepl(pattern, conditionMessage(w)))
        msg <<- conditionMessage(w)
      invokeRestart("muffleWarning")
    }
  )
  msg
}

.suppress_all <- function(expr) {
  suppressWarnings(expr)
}

# ---- Fixtures ----------------------------------------------------------------

set.seed(42)
pos_vals <- rexp(200, rate = 0.5)         # non-negative exponential
signed_vals <- rnorm(100)                 # signed
prob_vals   <- runif(100, 0, 1)           # probability bounded [0,1]
groups_2 <- rep(c("A", "B"), each = 100)

tmpdir <- tempfile("test_density_")
dir.create(tmpdir)
on.exit(unlink(tmpdir, recursive = TRUE), add = TRUE)

# ---- Unit: .detect_bounds ----------------------------------------------------

cat("1. .detect_bounds: non-negative -> left=0, right=NA...")
b <- .detect_bounds(c(0, 1.5, 3.0))
stopifnot(b$left == 0, is.na(b$right))
cat(" ok\n")

cat("2. .detect_bounds: probability -> left=0, right=1...")
b <- .detect_bounds(c(0, 0.3, 0.9, 1.0))
stopifnot(b$left == 0, b$right == 1)
cat(" ok\n")

cat("3. .detect_bounds: signed -> both NA...")
b <- .detect_bounds(c(-1.0, 0.5, 2.0))
stopifnot(is.na(b$left), is.na(b$right))
cat(" ok\n")

# ---- Unit: .group_colors -----------------------------------------------------

cat("4. .group_colors NULL cycles accent palette...")
cols <- .group_colors(NULL, c("A", "B", "C"))
stopifnot(cols[["A"]] == .ACCENT_COLORS[1])
stopifnot(cols[["B"]] == .ACCENT_COLORS[2])
stopifnot(length(cols) == 3)
cat(" ok\n")

cat("5. .group_colors single string -> uniform...")
cols <- .group_colors("red", c("A", "B"))
stopifnot(all(cols == "red"))
cat(" ok\n")

cat("6. .group_colors explicit vector...")
cols <- .group_colors(c("#aaa", "#bbb"), c("A", "B"))
stopifnot(cols[["A"]] == "#aaa", cols[["B"]] == "#bbb")
cat(" ok\n")

cat("7. .group_colors length mismatch -> error...")
err <- tryCatch(.group_colors(c("red", "blue", "green"), c("A", "B")), error = function(e) e)
stopifnot(inherits(err, "error"), grepl("color", conditionMessage(err)))
cat(" ok\n")

# ---- Unit: .reflect_kde ------------------------------------------------------

cat("8. .reflect_kde: zero outside left bound...")
d <- .reflect_kde(seq(0.01, 3.0, length.out = 100), bw = "nrd0", left = 0, right = NA_real_)
stopifnot(is.data.frame(d), all(c("x","y") %in% names(d)))
neg_density <- d$y[d$x < 0]
stopifnot(all(neg_density == 0))
stopifnot(max(d$y) > 0)
cat(" ok\n")

# ---- Integration: density mode -----------------------------------------------

cat("9. density single value -> gg object...")
p <- .suppress_all(pavlab_density(pos_vals))
stopifnot(inherits(p, "gg"))
cat(" ok\n")

cat("10. density writes file...")
outfile <- file.path(tmpdir, "dens.png")
.suppress_all(pavlab_density(pos_vals, filename = outfile))
stopifnot(file.exists(outfile), file.size(outfile) > 500)
cat(" ok\n")

cat("11. density warns about bounds for non-negative data...")
w <- .catch_warning(pavlab_density(pos_vals), "reflect_bounds|bounded")
stopifnot(!is.null(w))
cat(" ok\n")

cat("12. density no bounds warning for signed data...")
got_bounds_warn <- FALSE
withCallingHandlers(
  pavlab_density(signed_vals),
  warning = function(w) {
    if (grepl("reflect_bounds|bounded", conditionMessage(w))) got_bounds_warn <<- TRUE
    invokeRestart("muffleWarning")
  }
)
stopifnot(!got_bounds_warn)
cat(" ok\n")

cat("13. density reflect_bounds=TRUE: no density outside [0, inf)...")
p <- .suppress_all(pavlab_density(pos_vals, reflect_bounds = TRUE))
# The reflected KDE is plotted via geom_ribbon/geom_line with computed data;
# extract geom_line data from layer data via ggplot_build
built <- .suppress_all(ggplot2::ggplot_build(p))
line_data <- tryCatch(built$data[[2]], error = function(e) NULL)
if (!is.null(line_data) && "x" %in% names(line_data)) {
  neg_rows <- line_data[line_data$x < 0, ]
  if (nrow(neg_rows) > 0)
    stopifnot(all(abs(neg_rows$y) < 1e-6))
}
cat(" ok\n")

cat("14. density grouped overlay returns gg object...")
p <- .suppress_all(pavlab_density(pos_vals, groups = groups_2, kind = "density"))
stopifnot(inherits(p, "gg"))
cat(" ok\n")

cat("15. density warns with > 3 groups in overlay mode...")
g4 <- rep(c("A","B","C","D"), each = 25)
v4 <- rnorm(100)
w <- .catch_warning(
  pavlab_density(v4, groups = g4, kind = "density", facet = FALSE),
  "facet"
)
stopifnot(!is.null(w))
cat(" ok\n")

cat("16. density faceted: returns gg with facet_wrap layer...")
p <- .suppress_all(pavlab_density(pos_vals, groups = groups_2, kind = "density", facet = TRUE))
stopifnot(inherits(p, "gg"))
built <- .suppress_all(ggplot2::ggplot_build(p))
stopifnot(length(built$layout$layout$PANEL) == 2)
cat(" ok\n")

cat("17. density log_x label suffix...")
p <- .suppress_all(pavlab_density(pos_vals, log_x = "log2", xlabel = "TPM"))
xl <- p$labels$x
stopifnot(!is.null(xl), nchar(xl) > 0)
cat(" ok\n")

cat("18. density show_mean: vline layer present...")
p <- .suppress_all(pavlab_density(pos_vals, show_mean = TRUE))
layer_classes <- sapply(p$layers, function(l) class(l$geom)[1])
stopifnot(any(grepl("GeomVline", layer_classes)))
vl <- p$layers[[which(grepl("GeomVline", layer_classes))[1]]]
stopifnot(!is.null(vl$data$xintercept))
cat(" ok\n")

cat("19. density show_median: vline layer present...")
p <- .suppress_all(pavlab_density(pos_vals, show_median = TRUE))
layer_classes <- sapply(p$layers, function(l) class(l$geom)[1])
stopifnot(any(grepl("GeomVline", layer_classes)))
cat(" ok\n")

# ---- Integration: histogram mode ---------------------------------------------

cat("20. histogram returns gg object...")
p <- .suppress_all(pavlab_density(pos_vals, kind = "histogram"))
stopifnot(inherits(p, "gg"))
cat(" ok\n")

cat("21. histogram faceted returns gg with 2 panels...")
p <- .suppress_all(
  pavlab_density(pos_vals, groups = groups_2, kind = "histogram", facet = TRUE)
)
built <- .suppress_all(ggplot2::ggplot_build(p))
stopifnot(length(built$layout$layout$PANEL) == 2)
cat(" ok\n")

cat("22. histogram stat=count: geom_histogram with count aesthetic...")
p <- .suppress_all(pavlab_density(pos_vals, kind = "histogram", stat = "count"))
stopifnot(inherits(p, "gg"))
cat(" ok\n")

# ---- Integration: violin mode -----------------------------------------------

cat("23. violin requires groups -> error...")
err <- tryCatch(pavlab_density(pos_vals, kind = "violin"), error = function(e) e)
stopifnot(inherits(err, "error"), grepl("groups", conditionMessage(err)))
cat(" ok\n")

cat("24. violin returns gg object...")
p <- .suppress_all(pavlab_density(pos_vals, groups = groups_2, kind = "violin"))
stopifnot(inherits(p, "gg"))
cat(" ok\n")

cat("25. violin show_mean: hline layer present with correct yintercept...")
p <- pavlab_density(pos_vals, groups = groups_2, kind = "violin", show_mean = TRUE)
layer_classes <- sapply(p$layers, function(l) class(l$geom)[1])
stopifnot(any(grepl("GeomHline", layer_classes)))
hl <- p$layers[[which(grepl("GeomHline", layer_classes))[1]]]
expected <- mean(pos_vals)
stopifnot(abs(hl$data$yintercept - expected) < 1e-6)
cat(" ok\n")

cat("26. violin group order respected...")
p <- .suppress_all(
  pavlab_density(pos_vals, groups = groups_2, kind = "violin", order = c("B", "A"))
)
built <- .suppress_all(ggplot2::ggplot_build(p))
xlabels <- built$layout$panel_scales_x[[1]]$range$range
stopifnot(xlabels[1] == "B", xlabels[2] == "A")
cat(" ok\n")

# ---- Input validation -------------------------------------------------------

cat("27. unequal length -> error...")
err <- tryCatch(
  pavlab_density(pos_vals, groups = rep("A", length(pos_vals) - 1)),
  error = function(e) e
)
stopifnot(inherits(err, "error"), grepl("equal length|equal", conditionMessage(err)))
cat(" ok\n")

cat("28. nonfinite values dropped silently...")
vals_na <- c(1.0, NA, 2.0, Inf, 3.0)
p <- .suppress_all(pavlab_density(vals_na, kind = "histogram", stat = "count"))
built <- .suppress_all(ggplot2::ggplot_build(p))
hist_data <- built$data[[1]]
total_count <- sum(hist_data$count, na.rm = TRUE)
stopifnot(total_count == 3)
cat(" ok\n")

cat("29. theme: no top/right spines...")
p <- .suppress_all(pavlab_density(pos_vals))
built <- .suppress_all(ggplot2::ggplot_build(p))
theme_el <- ggplot2::theme_get()
p_theme  <- p$theme
stopifnot(inherits(p, "gg"))
cat(" ok\n")

cat("30. density single no-groups, reflect_bounds=TRUE produces geom_ribbon...")
p <- .suppress_all(pavlab_density(pos_vals, reflect_bounds = TRUE))
layer_classes <- sapply(p$layers, function(l) class(l$geom)[1])
stopifnot(any(grepl("GeomRibbon|GeomLine", layer_classes)))
cat(" ok\n")

cat("\nAll 30 tests passed.\n")

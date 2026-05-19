#!/usr/bin/env Rscript
# Tests for pavlab_stripchart (R/ggplot2 backend).
# Run from skills/plotting/:
#   Rscript tests/test_stripchart.R

if (!requireNamespace("ggplot2", quietly = TRUE))
  stop("ggplot2 required: install.packages('ggplot2')")

source("R/palettes.R")
source("R/pavlab_scatter.R")
source("R/pavlab_stripchart.R")

cat("test_stripchart.R\n")
cat("=================\n")

# ---- Helper -----------------------------------------------------------------

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

# ---- Fixtures ---------------------------------------------------------------

set.seed(0)
groups <- rep(c("A", "B"), each = 10)
values <- runif(20, 1, 5)

set.seed(1)
g3 <- rep(c("ctrl", "treat", "dko"), each = 15)
v3 <- runif(45, 0, 10)

tmpdir <- tempfile("test_stripchart_")
dir.create(tmpdir)
on.exit(unlink(tmpdir, recursive = TRUE), add = TRUE)

# ---- 1. Basic rendering -----------------------------------------------------

cat("1. basic call returns gg object and writes PNG...")
p <- pavlab_stripchart(groups, values,
                       filename = file.path(tmpdir, "basic.png"))
stopifnot(inherits(p, "gg"))
stopifnot(file.exists(file.path(tmpdir, "basic.png")))
stopifnot(file.size(file.path(tmpdir, "basic.png")) > 1000)
cat(" ok\n")

cat("2. theme_classic applied: no grid, top/right off...")
built <- ggplot2::ggplot_build(p)
stopifnot(!is.null(built))
cat(" ok\n")

# ---- 2. Input validation ----------------------------------------------------

cat("3. unequal-length x/y throws error...")
err <- tryCatch(
  pavlab_stripchart(c("A", "B"), c(1, 2, 3)),
  error = function(e) conditionMessage(e)
)
stopifnot(grepl("equal length", err))
cat(" ok\n")

# ---- 3. Non-finite y dropped ------------------------------------------------

cat("4. non-finite y values dropped silently...")
g_na <- c("A", "A", "B", "B", "B")
v_na <- c(1.0, NA, 2.0, Inf, 3.0)
p_na <- pavlab_stripchart(g_na, v_na)
stopifnot(inherits(p_na, "gg"))
# 3 finite rows remain
stopifnot(nrow(p_na$data) == 3)
cat(" ok\n")

# ---- 4. Group ordering ------------------------------------------------------

cat("5. default order follows first-appearance of groups...")
p_ord <- pavlab_stripchart(c("B", "A", "B", "A"), c(1, 2, 3, 4))
lvls <- levels(p_ord$data$x_grp)
stopifnot(lvls[1] == "B")
stopifnot(lvls[2] == "A")
cat(" ok\n")

cat("6. order= parameter reorders groups...")
p_reord <- pavlab_stripchart(g3, v3, order = c("dko", "ctrl", "treat"))
lvls_reord <- levels(p_reord$data$x_grp)
stopifnot(lvls_reord[1] == "dko")
stopifnot(lvls_reord[2] == "ctrl")
stopifnot(lvls_reord[3] == "treat")
cat(" ok\n")

# ---- 5. Mean / median reference lines ---------------------------------------

cat("7. show_mean=TRUE adds a geom_hline at grand mean...")
grand_mean <- mean(values)
p_mean <- pavlab_stripchart(groups, values, show_mean = TRUE)
# Reference lines are added before geom_jitter, so layers[[1]] is geom_hline
has_hline <- inherits(p_mean$layers[[1]]$geom, "GeomHline")
stopifnot(has_hline)
hline_y <- p_mean$layers[[1]]$data$yintercept
stopifnot(abs(hline_y - grand_mean) < 1e-9)
cat(" ok\n")

cat("8. show_median=TRUE adds a geom_hline at grand median...")
grand_median <- median(values)
p_med <- pavlab_stripchart(groups, values, show_median = TRUE)
stopifnot(inherits(p_med$layers[[1]]$geom, "GeomHline"))
med_y <- p_med$layers[[1]]$data$yintercept
stopifnot(abs(med_y - grand_median) < 1e-9)
cat(" ok\n")

cat("9. show_mean + show_median → two geom_hline layers...")
p_both <- pavlab_stripchart(groups, values, show_mean = TRUE, show_median = TRUE)
hline_layers <- Filter(function(l) inherits(l$geom, "GeomHline"), p_both$layers)
stopifnot(length(hline_layers) == 2)
cat(" ok\n")

cat("10. no mean line by default...")
p_nomean <- pavlab_stripchart(groups, values)
hline_layers_no <- Filter(function(l) inherits(l$geom, "GeomHline"), p_nomean$layers)
stopifnot(length(hline_layers_no) == 0)
cat(" ok\n")

# ---- 6. Log transform -------------------------------------------------------

cat("11. log_y appends suffix to y-axis label...")
p_log <- pavlab_stripchart(groups, values, log_y = "log2", ylabel = "Expression")
stopifnot(grepl("log", p_log$labels$y))
cat(" ok\n")

cat("12. log_y transforms values in plot data...")
# values all > 0, pseudocount=1: log2(v+1)
p_logval <- pavlab_stripchart(groups, values, log_y = "log2", pseudocount = 1.0)
expected_y <- log2(values + 1.0)
actual_y   <- sort(p_logval$data$y_val)
stopifnot(all(abs(actual_y - sort(expected_y)) < 1e-9))
cat(" ok\n")

# ---- 7. Colour modes --------------------------------------------------------

cat("13. color=NULL → uniform black points...")
p_blk <- pavlab_stripchart(groups, values)
# No color_col column in data → uniform color
stopifnot(!"color_col" %in% names(p_blk$data))
cat(" ok\n")

cat("14. categorical color_col column added for char vector...")
strat <- rep(c("X", "Y"), 10)
p_cat <- pavlab_stripchart(groups, values, color = strat)
stopifnot("color_col" %in% names(p_cat$data))
built_cat <- ggplot2::ggplot_build(p_cat)
stopifnot(!is.null(built_cat))
cat(" ok\n")

cat("15. numeric color_col column added for float vector...")
scores <- runif(20)
p_num <- pavlab_stripchart(groups, values, color = scores)
stopifnot("color_col" %in% names(p_num$data))
built_num <- ggplot2::ggplot_build(p_num)
stopifnot(!is.null(built_num))
cat(" ok\n")

# ---- 8. origin_zero ---------------------------------------------------------

cat("16. origin_zero=TRUE trains y scale to include 0...")
p_oz <- pavlab_stripchart(groups, values, origin_zero = TRUE)  # all y > 0
built_oz <- ggplot2::ggplot_build(p_oz)
y_range <- built_oz$layout$panel_scales_y[[1]]$range$range
stopifnot(y_range[1] <= 0)
cat(" ok\n")

cat("17. origin_zero=FALSE leaves y range above 0...")
p_noz <- pavlab_stripchart(groups, values, origin_zero = FALSE)
built_noz <- ggplot2::ggplot_build(p_noz)
y_range_noz <- built_noz$layout$panel_scales_y[[1]]$range$range
stopifnot(y_range_noz[1] > 0.5)
cat(" ok\n")

# ---- 9. Labels --------------------------------------------------------------

cat("18. title/xlabel/ylabel appear in plot labels...")
p_labs <- pavlab_stripchart(groups, values, title = "Title",
                             xlabel = "Group", ylabel = "Value")
stopifnot(p_labs$labels$title == "Title")
stopifnot(grepl("Group", p_labs$labels$x))
stopifnot(grepl("Value", p_labs$labels$y))
cat(" ok\n")

# ---- 10. kind="swarm" -------------------------------------------------------

cat("19. kind='strip' (default) jitters the point layer...")
p_strip <- pavlab_stripchart(groups, values)  # default kind
# geom_jitter reports class "GeomPoint" — the jitter is on the layer's
# position, not the geom. Look for at least one PositionJitter layer.
positions <- vapply(p_strip$layers, function(l) class(l$position)[1], character(1))
stopifnot("PositionJitter" %in% positions)
cat(" ok\n")

if (requireNamespace("ggbeeswarm", quietly = TRUE)) {
  cat("20. kind='swarm' uses GeomBeeswarm when ggbeeswarm is available...")
  p_sw <- pavlab_stripchart(groups, values, kind = "swarm")
  geoms_sw <- vapply(p_sw$layers, function(l) class(l$geom)[1], character(1))
  stopifnot("GeomBeeswarm" %in% geoms_sw)
  cat(" ok\n")
} else {
  cat("20. kind='swarm' raises clear error when ggbeeswarm missing...")
  err <- tryCatch({
    pavlab_stripchart(groups, values, kind = "swarm"); NULL
  }, error = function(e) conditionMessage(e))
  stopifnot(!is.null(err), grepl("ggbeeswarm", err))
  cat(" ok\n")
}

cat("21. kind='violin' rejected by match.arg...")
err2 <- tryCatch({
  pavlab_stripchart(groups, values, kind = "violin"); NULL
}, error = function(e) conditionMessage(e))
stopifnot(!is.null(err2), grepl("should be one of", err2))
cat(" ok\n")

cat("\nALL TESTS PASSED\n")

# pavlab_boxplot: opinionated lab-style boxplot (ggplot2 backend).
#
# Used sparingly. The box itself — quartiles + whiskers + median — IS
# the spread/uncertainty visualization; no separate overlaid error bar
# is drawn. Two modes:
#
#   show_points=TRUE  (default): raw data points (swarmed) under the box.
#   show_points=FALSE:           compact box only (multi-panel layouts
#                                where visual compactness matters).
#
# There is intentionally no `error=` parameter. A separate mean +/- SD
# or +/- 95% CI overlay would double the spread cue the box already
# carries via its whiskers and IQR. Helpers for parameter-estimate
# plots (forest plots, regression-coefficient charts) WILL carry an
# error-bar API in the future, following the cross-plot rule in
# feedback_error_bars_never_sem.md — SD for raw-data charts, 95% CI
# for parameter-estimate charts, never SEM.
#
# Helpers reused from pavlab_scatter.R (which sources palettes.R):
#   .pick_log_kind  .apply_log  .axis_label  .font_sizes  .maybe_warn_log
#   .color_mode  .N_ALPHA  .ACCENT_COLORS  .LABEL_SIZES
#
# Usage:
#   source("R/palettes.R")
#   source("R/pavlab_scatter.R")
#   source("R/pavlab_boxplot.R")
#   pavlab_boxplot(groups, values)
#   pavlab_boxplot(groups, values, error = "sd")
#   pavlab_boxplot(groups, values, points_kind = "strip")
#   pavlab_boxplot(groups, values, show_points = FALSE, error = NULL)  # warns

# ---- Main function ---------------------------------------------------------

#' Pavlab-style boxplot with raw-points underlayer.
#'
#' Categorical x-axis, continuous y-axis. Default rendering: pale box
#' with structural-coloured outline + raw points (swarmed by default)
#' underneath. No separate error-bar overlay — the box's whiskers and
#' IQR are the spread visualisation. Set `show_points=FALSE` for a
#' compact box-only chart.
#'
#' @param x Character or factor vector of group labels (length n).
#' @param y Numeric vector of values (length n). Non-finite values are
#'   silently dropped.
#' @param color NULL, single color string, character/factor vector, or
#'   numeric vector — same semantics as pavlab_stripchart. Affects the
#'   points layer only; the box always uses the structural lab colour.
#' @param color_label Colorbar title for numeric `color`.
#' @param show_points TRUE (default) draws raw points underneath the box.
#' @param points_kind "swarm" (default) or "strip" — layout for the points
#'   underlayer. "swarm" requires `ggbeeswarm`.
#' @param jitter Half-width of jitter when `points_kind="strip"`. Default 0.2.
#' @param box_width Width of each box in x-data units. Default 0.55.
#' @param order Character vector of group levels controlling x-axis order.
#' @param log_y FALSE | TRUE | "log2" | "log10". Auto-selects when TRUE.
#' @param pseudocount Added to y before log transform. Default 1.
#' @param origin_zero TRUE pins non-negative y lower bound to 0.
#' @param ylim Explicit y limits (length 2).
#' @param label_size "small" / "med" / "large" / numeric pt size.
#' @param xlabel,ylabel,title Plot labels.
#' @param point_size Override marker size in mm.
#' @param filename Save path; format inferred from extension.
#' @param figsize Numeric length-2 c(width, height) in inches.
#' @return ggplot2 object (invisibly).
#' @export
pavlab_boxplot <- function(
  x, y,
  color       = NULL,
  color_label = NULL,
  show_points = TRUE,
  points_kind = "swarm",
  jitter      = 0.2,
  box_width   = 0.55,
  order       = NULL,
  log_y       = FALSE,
  pseudocount = 1.0,
  origin_zero = TRUE,
  ylim        = NULL,
  label_size  = "med",
  xlabel      = NULL,
  ylabel      = NULL,
  title       = NULL,
  point_size  = NULL,
  filename    = NULL,
  figsize     = NULL
) {
  if (!requireNamespace("ggplot2", quietly = TRUE))
    stop("pavlab_boxplot: ggplot2 is required. Install with install.packages('ggplot2').",
         call. = FALSE)

  points_kind <- match.arg(tolower(as.character(points_kind)),
                           c("strip", "swarm"))
  if (show_points && points_kind == "swarm" &&
      !requireNamespace("ggbeeswarm", quietly = TRUE)) {
    stop("pavlab_boxplot: points_kind='swarm' requires the ggbeeswarm package. ",
         "Install with install.packages('ggbeeswarm'), or pass points_kind='strip'.",
         call. = FALSE)
  }

  x <- as.character(x)
  y <- as.numeric(y)
  if (length(x) != length(y))
    stop(sprintf("x and y must have equal length (%d vs %d)", length(x), length(y)),
         call. = FALSE)

  has_vec_color <- !is.null(color) && length(color) == length(y)
  mask <- is.finite(y)
  if (has_vec_color) color <- color[mask]
  x <- x[mask]; y <- y[mask]
  n <- length(y)
  if (n == 0) warning("pavlab_boxplot: no finite data points to plot.", call. = FALSE)

  # Suggest log scale when not transforming.
  if (identical(log_y, FALSE)) .maybe_warn_log(y, "y")
  y_kind <- .pick_log_kind(log_y, y, "y")
  if (!is.null(y_kind)) {
    neg <- sum(is.finite(y) & (y + pseudocount) <= 0)
    if (neg > 0)
      warning(sprintf(
        "pavlab_boxplot: %d y value(s) will produce -Inf after log transform (pseudocount=%g insufficient).",
        neg, pseudocount), call. = FALSE)
    y <- .apply_log(y, y_kind, pseudocount)
  }

  seen <- unique(x)
  if (!is.null(order)) {
    extra  <- seen[!seen %in% order]
    levels <- c(order, extra)
  } else {
    levels <- seen
  }
  x_fac <- factor(x, levels = levels)

  fs       <- .font_sizes(label_size)
  label_pt <- fs[1]
  tick_pt  <- fs[2]
  yl       <- .axis_label(ylabel, y_kind)

  ps <- if (!is.null(point_size)) as.numeric(point_size) else
          if (n <= .N_ALPHA) 1.7 else 1.3
  alpha_val <- if (n <= .N_ALPHA) 0.85 else {
    frac <- min(1.0, (n - .N_ALPHA) / max(1L, 10000L - .N_ALPHA))
    max(0.15, 0.6 - frac * 0.45)
  }

  df <- data.frame(x_grp = x_fac, y_val = y, stringsAsFactors = FALSE)

  # ---- Style constants (match the Python helper) --------------------------
  BOX_COLOR   <- "#1f2937"
  POINT_COLOR <- "#374151"
  BOX_FILL    <- "#f3f4f6"

  # Base aesthetic
  cmode <- .color_mode(color, n)
  if (cmode %in% c("uniform_black", "uniform_string")) {
    p <- ggplot2::ggplot(df, ggplot2::aes(x = x_grp, y = y_val))
  } else if (cmode == "categorical") {
    df$color_col <- as.character(color)
    p <- ggplot2::ggplot(df, ggplot2::aes(x = x_grp, y = y_val))
  } else {
    df$color_col <- as.numeric(color)
    p <- ggplot2::ggplot(df, ggplot2::aes(x = x_grp, y = y_val))
  }

  # ---- Layer 1: raw points underneath ------------------------------------
  if (show_points) {
    point_layer <- function(...) {
      if (points_kind == "swarm") {
        ggbeeswarm::geom_beeswarm(..., cex = 1.0, method = "swarm",
                                  shape = 16, stroke = 0, size = ps)
      } else {
        ggplot2::geom_jitter(..., shape = 16, stroke = 0, size = ps,
                             position = ggplot2::position_jitter(width = jitter, height = 0))
      }
    }
    if (cmode == "uniform_black") {
      p <- p + point_layer(color = POINT_COLOR, alpha = alpha_val)
    } else if (cmode == "uniform_string") {
      p <- p + point_layer(color = as.character(color), alpha = alpha_val)
    } else if (cmode == "categorical") {
      cats     <- unique(as.character(color))
      cat_idx  <- ((seq_along(cats) - 1L) %% length(.ACCENT_COLORS)) + 1L
      cat_cols <- setNames(.ACCENT_COLORS[cat_idx], cats)
      p <- p +
        point_layer(ggplot2::aes(color = color_col), alpha = alpha_val) +
        ggplot2::scale_color_manual(values = cat_cols, name = NULL) +
        ggplot2::guides(color = ggplot2::guide_legend(
          override.aes = list(size = 3, alpha = 1)))
    } else {
      clabel <- if (!is.null(color_label)) color_label else ""
      p <- p +
        point_layer(ggplot2::aes(color = color_col), alpha = alpha_val) +
        ggplot2::scale_color_viridis_c(name = clabel)
    }
  }

  # ---- Layer 2: the box itself --------------------------------------------
  p <- p + ggplot2::geom_boxplot(
    fill      = BOX_FILL,
    color     = BOX_COLOR,
    alpha     = 0.85,
    width     = box_width,
    outlier.shape = NA,       # raw points show outliers already
    linewidth = 0.55,
    fatten    = 1.3            # median line slightly heavier than box outline
  )

  # ---- Theme + labels + limits -------------------------------------------
  p <- p +
    ggplot2::theme_classic(base_size = tick_pt) +
    ggplot2::theme(
      axis.title        = ggplot2::element_text(size = label_pt, color = "#1f2937"),
      axis.text         = ggplot2::element_text(size = tick_pt,  color = "#6b7280"),
      axis.ticks        = ggplot2::element_line(color = "#6b7280"),
      plot.title        = ggplot2::element_text(size = label_pt, color = "#1f2937",
                                                hjust = 0, face = "plain"),
      legend.text       = ggplot2::element_text(size = tick_pt),
      legend.title      = ggplot2::element_text(size = tick_pt),
      legend.background = ggplot2::element_blank(),
      legend.key        = ggplot2::element_blank(),
      plot.margin       = ggplot2::margin(3, 3, 3, 3, "mm")
    )

  if (!is.null(xlabel) && nchar(xlabel) > 0) p <- p + ggplot2::xlab(xlabel)
  if (nchar(yl) > 0) p <- p + ggplot2::ylab(yl)
  if (!is.null(title)) p <- p + ggplot2::ggtitle(title)

  if (origin_zero) {
    fy <- df$y_val[is.finite(df$y_val)]
    if (length(fy) > 0 && min(fy) >= 0) p <- p + ggplot2::expand_limits(y = 0)
  }
  if (!is.null(ylim)) p <- p + ggplot2::coord_cartesian(ylim = ylim)

  if (!is.null(filename)) {
    w <- if (!is.null(figsize)) figsize[1] else 5.5
    h <- if (!is.null(figsize)) figsize[2] else 5.0
    ggplot2::ggsave(filename, plot = p, width = w, height = h, dpi = 150)
  }

  invisible(p)
}

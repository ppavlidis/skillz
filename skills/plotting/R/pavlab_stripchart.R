# pavlab_stripchart: opinionated lab-style strip chart (ggplot2 backend).
# Mirrors the design conventions of pavlab_scatter for categorical x / continuous y:
#   - Jittered points, no fill, shape 16, no stroke
#   - N-adaptive alpha and point size
#   - log_y: FALSE/TRUE/"log2"/"log10"; same semantics as pavlab_scatter
#   - color: NULL=black; single string=uniform; char/factor vec=categorical+legend;
#            numeric vec=viridis colorbar
#   - Optional grand-mean and grand-median reference lines (behind points)
#   - origin_zero: pins non-negative y lower bound to 0
#
# Helpers reused from pavlab_scatter.R (which sources palettes.R):
#   .pick_log_kind  .apply_log  .axis_label  .font_sizes  .maybe_warn_log
#   .color_mode  .N_ALPHA  .ACCENT_COLORS  .LABEL_SIZES
#
# Usage:
#   source("R/palettes.R")
#   source("R/pavlab_scatter.R")
#   source("R/pavlab_stripchart.R")
#   pavlab_stripchart(groups, values)
#   pavlab_stripchart(groups, values, log_y="log2", ylabel="Expression", show_mean=TRUE)
#   pavlab_stripchart(groups, values, color=group_vec, order=c("ctrl","treat"))
#   p <- pavlab_stripchart(groups, values, filename="fig2a.svg")
#   p + ggplot2::geom_boxplot(alpha=0)   # extend with ggplot2 layers

# ---- Main function -----------------------------------------------------------

#' Pavlab-style strip chart (ggplot2).
#'
#' Categorical x-axis, continuous y-axis; points jittered horizontally.
#' N-adaptive point size and alpha. Returns a ggplot2 object that can be
#' extended with `+` layers.
#'
#' @param x Character or factor vector of group labels (length n).
#' @param y Numeric vector of values (length n). Non-finite values are silently
#'   dropped; aligned `color` vector is masked to the same rows.
#' @param color NULL (all black), a single color string (uniform), a
#'   character / factor vector of length n (categorical — lab accent palette +
#'   legend), or a numeric vector of length n (viridis colorbar).
#' @param color_label Colorbar title for numeric `color`. Default NULL (empty).
#' @param jitter Horizontal jitter width passed to `position_jitter`. Default 0.2.
#' @param show_mean If TRUE, draw a dashed horizontal reference line at the
#'   grand mean of all (post-transform) y values. Line renders behind points.
#'   Default FALSE.
#' @param show_median If TRUE, draw a dotted horizontal reference line at the
#'   grand median. Default FALSE.
#' @param order Optional character vector of group levels controlling x-axis
#'   order. Unrecognised levels in `x` are silently appended in appearance order.
#' @param log_y FALSE | TRUE | "log2" | "log10". TRUE auto-selects: log10 when
#'   max > 1 000, log2 otherwise. pseudocount added before transform so zeros
#'   survive. Warns when data spans > 100× and no transform is requested.
#' @param pseudocount Added to y before log transform. Default 1.
#' @param origin_zero If TRUE (default) and all transformed y >= 0, expand the
#'   y lower bound to include 0. Explicit ylim takes precedence.
#' @param ylim Numeric length-2 vector for explicit y limits. Takes precedence
#'   over origin_zero.
#' @param label_size "small", "med", "large", or a numeric point size for axis
#'   labels (tick labels scale proportionally). Default "med" (14 pt / 11 pt).
#' @param xlabel,ylabel Axis labels. Log-scale suffix ("(log₂)" etc.) appended
#'   automatically on the y axis when a transform is applied.
#' @param title Plot title. Left-aligned, normal weight.
#' @param point_size Override auto marker size (ggplot2 `size=` in mm).
#'   Default: 2.0 for N <= 500, 1.5 otherwise.
#' @param filename Save path. Format inferred from extension via ggsave.
#' @param figsize Numeric length-2 vector c(width, height) in inches.
#'   Default c(5.5, 5.0).
#' @return ggplot2 object (invisibly).
#' @export
pavlab_stripchart <- function(
  x, y,
  color       = NULL,
  color_label = NULL,
  jitter      = 0.2,
  show_mean   = FALSE,
  show_median = FALSE,
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
    stop("pavlab_stripchart: ggplot2 is required. Install with install.packages('ggplot2').",
         call. = FALSE)

  x <- as.character(x)
  y <- as.numeric(y)
  if (length(x) != length(y))
    stop(sprintf("x and y must have equal length (%d vs %d)", length(x), length(y)),
         call. = FALSE)

  # Drop non-finite y; align color vector to the same mask.
  has_vec_color <- !is.null(color) && length(color) == length(y)
  mask <- is.finite(y)
  if (has_vec_color) color <- color[mask]
  x <- x[mask]
  y <- y[mask]

  n <- length(y)
  if (n == 0)
    warning("pavlab_stripchart: no finite data points to plot.", call. = FALSE)

  # Suggest log scale when not transforming.
  if (identical(log_y, FALSE)) .maybe_warn_log(y, "y")

  # Apply log transform.
  y_kind <- .pick_log_kind(log_y, y, "y")
  if (!is.null(y_kind)) {
    neg <- sum(is.finite(y) & (y + pseudocount) <= 0)
    if (neg > 0)
      warning(sprintf(
        "pavlab_stripchart: %d y value(s) will produce -Inf after log transform (pseudocount=%g insufficient).",
        neg, pseudocount
      ), call. = FALSE)
    y <- .apply_log(y, y_kind, pseudocount)
  }

  # Build factor levels from order, then append any remaining values in
  # appearance order so nothing gets silently dropped.
  seen <- unique(x)
  if (!is.null(order)) {
    extra  <- seen[!seen %in% order]
    levels <- c(order, extra)
  } else {
    levels <- seen
  }
  x_fac <- factor(x, levels = levels)

  # Font sizes.
  fs       <- .font_sizes(label_size)
  label_pt <- fs[1]
  tick_pt  <- fs[2]

  # Y-axis label with optional log suffix.
  yl <- .axis_label(ylabel, y_kind)

  # Point size + alpha.
  ps <- if (!is.null(point_size)) as.numeric(point_size) else
          if (n <= .N_ALPHA) 2.0 else 1.5

  alpha_val <- if (n <= .N_ALPHA) {
    1.0
  } else {
    frac <- min(1.0, (n - .N_ALPHA) / max(1L, 10000L - .N_ALPHA))
    max(0.15, 0.6 - frac * 0.45)
  }

  # Build data frame.
  df <- data.frame(x_grp = x_fac, y_val = y, stringsAsFactors = FALSE)

  # ---- Base ggplot + reference lines (drawn first, behind points) ----------

  cmode <- .color_mode(color, n)

  # Construct the base aesthetic; color column added per mode below.
  if (cmode %in% c("uniform_black", "uniform_string")) {
    p <- ggplot2::ggplot(df, ggplot2::aes(x = x_grp, y = y_val))
  } else if (cmode == "categorical") {
    df$color_col <- as.character(color)
    p <- ggplot2::ggplot(df, ggplot2::aes(x = x_grp, y = y_val, color = color_col))
  } else {
    df$color_col <- as.numeric(color)
    p <- ggplot2::ggplot(df, ggplot2::aes(x = x_grp, y = y_val, color = color_col))
  }

  # Reference lines go before geom_jitter so they render behind the points.
  if (show_mean) {
    grand_mean <- mean(df$y_val, na.rm = TRUE)
    p <- p + ggplot2::geom_hline(
      yintercept = grand_mean,
      color      = "#9ca3af",
      linetype   = "dashed",
      linewidth  = 0.5
    )
  }
  if (show_median) {
    grand_median <- stats::median(df$y_val, na.rm = TRUE)
    p <- p + ggplot2::geom_hline(
      yintercept = grand_median,
      color      = "#9ca3af",
      linetype   = "dotted",
      linewidth  = 0.5
    )
  }

  # ---- Points --------------------------------------------------------------

  jitter_pos <- ggplot2::position_jitter(width = jitter, height = 0)

  if (cmode == "uniform_black") {
    p <- p + ggplot2::geom_jitter(
      color    = "#000000",
      alpha    = alpha_val,
      size     = ps,
      shape    = 16,
      stroke   = 0,
      position = jitter_pos
    )

  } else if (cmode == "uniform_string") {
    p <- p + ggplot2::geom_jitter(
      color    = as.character(color),
      alpha    = alpha_val,
      size     = ps,
      shape    = 16,
      stroke   = 0,
      position = jitter_pos
    )

  } else if (cmode == "categorical") {
    cats     <- unique(as.character(color))
    cat_idx  <- ((seq_along(cats) - 1L) %% length(.ACCENT_COLORS)) + 1L
    cat_cols <- setNames(.ACCENT_COLORS[cat_idx], cats)
    p <- p +
      ggplot2::geom_jitter(
        alpha    = alpha_val,
        size     = ps,
        shape    = 16,
        stroke   = 0,
        position = jitter_pos
      ) +
      ggplot2::scale_color_manual(values = cat_cols, name = NULL) +
      ggplot2::guides(color = ggplot2::guide_legend(
        override.aes = list(size = 3, alpha = 1)
      ))

  } else {
    # numeric → viridis colorbar
    clabel <- if (!is.null(color_label)) color_label else ""
    p <- p +
      ggplot2::geom_jitter(
        alpha    = alpha_val,
        size     = ps,
        shape    = 16,
        stroke   = 0,
        position = jitter_pos
      ) +
      ggplot2::scale_color_viridis_c(name = clabel)
  }

  # ---- Theme ---------------------------------------------------------------

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

  # ---- Labels --------------------------------------------------------------

  if (!is.null(xlabel) && nchar(xlabel) > 0) p <- p + ggplot2::xlab(xlabel)
  if (nchar(yl) > 0) p <- p + ggplot2::ylab(yl)
  if (!is.null(title)) p <- p + ggplot2::ggtitle(title)

  # ---- Y-axis limits -------------------------------------------------------

  if (origin_zero) {
    fy <- df$y_val[is.finite(df$y_val)]
    if (length(fy) > 0 && min(fy) >= 0) p <- p + ggplot2::expand_limits(y = 0)
  }
  if (!is.null(ylim)) {
    p <- p + ggplot2::coord_cartesian(ylim = ylim)
  }

  # ---- Save ----------------------------------------------------------------

  if (!is.null(filename)) {
    w <- if (!is.null(figsize)) figsize[1] else 5.5
    h <- if (!is.null(figsize)) figsize[2] else 5.0
    ggplot2::ggsave(filename, plot = p, width = w, height = h, dpi = 150)
  }

  invisible(p)
}

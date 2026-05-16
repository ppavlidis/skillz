# pavlab_density: opinionated lab-style density / histogram / violin plot (ggplot2 backend).
# Mirrors Python pavlab_density defaults:
#   - kind="density": KDE fill, alpha 0.5; optional boundary reflection
#   - kind="histogram": filled bars, alpha 0.7, white dividers
#   - kind="violin": one violin per group, categorical x / continuous y
#   - log_x: pre-transform values before KDE/histogram; log_y: scale y-axis
#   - reflect_bounds: manual KDE reflection for non-negative / probability data
#   - show_mean/show_median: vline (density/histogram) or hline (violin)
#
# Usage:
#   source("R/palettes.R")
#   source("R/pavlab_scatter.R")
#   source("R/pavlab_density.R")
#   pavlab_density(x)
#   pavlab_density(x, groups=g, kind="violin", show_mean=TRUE)
#   pavlab_density(x, groups=g, kind="histogram", facet=TRUE, bins=50)
#   pavlab_density(x, log_x=TRUE, reflect_bounds=TRUE, xlabel="Expression")
#   pavlab_density(x, groups=g, kind="density", facet=FALSE, stat="count")
#   p <- pavlab_density(x, groups=g, kind="violin", order=c("ctrl","trt"), filename="fig.svg")
#
# Dependencies: ggplot2 (>= 3.4.0).
# Helpers sourced from pavlab_scatter.R (which sources palettes.R):
#   .pick_log_kind  .apply_log  .axis_label  .font_sizes  .maybe_warn_log
#   .N_ALPHA  .ACCENT_COLORS

# ---- Private helpers ---------------------------------------------------------

.group_colors <- function(color, unique_groups) {
  ng <- length(unique_groups)
  if (is.null(color)) {
    idx <- ((seq_len(ng) - 1L) %% length(.ACCENT_COLORS)) + 1L
    return(setNames(.ACCENT_COLORS[idx], unique_groups))
  }
  if (length(color) == 1L) {
    return(setNames(rep(as.character(color), ng), unique_groups))
  }
  if (length(color) == ng) {
    return(setNames(as.character(color), unique_groups))
  }
  stop(
    sprintf(
      "pavlab_density: color must be NULL, a single string, or a vector of length %d (one per group); got length %d.",
      ng, length(color)
    ),
    call. = FALSE
  )
}

.detect_bounds <- function(vals) {
  left  <- if (min(vals, na.rm = TRUE) >= 0) 0 else NA_real_
  right <- if (!is.na(left) && max(vals, na.rm = TRUE) <= 1) 1 else NA_real_
  list(left = left, right = right)
}

.reflect_kde <- function(vals, bw, left, right) {
  reflected <- vals
  if (!is.na(left))  reflected <- c(reflected, 2 * left  - vals)
  if (!is.na(right)) reflected <- c(reflected, 2 * right - vals)
  d <- stats::density(reflected, bw = bw, n = 512)
  x_out <- d$x
  y_out <- d$y * 2
  if (!is.na(left))  y_out[x_out < left]  <- 0
  if (!is.na(right)) y_out[x_out > right] <- 0
  data.frame(x = x_out, y = y_out)
}

# ---- Main function -----------------------------------------------------------

#' Pavlab-style density / histogram / violin plot (ggplot2).
#'
#' Single interface for three distribution visualisations. Returns a ggplot2
#' object that can be extended with `+` layers.
#'
#' @param values Numeric vector of values to plot.
#' @param groups Character or factor vector of group labels (same length as
#'   `values`). Required for `kind="violin"`.
#' @param kind One of `"density"`, `"histogram"`, or `"violin"`.
#' @param facet If TRUE, draw one panel per group (density / histogram only).
#' @param stat `"density"` or `"count"` — controls the y-axis of density /
#'   histogram plots.
#' @param bins Integer number of bins for `kind="histogram"`. Default 30.
#' @param bw KDE bandwidth passed to `density(bw=)` and `geom_density(bw=)`.
#'   Default `"nrd0"`.
#' @param reflect_bounds If TRUE, reflect the KDE at detected boundaries (0 for
#'   non-negative data; 1 for probability data) to remove edge bias. For
#'   `kind="density"` only; a warning is issued for other kinds.
#' @param color NULL (accent palette per group), a single color string
#'   (uniform), or a character vector of length equal to the number of groups
#'   (per-group colors).
#' @param log_x Pre-transform values before KDE / histogram. FALSE | TRUE |
#'   `"log2"` | `"log10"`. Not applicable to `kind="violin"` x-axis (warn +
#'   ignore if categorical x would conflict; applied to values y-axis for
#'   violin).
#' @param log_y For density / histogram: log10-scale the frequency / density
#'   y-axis via `scale_y_log10()`. For violin: pre-transform the values (y)
#'   data (same semantics as `log_y` in pavlab_stripchart).
#' @param pseudocount Added to values before log transform. Default 1.
#' @param origin_zero If TRUE (default) and all y >= 0, expand y lower bound
#'   to include 0. For violin, applies to the values (y) axis.
#' @param label_size `"small"`, `"med"`, `"large"`, or numeric point size.
#'   Default `"med"`.
#' @param xlabel Axis label for the values axis (x for density/histogram; x
#'   for violin group axis). Log suffix appended automatically on values axis.
#' @param ylabel Y-axis label. Auto-derived from `stat` and `kind` if NULL.
#' @param title Plot title. Left-aligned, normal weight.
#' @param xlim Numeric length-2 vector for x-axis limits (density/histogram).
#'   Passed to `coord_cartesian`.
#' @param ylim Numeric length-2 vector for y-axis limits. Passed to
#'   `coord_cartesian`.
#' @param show_mean If TRUE, draw a dashed grey reference line at the grand
#'   mean of post-transform values. Vertical for density/histogram; horizontal
#'   for violin.
#' @param show_median If TRUE, draw a dotted grey reference line at the grand
#'   median. Same orientation as `show_mean`.
#' @param order Optional character vector controlling group level order. Extras
#'   found in `groups` are appended in appearance order.
#' @param figsize Numeric length-2 vector c(width, height) in inches.
#'   Default c(5.5, 5.0).
#' @param filename Save path. Format inferred from extension via ggsave.
#' @return ggplot2 object (invisibly).
#' @export
pavlab_density <- function(
  values,
  groups         = NULL,
  kind           = "density",
  facet          = FALSE,
  stat           = "density",
  bins           = 30,
  bw             = "nrd0",
  reflect_bounds = FALSE,
  color          = NULL,
  log_x          = FALSE,
  log_y          = FALSE,
  pseudocount    = 1.0,
  origin_zero    = TRUE,
  label_size     = "med",
  xlabel         = NULL,
  ylabel         = NULL,
  title          = NULL,
  xlim           = NULL,
  ylim           = NULL,
  show_mean      = FALSE,
  show_median    = FALSE,
  order          = NULL,
  figsize        = NULL,
  filename       = NULL
) {
  if (!requireNamespace("ggplot2", quietly = TRUE))
    stop("pavlab_density: ggplot2 is required. Install with install.packages('ggplot2').",
         call. = FALSE)

  kind <- match.arg(kind, c("density", "histogram", "violin"))
  stat <- match.arg(stat, c("density", "count"))

  values <- as.numeric(values)
  if (!is.null(groups)) {
    groups <- as.character(groups)
    if (length(groups) != length(values))
      stop(sprintf(
        "pavlab_density: values and groups must have equal length (%d vs %d).",
        length(values), length(groups)
      ), call. = FALSE)
  }

  if (kind == "violin" && is.null(groups))
    stop("pavlab_density: groups must be supplied when kind='violin'.", call. = FALSE)

  mask <- is.finite(values)
  values <- values[mask]
  if (!is.null(groups)) groups <- groups[mask]

  if (length(values) == 0)
    warning("pavlab_density: no finite values to plot.", call. = FALSE)

  if (kind == "violin" && !identical(log_x, FALSE)) {
    warning(
      "pavlab_density: log_x is not applicable to kind='violin' (x is categorical); ignoring log_x.",
      call. = FALSE
    )
    log_x <- FALSE
  }

  if (identical(log_x, FALSE)) .maybe_warn_log(values, "x")

  x_kind <- .pick_log_kind(log_x, values, "x")
  if (!is.null(x_kind)) {
    neg <- sum(is.finite(values) & (values + pseudocount) <= 0)
    if (neg > 0)
      warning(sprintf(
        "pavlab_density: %d value(s) will produce -Inf after log transform (pseudocount=%g insufficient).",
        neg, pseudocount
      ), call. = FALSE)
    values <- .apply_log(values, x_kind, pseudocount)
  }

  y_kind <- NULL
  if (kind == "violin") {
    if (identical(log_y, FALSE)) .maybe_warn_log(values, "y")
    y_kind <- .pick_log_kind(log_y, values, "y")
    if (!is.null(y_kind)) {
      neg <- sum(is.finite(values) & (values + pseudocount) <= 0)
      if (neg > 0)
        warning(sprintf(
          "pavlab_density: %d value(s) will produce -Inf after log transform (pseudocount=%g insufficient).",
          neg, pseudocount
        ), call. = FALSE)
      values <- .apply_log(values, y_kind, pseudocount)
    }
  }

  bounds <- .detect_bounds(values)
  has_left  <- !is.na(bounds$left)
  has_right <- !is.na(bounds$right)
  if ((has_left || has_right) && !reflect_bounds && kind == "density") {
    bound_desc <- if (has_right) "[0, 1]" else ">= 0"
    warning(sprintf(
      "pavlab_density: data appears bounded (%s); consider reflect_bounds=TRUE to remove KDE edge bias.",
      bound_desc
    ), call. = FALSE)
  }
  if ((has_left || has_right) && !reflect_bounds && kind %in% c("histogram", "violin")) {
    bound_desc <- if (has_right) "[0, 1]" else ">= 0"
    warning(sprintf(
      "pavlab_density: data appears bounded (%s); reflect_bounds=TRUE has no effect for kind='%s'.",
      bound_desc, kind
    ), call. = FALSE)
  }

  unique_groups <- if (!is.null(groups)) {
    seen <- unique(groups)
    if (!is.null(order)) {
      extra  <- seen[!seen %in% order]
      c(order, extra)
    } else {
      seen
    }
  } else {
    NULL
  }

  if (!is.null(groups))
    groups <- factor(groups, levels = unique_groups)

  col_map <- .group_colors(color, if (!is.null(unique_groups)) unique_groups else "1")
  fill_color_1 <- col_map[[1]]

  fs       <- .font_sizes(label_size)
  label_pt <- fs[1]
  tick_pt  <- fs[2]

  xl <- .axis_label(xlabel, x_kind)
  if (kind == "violin") {
    yl_base <- if (!is.null(ylabel)) ylabel else "Values"
    yl <- .axis_label(yl_base, y_kind)
  } else {
    yl <- if (!is.null(ylabel)) ylabel else
            if (stat == "density") "Density" else "Count"
  }

  if (kind == "violin" && !is.null(groups))
    df <- data.frame(vals = values, grp = groups, stringsAsFactors = FALSE)
  else if (!is.null(groups))
    df <- data.frame(vals = values, grp = groups, stringsAsFactors = FALSE)
  else
    df <- data.frame(vals = values, stringsAsFactors = FALSE)

  ref_line_color    <- "#9ca3af"
  ref_line_width    <- 0.5
  grand_mean_val    <- mean(values, na.rm = TRUE)
  grand_median_val  <- stats::median(values, na.rm = TRUE)

  # ---- kind = "density" -------------------------------------------------------

  if (kind == "density") {
    if (is.null(groups)) {
      if (reflect_bounds) {
        kde_df <- .reflect_kde(values, bw, bounds$left, bounds$right)
        p <- ggplot2::ggplot()
        if (show_mean)
          p <- p + ggplot2::geom_vline(
            xintercept = grand_mean_val,
            color = ref_line_color, linetype = "dashed", linewidth = ref_line_width
          )
        if (show_median)
          p <- p + ggplot2::geom_vline(
            xintercept = grand_median_val,
            color = ref_line_color, linetype = "dotted", linewidth = ref_line_width
          )
        p <- p +
          ggplot2::geom_ribbon(
            data = kde_df,
            ggplot2::aes(x = x, ymin = 0, ymax = y),
            fill = fill_color_1, alpha = 0.5, color = NA
          ) +
          ggplot2::geom_line(
            data = kde_df,
            ggplot2::aes(x = x, y = y),
            color = fill_color_1, linewidth = 0.7
          )
      } else {
        p <- ggplot2::ggplot(df, ggplot2::aes(x = vals))
        if (show_mean)
          p <- p + ggplot2::geom_vline(
            xintercept = grand_mean_val,
            color = ref_line_color, linetype = "dashed", linewidth = ref_line_width
          )
        if (show_median)
          p <- p + ggplot2::geom_vline(
            xintercept = grand_median_val,
            color = ref_line_color, linetype = "dotted", linewidth = ref_line_width
          )
        if (stat == "count") {
          p <- p + ggplot2::geom_density(
            ggplot2::aes(y = ggplot2::after_stat(count)),
            fill = fill_color_1, alpha = 0.5, color = fill_color_1, bw = bw
          )
        } else {
          p <- p + ggplot2::geom_density(
            ggplot2::aes(y = ggplot2::after_stat(density)),
            fill = fill_color_1, alpha = 0.5, color = fill_color_1, bw = bw
          )
        }
      }
    } else {
      if (length(unique_groups) > 3)
        warning(sprintf(
          "pavlab_density: %d groups with facet=FALSE can produce a hard-to-read plot; consider facet=TRUE.",
          length(unique_groups)
        ), call. = FALSE)
      p <- ggplot2::ggplot(df, ggplot2::aes(x = vals, fill = grp, color = grp))
      if (show_mean)
        p <- p + ggplot2::geom_vline(
          xintercept = grand_mean_val,
          color = ref_line_color, linetype = "dashed", linewidth = ref_line_width
        )
      if (show_median)
        p <- p + ggplot2::geom_vline(
          xintercept = grand_median_val,
          color = ref_line_color, linetype = "dotted", linewidth = ref_line_width
        )
      if (stat == "count") {
        p <- p + ggplot2::geom_density(
          ggplot2::aes(y = ggplot2::after_stat(count)),
          alpha = 0.4, bw = bw
        )
      } else {
        p <- p + ggplot2::geom_density(
          ggplot2::aes(y = ggplot2::after_stat(density)),
          alpha = 0.4, bw = bw
        )
      }
      p <- p +
        ggplot2::scale_fill_manual(values = col_map, name = NULL) +
        ggplot2::scale_color_manual(values = col_map, name = NULL)
      if (facet) {
        p <- p + ggplot2::facet_wrap(~grp, scales = "free_y") +
          ggplot2::guides(fill = "none", color = "none")
      }
    }
  }

  # ---- kind = "histogram" -----------------------------------------------------

  if (kind == "histogram") {
    if (is.null(groups)) {
      p <- ggplot2::ggplot(df, ggplot2::aes(x = vals))
      if (show_mean)
        p <- p + ggplot2::geom_vline(
          xintercept = grand_mean_val,
          color = ref_line_color, linetype = "dashed", linewidth = ref_line_width
        )
      if (show_median)
        p <- p + ggplot2::geom_vline(
          xintercept = grand_median_val,
          color = ref_line_color, linetype = "dotted", linewidth = ref_line_width
        )
      if (stat == "density") {
        p <- p + ggplot2::geom_histogram(
          ggplot2::aes(y = ggplot2::after_stat(density)),
          bins = bins, fill = fill_color_1, alpha = 0.7, color = "white"
        )
      } else {
        p <- p + ggplot2::geom_histogram(
          bins = bins, fill = fill_color_1, alpha = 0.7, color = "white"
        )
      }
    } else {
      if (length(unique_groups) > 3)
        warning(sprintf(
          "pavlab_density: %d groups with facet=FALSE can produce a hard-to-read overlapping histogram; consider facet=TRUE.",
          length(unique_groups)
        ), call. = FALSE)
      p <- ggplot2::ggplot(df, ggplot2::aes(x = vals, fill = grp))
      if (show_mean)
        p <- p + ggplot2::geom_vline(
          xintercept = grand_mean_val,
          color = ref_line_color, linetype = "dashed", linewidth = ref_line_width
        )
      if (show_median)
        p <- p + ggplot2::geom_vline(
          xintercept = grand_median_val,
          color = ref_line_color, linetype = "dotted", linewidth = ref_line_width
        )
      if (stat == "density") {
        p <- p + ggplot2::geom_histogram(
          ggplot2::aes(y = ggplot2::after_stat(density)),
          bins = bins, alpha = 0.5, position = "identity", color = NA
        )
      } else {
        p <- p + ggplot2::geom_histogram(
          bins = bins, alpha = 0.5, position = "identity", color = NA
        )
      }
      p <- p + ggplot2::scale_fill_manual(values = col_map, name = NULL)
      if (facet) {
        p <- p + ggplot2::facet_wrap(~grp, scales = "free_y") +
          ggplot2::guides(fill = "none")
      }
    }
  }

  # ---- kind = "violin" --------------------------------------------------------

  if (kind == "violin") {
    p <- ggplot2::ggplot(df, ggplot2::aes(x = grp, y = vals))
    if (show_mean)
      p <- p + ggplot2::geom_hline(
        yintercept = grand_mean_val,
        color = ref_line_color, linetype = "dashed", linewidth = ref_line_width
      )
    if (show_median)
      p <- p + ggplot2::geom_hline(
        yintercept = grand_median_val,
        color = ref_line_color, linetype = "dotted", linewidth = ref_line_width
      )
    violin_fill <- if (is.null(color)) "#4b5563" else col_map[as.character(unique_groups)]
    if (is.null(color)) {
      p <- p + ggplot2::geom_violin(fill = violin_fill, alpha = 0.7, color = NA, bw = bw)
    } else {
      p <- p +
        ggplot2::geom_violin(ggplot2::aes(fill = grp), alpha = 0.7, color = NA, bw = bw) +
        ggplot2::scale_fill_manual(values = col_map, name = NULL) +
        ggplot2::guides(fill = "none")
    }
  }

  # ---- Theme ------------------------------------------------------------------

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

  # ---- Labels -----------------------------------------------------------------

  if (nchar(xl) > 0) p <- p + ggplot2::xlab(xl)
  if (nchar(yl) > 0) p <- p + ggplot2::ylab(yl)
  if (!is.null(title)) p <- p + ggplot2::ggtitle(title)

  # ---- Axis limits ------------------------------------------------------------

  if (kind %in% c("density", "histogram")) {
    if (origin_zero) {
      p <- p + ggplot2::expand_limits(y = 0)
    }
    if (!is.null(xlim) || !is.null(ylim))
      p <- p + ggplot2::coord_cartesian(xlim = xlim, ylim = ylim)
    if (identical(log_y, TRUE) || (is.character(log_y) && log_y %in% c("log2", "log10"))) {
      p <- p + ggplot2::scale_y_log10()
    }
  }

  if (kind == "violin") {
    if (origin_zero) {
      fy <- values[is.finite(values)]
      if (length(fy) > 0 && min(fy) >= 0)
        p <- p + ggplot2::expand_limits(y = 0)
    }
    if (!is.null(ylim))
      p <- p + ggplot2::coord_cartesian(ylim = ylim)
  }

  # ---- Save -------------------------------------------------------------------

  if (!is.null(filename)) {
    w <- if (!is.null(figsize)) figsize[1] else 5.5
    h <- if (!is.null(figsize)) figsize[2] else 5.0
    ggplot2::ggsave(filename, plot = p, width = w, height = h, dpi = 150)
  }

  invisible(p)
}

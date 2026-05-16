# pavlab_scatter: opinionated lab-style scatter plot (ggplot2 backend).
# Mirrors Python pavlab_scatter defaults exactly:
#   - Black filled circles, no background, no gridlines, top+right off
#   - N-adaptive: solid circles ≤500, alpha-scaled 501–10 000, hexbin >10 000
#   - log_x/log_y: FALSE/TRUE/"log2"/"log10"; warns when data spans >100x; never ln
#   - origin_zero: pins non-negative axis lower bound to 0
#   - color: NULL=black; single string=uniform; char/factor vec=categorical+legend;
#            numeric vec=viridis colorbar
#
# Usage:
#   source("R/palettes.R")
#   source("R/pavlab_scatter.R")
#   pavlab_scatter(x, y)
#   pavlab_scatter(x, y, log_x="log2", log_y="log2", xlabel="TPM rep1", ylabel="TPM rep2")
#   pavlab_scatter(x, y, color=cell_types, xlabel="PC1", ylabel="PC2", origin_zero=FALSE)
#   p <- pavlab_scatter(x, y, filename="fig3a.pdf")
#   p + ggplot2::geom_abline(slope=1, linetype="dashed")   # extend with ggplot2 layers
#
# Dependencies: ggplot2 (>= 3.4.0); hexbin required only for N > 10 000.

# ---- Constants ---------------------------------------------------------------

.N_ALPHA   <- 500L
.N_DENSITY <- 10000L

# (axis_label_pt, tick_pt)
.LABEL_SIZES <- list(
  small = c(10.0,  8.0),
  med   = c(14.0, 11.0),
  large = c(18.0, 14.0)
)

.ACCENT_COLORS <- c(
  "#2563eb",  # blue-600   – primary
  "#10b981",  # emerald-500
  "#f59e0b",  # amber-500
  "#ef4444",  # red-500
  "#8b5cf6",  # violet-500
  "#ec4899",  # pink-500
  "#14b8a6",  # teal-500
  "#f97316"   # orange-500
)

# ---- Private helpers ---------------------------------------------------------

.pick_log_kind <- function(val, arr, axis) {
  if (identical(val, FALSE) || is.null(val)) return(NULL)
  if (identical(val, TRUE)) {
    pos <- arr[is.finite(arr) & arr > 0]
    if (length(pos) == 0) {
      warning(sprintf(
        "pavlab_scatter: %s-axis has no positive values; log transform skipped.",
        axis
      ), call. = FALSE)
      return(NULL)
    }
    return(if (max(pos) > 1000) "log10" else "log2")
  }
  if (is.character(val) && val %in% c("log2", "log10")) return(val)
  stop(sprintf(
    "log_%s must be FALSE, TRUE, 'log2', or 'log10'; got '%s'", axis, val
  ), call. = FALSE)
}

.apply_log <- function(arr, kind, pseudocount) {
  shifted <- arr + pseudocount
  if (kind == "log2") log2(shifted) else log10(shifted)
}

.axis_label <- function(base, log_kind) {
  # Unicode subscripts: log₂ = log₂, log₁₀ = log₁₀
  suffix_map <- c(log2 = "(log₂)", log10 = "(log₁₀)")
  suffix <- if (!is.null(log_kind) && log_kind %in% names(suffix_map))
               suffix_map[[log_kind]] else NULL
  parts <- character(0)
  if (!is.null(base)    && nchar(base)   > 0) parts <- c(parts, base)
  if (!is.null(suffix)  && nchar(suffix) > 0) parts <- c(parts, suffix)
  paste(parts, collapse = " ")
}

.font_sizes <- function(label_size) {
  if (is.character(label_size)) {
    if (!label_size %in% names(.LABEL_SIZES))
      stop(sprintf(
        "label_size must be 'small', 'med', 'large', or a number; got '%s'",
        label_size
      ), call. = FALSE)
    return(.LABEL_SIZES[[label_size]])
  }
  v <- as.numeric(label_size)
  c(v, round(v * 0.78, 1))
}

.maybe_warn_log <- function(arr, axis) {
  pos <- arr[is.finite(arr) & arr > 0]
  if (length(pos) < 2) return(invisible(NULL))
  ratio <- max(pos) / min(pos)
  if (ratio > 100) {
    warning(sprintf(
      "pavlab_scatter: %s-axis spans %.0fx — consider log_%s='log2' (biological) or 'log10' (counts).",
      axis, ratio, axis
    ), call. = FALSE)
  }
  invisible(NULL)
}

.color_mode <- function(color, n) {
  if (is.null(color))                                        return("uniform_black")
  if (is.character(color) && length(color) == 1)             return("uniform_string")
  if (is.numeric(color)   && length(color) == 1)             return("uniform_string")
  if ((is.character(color) || is.factor(color)) && length(color) == n) return("categorical")
  if (is.numeric(color) && length(color) == n)               return("numeric")
  stop(
    "color must be NULL, a single color string, a character/factor vector of length n, ",
    "or a numeric vector of length n.",
    call. = FALSE
  )
}

# ---- Main function -----------------------------------------------------------

#' Pavlab-style scatter plot (ggplot2).
#'
#' Opinionated lab defaults: black filled circles, no background, no gridlines,
#' top + right axes off (theme_classic). N-adaptive rendering. Returns a ggplot2
#' object that can be extended with `+` layers.
#'
#' @param x,y Numeric vectors of equal length. Non-finite pairs are silently
#'   dropped.
#' @param color NULL (all black), a single color string (uniform), a
#'   character / factor vector of length n (categorical — lab accent palette +
#'   legend), or a numeric vector of length n (viridis colorbar). Ignored with
#'   a warning when N > 10 000 (density mode).
#' @param color_label Colorbar title for numeric `color`. Default NULL (empty).
#' @param label_size "small", "med", "large", or a numeric point size for axis
#'   labels (tick labels scale proportionally). Default "med" (14 pt / 11 pt).
#' @param xlabel,ylabel Axis labels. Log-scale suffix (“(log₂)” etc.) appended
#'   automatically when a transform is applied.
#' @param title Plot title. Left-aligned, normal weight.
#' @param log_x,log_y FALSE | TRUE | "log2" | "log10". TRUE auto-selects:
#'   log10 when max > 1 000 (counts), log2 otherwise (expression). pseudocount
#'   added before transform so zeros survive. Warns when data spans > 100x and
#'   no transform is requested. ln is never used.
#' @param pseudocount Added to data before log transform. Default 1.
#' @param origin_zero If TRUE (default) and all transformed data >= 0, expands
#'   the axis lower bound to include 0. Explicit xlim / ylim take precedence.
#' @param xlim,ylim Numeric length-2 vectors for explicit axis limits. Take
#'   precedence over origin_zero.
#' @param point_size Override auto marker size (ggplot2 `size=` in mm).
#'   Default: 2.0 for N <= 500, 1.5 for N 501-10 000.
#' @param filename Save path. Format inferred from extension via ggsave.
#' @param figsize Numeric length-2 vector c(width, height) in inches.
#'   Default c(5.5, 5.0).
#' @return ggplot2 object (invisibly).
#' @export
pavlab_scatter <- function(
  x, y,
  color       = NULL,
  color_label = NULL,
  label_size  = "med",
  xlabel      = NULL,
  ylabel      = NULL,
  title       = NULL,
  log_x       = FALSE,
  log_y       = FALSE,
  pseudocount = 1.0,
  origin_zero = TRUE,
  xlim        = NULL,
  ylim        = NULL,
  point_size  = NULL,
  filename    = NULL,
  figsize     = NULL
) {
  if (!requireNamespace("ggplot2", quietly = TRUE))
    stop("pavlab_scatter: ggplot2 is required. Install with install.packages('ggplot2').",
         call. = FALSE)

  x <- as.numeric(x)
  y <- as.numeric(y)
  if (length(x) != length(y))
    stop(sprintf("x and y must have equal length (%d vs %d)", length(x), length(y)),
         call. = FALSE)

  # Align per-point color, then drop non-finite pairs.
  has_vec_color <- !is.null(color) && length(color) == length(x)
  mask <- is.finite(x) & is.finite(y)
  if (has_vec_color) color <- color[mask]
  x <- x[mask]
  y <- y[mask]

  n <- length(x)
  if (n == 0)
    warning("pavlab_scatter: no finite data points to plot.", call. = FALSE)

  # Suggest log scale when not transforming
  if (identical(log_x, FALSE)) .maybe_warn_log(x, "x")
  if (identical(log_y, FALSE)) .maybe_warn_log(y, "y")

  # Apply log transforms
  x_kind <- .pick_log_kind(log_x, x, "x")
  if (!is.null(x_kind)) {
    neg <- sum(is.finite(x) & (x + pseudocount) <= 0)
    if (neg > 0)
      warning(sprintf(
        "pavlab_scatter: %d x value(s) will produce -Inf after log transform (pseudocount=%g insufficient).",
        neg, pseudocount
      ), call. = FALSE)
    x <- .apply_log(x, x_kind, pseudocount)
  }

  y_kind <- .pick_log_kind(log_y, y, "y")
  if (!is.null(y_kind)) {
    neg <- sum(is.finite(y) & (y + pseudocount) <= 0)
    if (neg > 0)
      warning(sprintf(
        "pavlab_scatter: %d y value(s) will produce -Inf after log transform (pseudocount=%g insufficient).",
        neg, pseudocount
      ), call. = FALSE)
    y <- .apply_log(y, y_kind, pseudocount)
  }

  # Density mode
  density_mode <- n > .N_DENSITY
  if (density_mode && !is.null(color)) {
    warning("pavlab_scatter: N > 10 000; using hexbin density mode — 'color' ignored.",
            call. = FALSE)
    color <- NULL
  }

  # Font sizes
  fs       <- .font_sizes(label_size)
  label_pt <- fs[1]
  tick_pt  <- fs[2]

  # Axis labels with log suffix
  xl <- .axis_label(xlabel, x_kind)
  yl <- .axis_label(ylabel, y_kind)

  # Point size + alpha
  ps <- if (!is.null(point_size)) as.numeric(point_size) else
          if (n <= .N_ALPHA) 2.0 else 1.5

  alpha_val <- if (n <= .N_ALPHA) {
    1.0
  } else {
    frac <- min(1.0, (n - .N_ALPHA) / max(1L, .N_DENSITY - .N_ALPHA))
    max(0.15, 0.6 - frac * 0.45)
  }

  # ---- Data frame -----------------------------------------------------------
  df <- data.frame(x = x, y = y)

  # ---- Build ggplot ---------------------------------------------------------

  if (density_mode) {
    if (requireNamespace("hexbin", quietly = TRUE)) {
      p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
        ggplot2::geom_hex(bins = 40) +
        ggplot2::scale_fill_gradientn(colors = black_body_palette(256), name = "count")
    } else {
      message("pavlab_scatter: hexbin not installed; using rectangular bin2d. Install hexbin for hexagonal bins.")
      p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
        ggplot2::geom_bin2d(bins = 40) +
        ggplot2::scale_fill_gradientn(colors = black_body_palette(256), name = "count")
    }

  } else {
    cmode <- .color_mode(color, n)

    if (cmode == "uniform_black") {
      p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
        ggplot2::geom_point(
          color = "#000000", alpha = alpha_val, size = ps, shape = 16, stroke = 0
        )

    } else if (cmode == "uniform_string") {
      p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y)) +
        ggplot2::geom_point(
          color = as.character(color), alpha = alpha_val, size = ps,
          shape = 16, stroke = 0
        )

    } else if (cmode == "categorical") {
      cats     <- unique(as.character(color))
      cat_idx  <- ((seq_along(cats) - 1L) %% length(.ACCENT_COLORS)) + 1L
      cat_cols <- setNames(.ACCENT_COLORS[cat_idx], cats)
      df$color_col <- as.character(color)
      p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y, color = color_col)) +
        ggplot2::geom_point(alpha = alpha_val, size = ps, shape = 16, stroke = 0) +
        ggplot2::scale_color_manual(values = cat_cols, name = NULL) +
        ggplot2::guides(color = ggplot2::guide_legend(
          override.aes = list(size = 3, alpha = 1)
        ))

    } else {
      # numeric → viridis colorbar
      df$color_col <- as.numeric(color)
      clabel <- if (!is.null(color_label)) color_label else ""
      p <- ggplot2::ggplot(df, ggplot2::aes(x = x, y = y, color = color_col)) +
        ggplot2::geom_point(alpha = alpha_val, size = ps, shape = 16, stroke = 0) +
        ggplot2::scale_color_viridis_c(name = clabel)
    }
  }

  # ---- Theme: no background, no gridlines, top+right off -------------------
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

  # ---- Labels ---------------------------------------------------------------
  if (nchar(xl) > 0) p <- p + ggplot2::xlab(xl)
  if (nchar(yl) > 0) p <- p + ggplot2::ylab(yl)
  if (!is.null(title)) p <- p + ggplot2::ggtitle(title)

  # ---- Axis limits ----------------------------------------------------------
  # expand_limits trains the scale to include 0; coord_cartesian clips the view.
  if (origin_zero) {
    fx <- x[is.finite(x)]
    if (length(fx) > 0 && min(fx) >= 0) p <- p + ggplot2::expand_limits(x = 0)
    fy <- y[is.finite(y)]
    if (length(fy) > 0 && min(fy) >= 0) p <- p + ggplot2::expand_limits(y = 0)
  }
  if (!is.null(xlim) || !is.null(ylim)) {
    p <- p + ggplot2::coord_cartesian(xlim = xlim, ylim = ylim)
  }

  # ---- Save -----------------------------------------------------------------
  if (!is.null(filename)) {
    w <- if (!is.null(figsize)) figsize[1] else 5.5
    h <- if (!is.null(figsize)) figsize[2] else 5.0
    ggplot2::ggsave(filename, plot = p, width = w, height = h, dpi = 150)
  }

  invisible(p)
}

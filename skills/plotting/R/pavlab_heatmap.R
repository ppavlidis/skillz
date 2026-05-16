# pavlab_heatmap: opinionated pheatmap wrapper encoding the lab's default
# choices for publication-grade heatmaps. See ../SKILL.md for the rationale
# behind each default.
#
# Source palettes.R alongside this file:
#   source("R/palettes.R"); source("R/pavlab_heatmap.R")
#
# Dependencies: pheatmap (>= 1.0.12), grDevices, stats (all stdlib in R >= 4).

#' Pavlab-style heatmap.
#'
#' Wraps pheatmap::pheatmap with lab-standard defaults: no clustering,
#' grey for missing values, row-standardization for expression mode,
#' Z-clipping at +/- 3, divergent blue-black-yellow palette for signed data,
#' black-body sequential palette for non-negative data, NA on correlation
#' diagonals, and automatic row/column-label hiding when there are too many
#' labels to be readable.
#'
#' Any argument unrecognized by this function is forwarded to pheatmap().
#'
#' @param mat Numeric matrix to plot.
#' @param mode One of "expression", "correlation", "raw". Determines
#'   transformation and palette defaults; see SKILL.md.
#' @param cluster_rows,cluster_cols Logical. Default FALSE.
#' @param show_rownames,show_colnames Logical or NULL (auto).
#' @param standardize_rows Logical or NULL (NULL = TRUE iff mode is
#'   "expression").
#' @param zclip Numeric. Z-score values are clipped to [-zclip, +zclip] when
#'   standardize_rows is TRUE. Default 3.
#' @param divergent Logical or NULL (auto). NULL: TRUE for correlation or
#'   expression, OR for raw data that spans zero.
#' @param na_color Color for missing values. Default "grey80".
#' @param palette_n Number of palette colors. Default 256.
#' @param rowname_threshold,colname_threshold Integer. Auto-hide labels when
#'   the corresponding dimension exceeds the threshold. Defaults 50 (rows)
#'   and 30 (cols).
#' @param angle_col Column-label rotation. Default 45.
#' @param border_color Cell border color. Default NA (no gridlines between
#'   cells — pheatmap's default `grey60` gridlines visually clutter the
#'   color signal).
#' @param correlation_negative_tolerance In `mode = "correlation"`, values
#'   between this threshold and 0 are treated as "effectively zero" — clipped
#'   to 0 and the palette stays sequential (black-body). Only when there are
#'   substantial negative correlations (below this threshold) do we fall back
#'   to the divergent palette. Default -0.1.
#' @param filename If non-NULL, written via pheatmap's filename arg
#'   (auto-detects format from extension).
#' @param ... Forwarded to pheatmap::pheatmap.
#'
#' @return The pheatmap object (invisibly), as returned by pheatmap::pheatmap.
#' @export
pavlab_heatmap <- function(
  mat,
  mode = c("expression", "correlation", "raw"),
  cluster_rows = FALSE,
  cluster_cols = FALSE,
  show_rownames = NULL,
  show_colnames = NULL,
  standardize_rows = NULL,
  zclip = 3,
  divergent = NULL,
  na_color = "grey80",
  palette_n = 256,
  rowname_threshold = 50,
  colname_threshold = 30,
  angle_col = 45,
  border_color = NA,
  correlation_negative_tolerance = -0.1,
  filename = NULL,
  ...
) {
  if (!requireNamespace("pheatmap", quietly = TRUE)) {
    stop("pavlab_heatmap requires the pheatmap package. install.packages('pheatmap')")
  }
  if (!is.matrix(mat)) {
    mat <- as.matrix(mat)
  }
  if (!is.numeric(mat)) {
    stop("pavlab_heatmap: matrix must be numeric (got ", class(mat)[1], ")")
  }
  mode <- match.arg(mode)

  # --- Resolve auto-defaults from mode + data shape ---

  if (is.null(standardize_rows)) {
    standardize_rows <- mode == "expression"
  }
  if (is.null(show_rownames)) {
    show_rownames <- nrow(mat) <= rowname_threshold
  }
  if (is.null(show_colnames)) {
    show_colnames <- ncol(mat) <= colname_threshold
  }

  # --- Mode-specific transforms ---

  if (mode == "correlation") {
    if (nrow(mat) == ncol(mat)) {
      diag(mat) <- NA
    } else {
      warning("pavlab_heatmap: mode='correlation' but matrix isn't square; ",
              "leaving diagonal alone")
    }
  }

  if (isTRUE(standardize_rows)) {
    mat <- t(scale(t(mat)))
    if (!is.null(zclip) && is.finite(zclip) && zclip > 0) {
      mat[!is.na(mat) & mat >  zclip] <-  zclip
      mat[!is.na(mat) & mat < -zclip] <- -zclip
    }
  }

  # --- Palette + symmetric breaks for divergent ---

  if (is.null(divergent)) {
    if (mode == "expression") {
      divergent <- TRUE   # Z-scores always span 0
    } else if (mode == "correlation") {
      # Correlation heatmaps where all values are positive (common — every
      # pair of samples / genes is at least loosely positively correlated)
      # are clearer with the sequential black-body palette. Small negative
      # noise within tolerance gets clipped to 0.
      min_val <- suppressWarnings(min(mat, na.rm = TRUE))
      if (!is.finite(min_val)) {
        divergent <- FALSE
      } else if (min_val >= correlation_negative_tolerance) {
        if (min_val < 0) {
          mat[!is.na(mat) & mat < 0] <- 0
        }
        divergent <- FALSE
      } else {
        divergent <- TRUE
      }
    } else {  # raw
      vals <- mat[is.finite(mat)]
      divergent <- (length(vals) > 0) && any(vals < 0) && any(vals > 0)
    }
  }

  if (isTRUE(divergent)) {
    palette <- divergent_palette(palette_n)
    max_abs <- suppressWarnings(max(abs(mat), na.rm = TRUE))
    if (!is.finite(max_abs) || max_abs == 0) max_abs <- 1
    breaks <- seq(-max_abs, max_abs, length.out = length(palette) + 1)
  } else {
    palette <- black_body_palette(palette_n)
    breaks <- NA   # let pheatmap auto-scale
  }

  # --- Defer to pheatmap ---

  call_args <- list(
    mat = mat,
    color = palette,
    cluster_rows = cluster_rows,
    cluster_cols = cluster_cols,
    show_rownames = show_rownames,
    show_colnames = show_colnames,
    na_col = na_color,
    angle_col = angle_col,
    border_color = border_color
  )
  if (!is.null(filename)) {
    call_args$filename <- filename
  }
  # Only pass breaks if we computed them — otherwise pheatmap should auto-choose.
  if (length(breaks) > 1 && !all(is.na(breaks))) {
    call_args$breaks <- breaks
  }

  # Merge user-provided ... arguments; user values override our defaults.
  extra <- list(...)
  for (nm in names(extra)) call_args[[nm]] <- extra[[nm]]

  do.call(pheatmap::pheatmap, call_args)
}

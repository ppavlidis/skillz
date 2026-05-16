"""pavlab Python plotting helpers.

    import sys
    sys.path.insert(0, "/path/to/skills/plotting/python")
    from pavlab_heatmap import pavlab_heatmap
    from pavlab_scatter import pavlab_scatter
    from pavlab_stripchart import pavlab_stripchart
    from pavlab_density import pavlab_density
"""

from .pavlab_heatmap import pavlab_heatmap      # noqa: F401
from .pavlab_scatter import pavlab_scatter      # noqa: F401
from .pavlab_stripchart import pavlab_stripchart  # noqa: F401
from .pavlab_density import pavlab_density      # noqa: F401
from .palettes import (  # noqa: F401
    black_body_palette,
    divergent_palette,
    divergent_palette_rdbu,
    divergent_palette_spectral,
    divergent_palette_cyan_yellow,
    divergent_palette_blue_yellow,
)

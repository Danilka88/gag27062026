import numpy as np
import plotly.graph_objects as go

from gagarin.viz.utils import TEMPLATE, OBSERVED_COLOR, REFERENCE_COLOR


def profile_comparison(
    observed: np.ndarray,
    reference: np.ndarray,
    azimuth: float,
    speed: float,
    correlation: float,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            y=observed,
            mode="lines",
            name="Observed terrain profile",
            line=dict(color=OBSERVED_COLOR, width=2),
        )
    )
    fig.add_trace(
        go.Scatter(
            y=reference,
            mode="lines",
            name=f"Reference profile (az={azimuth:.1f}°, v={speed:.1f} m/s)",
            line=dict(color=REFERENCE_COLOR, width=2, dash="dash"),
        )
    )

    fig.update_layout(
        title=f"Profile Comparison | Correlation: {correlation:.4f}",
        xaxis_title="Sample",
        yaxis_title="Terrain Height (m)",
        height=450,
        template=TEMPLATE,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    return fig

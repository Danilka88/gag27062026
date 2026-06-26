from typing import Optional
import numpy as np
import plotly.graph_objects as go


def correlation_heatmap(
    azimuths: np.ndarray,
    speeds: np.ndarray,
    corr_matrix: np.ndarray,
    best_azimuth: Optional[float] = None,
    best_speed: Optional[float] = None,
) -> go.Figure:
    fig = go.Figure(
        data=go.Heatmap(
            z=corr_matrix.T,
            x=azimuths,
            y=speeds,
            colorscale="RdBu_r",
            zmid=0,
            colorbar_title="Correlation",
            hovertemplate="Az: %{x:.1f}°<br>Speed: %{y:.1f} m/s<br>Corr: %{z:.3f}<extra></extra>",
        )
    )
    if best_azimuth is not None and best_speed is not None:
        fig.add_trace(
            go.Scatter(
                x=[best_azimuth],
                y=[best_speed],
                mode="markers",
                marker=dict(color="lime", size=14, symbol="star"),
                name=f"Best: {best_azimuth:.1f}°, {best_speed:.1f} m/s",
            )
        )

    fig.update_layout(
        title="Correlation Heatmap: Azimuth vs Speed",
        xaxis_title="Azimuth (°)",
        yaxis_title="Speed (m/s)",
        xaxis=dict(dtick=30),
        height=600,
        template="plotly_dark",
    )
    return fig

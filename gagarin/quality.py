from typing import Optional
import numpy as np

from gagarin.correlator import MatchResult


def assess(match: MatchResult) -> dict:
    confidence = match.confidence
    roughness = match.terrain_roughness

    is_reliable = confidence > 0.6
    is_marginal = 0.3 < confidence <= 0.6

    if is_reliable:
        quality = "good"
    elif is_marginal:
        quality = "marginal"
    else:
        quality = "poor"

    return {
        "quality": quality,
        "confidence": confidence,
        "terrain_roughness": roughness,
        "is_reliable": is_reliable,
        "peak_sharpness": peak_sharpness(match),
        "discrimination_ratio": discrimination_ratio(match),
    }


def peak_sharpness(match: MatchResult) -> float:
    if match is None:
        return 0.0
    corr_signal = np.abs(match.reference_profile - np.mean(match.reference_profile))
    if np.std(corr_signal) < 1e-12:
        return 0.0
    return float(np.max(corr_signal) / np.std(corr_signal))


def discrimination_ratio(match: MatchResult) -> float:
    if match is None:
        return 0.0
    aligned = np.abs(match.observed_profile - match.reference_profile)
    misaligned = np.abs(match.observed_profile - np.roll(match.reference_profile, len(match.reference_profile) // 4))
    sum_aligned = np.sum(aligned)
    sum_misaligned = np.sum(misaligned)
    if sum_aligned < 1e-12:
        return 1.0
    return float(sum_misaligned / sum_aligned)


def assess_match(match: Optional[MatchResult]) -> dict:
    if match is None:
        return {
            "quality": "none",
            "confidence": 0.0,
            "terrain_roughness": 0.0,
            "is_reliable": False,
            "peak_sharpness": 0.0,
            "discrimination_ratio": 0.0,
        }
    return assess(match)

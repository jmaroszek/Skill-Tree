"""Shared settings and exposure rules for bounded, direct-partner synergy."""
import math


def synergy_parameters(pair, strength, cross_context=1.0):
    """Return (strength, anticipation fraction, cross-context coefficient).

    Keep the existing settings keys: d_Syn_pair is the one-partner unfinished
    coefficient before work discount; d_Syn_mul is the completed coefficient.
    Legacy custom bundles could set pair > strength (including strength=0).
    Raise strength to pair in that case, preserving anticipation while making
    completion at least as strong. Named profiles already satisfy this rule.
    """
    values = []
    for label, raw in (('d_Syn_pair', pair), ('d_Syn_mul', strength),
                       ('cross_context_mult', cross_context)):
        try:
            value = float(raw)
        except (TypeError, ValueError, OverflowError):
            raise ValueError(f'{label} must be a finite nonnegative number') from None
        if not math.isfinite(value) or value < 0:
            raise ValueError(f'{label} must be a finite nonnegative number')
        values.append(value)
    pair, strength, cross_context = values
    strength = max(pair, strength)
    return strength, pair / strength if strength else 0.0, cross_context


def partner_exposure(anticipation, cross_context, future_discount):
    """An unfinished partner's exposure, bounded by the completed exposure 1.

    Stable even for a tiny anticipation fraction or a large context premium.
    A zero coefficient disables anticipation, including when anticipation=1.
    """
    if cross_context == 0 or anticipation == 0:
        return 0.0
    if anticipation == 1:
        return future_discount
    return -math.expm1(cross_context * math.log1p(-anticipation)) * future_discount

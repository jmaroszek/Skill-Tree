"""Scoring profiles: the hyperparameters each perspective on the graph uses.

Each profile expresses different priorities. Settings stores only the chosen
profile's name, so a retune here reaches every install."""


# Stamp on a HYPERPARAMS row written by set_hyperparams. Settings stores only
# the profile's name, so the scoring settings follow the profile as the code
# defines it. Before v5, bundles were Settings snapshots and are ignored.
# V5 tool overrides are retained and migrated to bounded synergy in memory;
# v6 writes preserve d_Syn_pair and ensure d_Syn_mul >= d_Syn_pair.
HYPERPARAMS_SCHEMA_VERSION = 6


# Old profile names, and the profile each became.
PROFILE_ALIASES = {'Industrious': 'Pragmatist', 'Pragmatic': 'Pragmatist',
                   'Default': 'Sage', 'Curious': 'Explorer', 'Sprinter': 'Glider',
                   'Compounder': 'Investor'}


DEFAULT_HYPERPARAMS = {
    'w_v': 1.00,
    'w_i': 1.00,
    # Preference transform on own ratings; relationships carry downstream value.
    'value_exponent': 2.00,
    'future_work_half_credit_hours': 1300.0,
    'future_work_exponent': 0.60,
    'd_H': 0.60,
    # Soft prep counts at half a hard step (2026-09): a soft route earns half
    # what the same route starting with a hard edge would.
    'd_S': 0.30,
    'd_Syn_pair': 0.10,  # One unfinished partner, before work discount.
    'd_Syn_mul': 0.40,  # One completed partner; many partners approach twice this.
    'cross_context_mult': 1.00,
    'w_e': 1.50,
    # w_t is on the normalized scale: it is the time term's value at exactly
    # t = TIME_REF_HOURS (40h). The pre-v2 equivalent was w_t / 40**beta.
    'w_t': 6.00,
    'beta': 0.60,
    'goal_boost': 1.50,
    'suggestion_context_premium': 5.0,
    'suggestion_subcontext_premium': 15.0,
    # Goal density remains independent of suggestion diversity. Goal-per-bucket
    # populations are an order of magnitude smaller than scored-node bucket
    # populations (typically 1-5 Goals vs. 20-40 scored nodes per bucket),
    # so a gentler exponent gives proportionate damping. Set to 0 to disable.
    'alpha_goal': 0.20,
}


# Profiles express different priorities. Scaling w_v and w_i together does
# not change rankings; their ratio does. Reassess profile behavior after any
# graph-model change rather than targeting a particular top-ten overlap.
PROFILES = {
    'Sage': DEFAULT_HYPERPARAMS,
    # Curiosity-driven: interest over value, sparse contexts amplified, and
    # enough synergy weight for cross_context_mult to actually register.
    'Explorer': {
        'w_v': 0.50, 'w_i': 2.00, 'value_exponent': 2.50,
        'd_H': 0.50, 'd_S': 0.35,
        'd_Syn_pair': 0.35, 'd_Syn_mul': 0.90,
        'cross_context_mult': 2.50,
        'w_e': 1.50, 'w_t': 6.00, 'beta': 0.60,
        'goal_boost': 1.00, 'alpha_goal': 0.50,
    },
    # Foundational depth. d_H near 1 with a low d_S makes value travel far
    # along *hard* prerequisite chains only, so nodes that unlock large
    # subtrees rise without repeatedly counting the same beneficiary.
    # A high d_S would flood value everywhere and erase the distinction.
    'Investor': {
        'w_v': 1.60, 'w_i': 0.40, 'value_exponent': 1.50,
        'd_H': 0.92, 'd_S': 0.20,
        'd_Syn_pair': 0.02, 'd_Syn_mul': 0.10,
        'cross_context_mult': 1.00,
        'w_e': 1.00, 'w_t': 5.00, 'beta': 0.50,
        'goal_boost': 1.00, 'alpha_goal': 0.00,
    },
    # Goal-driven execution: a strong goal boost, soft prerequisites all but
    # switched off, no synergy wandering. Pre-v2 this profile carried w_t=1.5,
    # which made it the *most* time-biased of the six — the opposite of its
    # stated intent. It now sits close to Sage on the cost axis.
    'Pragmatist': {
        'w_v': 2.00, 'w_i': 0.50, 'value_exponent': 2.50,
        'd_H': 0.65, 'd_S': 0.02,
        'd_Syn_pair': 0.00, 'd_Syn_mul': 0.10,
        'cross_context_mult': 1.00,
        'w_e': 1.80, 'w_t': 7.00, 'beta': 0.70,
        'goal_boost': 4.00, 'alpha_goal': 0.05,
    },
    # Synthesis: the pair bonus is large enough that cross_context_mult has
    # substantial influence on cross-context relationships.
    'Creator': {
        'w_v': 1.00, 'w_i': 1.00, 'value_exponent': 2.00,
        'd_H': 0.55, 'd_S': 0.45,
        'd_Syn_pair': 0.60, 'd_Syn_mul': 1.30,
        'cross_context_mult': 3.00,
        'w_e': 1.50, 'w_t': 6.00, 'beta': 0.60,
        'goal_boost': 1.00, 'alpha_goal': 0.20,
    },
    # Deliberately short-task biased — this is the profile's purpose, not a
    # defect. w_t 135 is the normalized equivalent of the pre-v2 w_t 4.0.
    'Glider': {
        'w_v': 1.00, 'w_i': 1.00, 'value_exponent': 1.00,
        'd_H': 0.40, 'd_S': 0.20,
        'd_Syn_pair': 0.05, 'd_Syn_mul': 0.20,
        'cross_context_mult': 1.00,
        'w_e': 3.50, 'w_t': 135.00, 'beta': 0.95,
        'goal_boost': 1.00, 'alpha_goal': 0.35,
    },
}


# Seed independently persisted future preferences from each profile's starting
# curvature. Later changes to beta do not change this preference.
# Premiums are percent extra merit needed after one previous recommendation.
SUGGESTION_PREMIUMS = {
    'Sage': (5.0, 15.0), 'Explorer': (10.0, 20.0),
    'Investor': (0.0, 0.0), 'Pragmatist': (2.0, 5.0),
    'Creator': (5.0, 15.0), 'Glider': (5.0, 20.0),
}
for _name, _profile in PROFILES.items():
    (_profile['suggestion_context_premium'],
     _profile['suggestion_subcontext_premium']) = SUGGESTION_PREMIUMS[_name]
    _profile.setdefault('future_work_half_credit_hours', 1300.0)
    _profile.setdefault('future_work_exponent', _profile['beta'])

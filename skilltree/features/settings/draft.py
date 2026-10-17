"""A Settings draft: which settings it changes, and writing them in one go."""
from skilltree.store.resources import get_sections, live_sections, save_sections
from skilltree.store import settings

# The same complete draft is committed after an ordinary close or after the
# migration dialog. Validation and migration planning happen before any write.
# Each draft key, and the setting it holds.
_DRAFT_SETTINGS = {
    'hp_profile': settings.HP_PROFILE, 'ts': settings.TIME_SETTINGS,
    'contexts': settings.CONTEXTS, 'subcontexts': settings.SUBCONTEXTS,
    'context_weights': settings.CONTEXT_WEIGHTS, 'shapes': settings.NODE_SHAPES,
    'colors': settings.NODE_COLORS, 'name_formatting': settings.NAME_FORMATTING,
    'show_scoring_perf': settings.SHOW_SCORING_PERF,
    'time_calibration_enabled': settings.TIME_CALIBRATION_ENABLED,
    'now_node_cap': settings.NOW_NODE_CAP,
    'subcontext_sort_mode': settings.SUBCONTEXT_SORT_MODE,
    'context_sort_mode': settings.CONTEXT_SORT_MODE,
    'backup_extra_dir': settings.BACKUP_EXTRA_DIR,
}


def changed_settings(draft):
    changed = {}
    for key, setting in _DRAFT_SETTINGS.items():
        if key not in draft:
            continue
        current = setting.get()
        if key == 'context_weights':
            # Missing weights already mean 1. Opening/closing the modal must
            # not turn those defaults into an edit or clear profile overrides.
            current = {name: current.get(name, 1.0)
                       for name in set(current) | set(draft[key])}
        if draft[key] != current:
            changed[key] = draft[key]
    return changed


def normalized_sections(rows):
    return [{'id': row['id'], 'name': (row.get('name') or '').strip(),
             'root_path': (row.get('root_path') or '').strip(), 'position': i}
            for i, row in enumerate(live_sections(rows))]


def apply_settings(draft):
    for key, value in changed_settings(draft).items():
        _DRAFT_SETTINGS[key].set(value)
        if key == 'hp_profile':
            settings.clear_hyperparams()
    if (normalized_sections(draft['resource_sections']) != get_sections()):
        save_sections(draft['resource_sections'])

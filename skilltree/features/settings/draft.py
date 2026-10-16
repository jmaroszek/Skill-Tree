"""A Settings draft: which settings it changes, and writing them in one go."""
from skilltree.store.resources import get_sections, live_sections, save_sections
from skilltree.store.settings import ConfigManager

# The same complete draft is committed after an ordinary close or after the
# migration dialog. Validation and migration planning happen before any write.
_SETTING_METHODS = {
    'hp_profile': 'hp_profile', 'ts': 'time_settings',
    'contexts': 'contexts', 'subcontexts': 'subcontexts',
    'context_weights': 'context_weights', 'shapes': 'node_shapes',
    'colors': 'node_colors', 'name_formatting': 'name_formatting',
    'show_scoring_perf': 'show_scoring_perf',
    'time_calibration_enabled': 'time_calibration_enabled',
    'now_node_cap': 'now_node_cap', 'subcontext_sort_mode': 'subcontext_sort_mode',
    'context_sort_mode': 'context_sort_mode', 'backup_extra_dir': 'backup_extra_dir',
}


def changed_settings(draft):
    changed = {}
    for key, method in _SETTING_METHODS.items():
        if key not in draft:
            continue
        current = getattr(ConfigManager, 'get_' + method)()
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
        getattr(ConfigManager, 'set_' + _SETTING_METHODS[key])(value)
        if key == 'hp_profile':
            ConfigManager.clear_hyperparams()
    if (normalized_sections(draft['resource_sections']) != get_sections()):
        save_sections(draft['resource_sections'])

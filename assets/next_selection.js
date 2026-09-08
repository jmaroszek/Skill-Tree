/* Next selection is local: descriptions travel with the displayed rows. */
(function () {
    function rows(children, type) {
        const found = [];
        function visit(value) {
            if (Array.isArray(value)) { value.forEach(visit); return; }
            if (!value || !value.props) return;
            const props = value.props;
            if (props.id && props.id.type === type) found.push(props);
            visit(props.children);
        }
        visit(children);
        return found;
    }
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.skillTreeNext = {
        select: function (clicks, nowClicks, table, cards, selected) {
            const suggestions = rows(table, 'suggestion-row');
            const now = rows(cards, 'now-row');
            const all = suggestions.concat(now);
            const triggered = window.dash_clientside.callback_context.triggered || [];
            for (const trigger of triggered) {
                if (!trigger.value || !trigger.prop_id.endsWith('.n_clicks')) continue;
                try {
                    const id = JSON.parse(trigger.prop_id.slice(0, -9));
                    if (all.some(row => row.id.index === id.index)) selected = id.index;
                } catch (_) { /* Initial insertion is not a user click. */ }
            }
            const row = all.find(row => row.id.index === selected);
            if (!row) selected = null;
            const description = row ? (row['data-description'] || 'No description')
                : 'Click a card or row to see its description';
            function style(row, card) {
                const active = row.id.index === selected;
                const result = Object.assign({}, row.style);
                if (active || card) result.backgroundColor = active ? '#2b3035' : '#212529';
                else delete result.backgroundColor;
                if (card) {
                    result.border = active ? '2px solid #0d6efd' : '1px solid #495057';
                    result.transition = 'none';
                }
                return result;
            }
            return [selected, description, suggestions.map(row => style(row, false)),
                now.map(row => style(row, true)),
                {color: row ? '#dee2e6' : '#6c757d', whiteSpace: 'pre-wrap', fontSize: '0.95rem'}];
        }
    };
}());

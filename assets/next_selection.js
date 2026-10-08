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
    function el(type, props) {
        return {type: type, namespace: 'dash_html_components', props: props};
    }
    // The selected node's neighbours, from the row's data-relations JSON.
    const SECTIONS = [['supports', 'Supports'], ['synergy', 'Synergy']];
    const SHOWN = 3;
    function relations(row) {
        if (!row) return null;
        let data;
        try { data = JSON.parse(row['data-relations'] || '{}'); } catch (_) { return null; }
        const blocks = [];
        for (const [key, title] of SECTIONS) {
            const items = data[key] || [];
            if (!items.length) continue;
            const children = [el('Div', {
                children: title + '  ' + items.length,
                style: {fontFamily: 'var(--st-font-mono)', fontSize: 'var(--st-fs-sm)',
                        color: 'var(--st-text-dim)', margin: '1.25rem 0 0.4rem',
                        whiteSpace: 'pre', gridColumn: '1 / -1'},
            })];
            for (const [name, color, kind, done] of items.slice(0, SHOWN)) {
                const tag = [kind, done ? 'done' : ''].filter(Boolean).join(' · ');
                children.push(el('Div', {
                    children: [
                        el('Span', {children: name, style: {
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            color: done ? 'var(--st-text-dim)' : 'var(--st-text-primary)'}}),
                        el('Span', {children: tag, style: {
                            fontFamily: 'var(--st-font-mono)', fontSize: 'var(--st-fs-sm)',
                            color: 'var(--st-text-dim)', flexShrink: 0}}),
                    ],
                    style: {display: 'grid', gridTemplateColumns: 'subgrid', gridColumn: '1 / -1',
                            alignItems: 'baseline',
                            borderLeft: '3px solid ' + color, paddingLeft: '10px',
                            margin: '0 0 6px', fontSize: 'var(--st-fs-md)', lineHeight: '1.5',
                            opacity: done ? 0.7 : 1},
                }));
            }
            if (items.length > SHOWN) {
                children.push(el('Div', {children: '+' + (items.length - SHOWN) + ' more',
                    style: {fontSize: 'var(--st-fs-sm)', color: 'var(--st-text-dim)',
                            paddingLeft: '13px', gridColumn: '1 / -1'}}));
            }
            // One grid per section: the tags line up in a column that starts
            // just after the longest name, not at the edge of the panel.
            blocks.push(el('Div', {children: children, style: {
                display: 'grid',
                gridTemplateColumns: 'minmax(0, max-content) max-content',
                columnGap: '100px', justifyContent: 'start'}}));
        }
        if (!blocks.length) return null;
        return el('Div', {children: blocks});
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
            // Wildcard outputs are matched to components in Dash's own registry
            // order, which stops following layout order once Now cards have been
            // reordered. Return each style at the position Dash asks for.
            function styles(rowsInLayout, outputs, card) {
                if (!outputs) return rowsInLayout.map(row => style(row, card));
                const byIndex = new Map(rowsInLayout.map(row => [row.id.index, row]));
                return outputs.map(output => {
                    const row = byIndex.get(output.id.index);
                    return row ? style(row, card) : window.dash_clientside.no_update;
                });
            }
            const outputs = window.dash_clientside.callback_context.outputs_list || [];
            return [selected, description, styles(suggestions, outputs[2], false),
                styles(now, outputs[3], true),
                {color: row ? '#dee2e6' : '#6c757d', whiteSpace: 'pre-wrap', fontSize: '0.95rem'},
                relations(row)];
        }
    };
}());

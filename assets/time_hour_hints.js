(function () {
    'use strict';
    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.time_hour_hints = {
        render: function (lower, expected, upper, unit, settings) {
            settings = settings || {};
            var week = settings.hours_per_week == null ? 20 : settings.hours_per_week;
            var month = settings.hours_per_month == null ? 80 : settings.hours_per_month;
            var multipliers = {days: week / 7, weeks: week, months: month, years: month * 13};
            var multiplier = multipliers[unit];
            var enabled = settings.show_hour_equivalents !== false && multiplier > 0;
            var texts = [];
            var styles = [];
            var anyVisible = false;
            [lower, expected, upper].forEach(function (value, index) {
                var id = 'node-time-' + ['o', 'm', 'p'][index];
                var input = document.getElementById(id);
                if (input) input.setAttribute('aria-describedby', id + '-hours');
                var hours = value * multiplier;
                var visible = enabled && typeof value === 'number' &&
                    Number.isFinite(hours) && value >= 0;
                anyVisible = anyVisible || visible;
                var rounded = Math.round(hours * 10) / 10;
                // Don't turn a positive sub-tenth-hour estimate into a zero.
                var text = hours > 0 && rounded === 0 ? '< 0.1h' :
                    '= ' + rounded.toLocaleString('en-US', {maximumFractionDigits: 1}) + 'h';
                texts.push(visible ? text : '');
                styles.push({display: visible ? 'block' : 'none'});
            });
            return texts.concat(styles, [anyVisible ? 'has-hour-hints' : '']);
        }
    };
})();

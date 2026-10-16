(function () {
    'use strict';
    window.dash_clientside = window.dash_clientside || {};

    // Hour equivalents for a lower/expected/upper trio of inputs. Returns the
    // three hint texts, then the three styles, then whether any hint shows.
    function hints(ids, values, unit, settings) {
        settings = settings || {};
        // The store holds the full saved settings. Without a rate, no hint.
        var week = settings.hours_per_week;
        var month = settings.hours_per_month;
        var multipliers = {days: week / 7, weeks: week, months: month, years: month * 13};
        var multiplier = multipliers[unit];
        var enabled = settings.show_hour_equivalents !== false && multiplier > 0;
        var texts = [];
        var styles = [];
        var anyVisible = false;
        values.forEach(function (value, index) {
            var id = ids[index];
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
        return texts.concat(styles, [anyVisible]);
    }

    window.dash_clientside.time_hour_hints = {
        render: function (lower, expected, upper, unit, settings) {
            var out = hints(['node-time-o', 'node-time-m', 'node-time-p'],
                            [lower, expected, upper], unit, settings);
            out[6] = out[6] ? 'has-hour-hints' : '';
            return out;
        },
        // The reflection modal's actual-time inputs.
        render_actual: function (lower, point, upper, unit, settings) {
            var out = hints(['time-calibration-lower', 'time-calibration-point',
                             'time-calibration-upper'],
                            [lower, point, upper], unit, settings);
            return out.slice(0, 6);
        }
    };
})();

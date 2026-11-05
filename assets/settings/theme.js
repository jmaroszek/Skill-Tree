/* Settings > Appearance's theme choice.

   Choosing one repaints everything CSS draws at once, as a preview. Closing the
   dialog saves it, and then the page reloads: bars, badges, charts and canvases
   take their colors from the server, which only has the new theme after that. */
(function () {
    var html = document.documentElement;
    var saved = html.dataset.theme;
    var noUpdate = function () { return window.dash_clientside.no_update; };

    window.dash_clientside = window.dash_clientside || {};
    window.dash_clientside.skilltree_theme = {
        preview: function (theme) {
            if (theme) html.dataset.theme = theme;
            return noUpdate();
        },
        reloadIfSaved: function (version, theme) {
            if (version && theme && theme !== saved) location.reload();
            return noUpdate();
        },
    };
})();

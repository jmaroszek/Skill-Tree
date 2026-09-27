# The download page

`index.html` is a single, self-contained download page for Skill Tree: no build
step, no other files, nothing loaded from elsewhere but GitHub's API. Put it
anywhere that serves a static page.

When it opens, it asks GitHub for the latest published release and lists each
installer in it, for Windows, both kinds of Mac and Linux. It suggests the one for
the visitor's system where the browser can tell. It links the release's
`SHA256SUMS`, its notes, and the install, privacy and troubleshooting pages. Until
there is a published release, or if GitHub can't be reached, its button opens the
releases page instead.

To use it:

- **On your own site:** copy `index.html` there, as a page or inside one. The
  script and styles are inline.
- **On GitHub Pages:** Pages publishes a branch only from its root or `/docs`,
  so publish this folder with a workflow instead: in Settings → Pages choose
  **GitHub Actions** as the source, and add a workflow that runs
  `actions/configure-pages`, then `actions/upload-pages-artifact` with
  `path: website`, then `actions/deploy-pages`. The page is then at
  `https://jmaroszek.github.io/Skill-Tree/`.

The installer names it looks for come from `electron/electron-builder.yml`.
`tests/test_download_page.py` fails if the two drift apart.

GitHub answers 60 requests an hour from each visitor's address without a key,
which is far more than one page view needs.

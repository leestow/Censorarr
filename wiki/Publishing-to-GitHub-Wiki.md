# Publishing These Pages to the GitHub Wiki Tab

The files in this `wiki/` folder are the canonical documentation source inside the main Censorarr repository.

GitHub's **Wiki** tab is stored as a separate Git repository (`Censorarr.wiki.git`), so it is not the same repository as the application source.

## One-time setup

1. In the Censorarr GitHub repository, open **Settings**.
2. Under repository features, enable **Wikis** if it is not already enabled.
3. Open the **Wiki** tab.
4. Create the first page if GitHub asks you to initialize the wiki.

## Publish from a terminal

Clone the wiki repository:

```bash
git clone https://github.com/leestow/Censorarr.wiki.git
cd Censorarr.wiki
```

Copy the Markdown files from the main repository's `wiki/` folder into the root of the wiki clone.

Then:

```bash
git add .
git commit -m "Publish Censorarr documentation"
git push
```

`Home.md` becomes the Wiki home page.

`_Sidebar.md` becomes the Wiki sidebar.

## Updating later

Keep the main repository's `wiki/` folder as the source of truth. When documentation changes, copy the updated Markdown files to the wiki repo and push again.

This avoids having two independently edited copies drift apart.

#!/usr/bin/env python

"""
This script will automatically add a list of recently edited or added recipes
to the top-level README of the recipes website.

It is intended that this script is run via GitHub actions (i.e. the edits to
the README with recent changes are not committed to the repo).
"""

from typing import List, Dict, Tuple

import sys
import re
import html

from pathlib import Path
from subprocess import run
from datetime import datetime, timedelta
from recipe_grid.markdown import compile_markdown


# The duration within which a commit is considered 'recent'
recent_limit = timedelta(days=14)


################################################################################
# Locate files
################################################################################

recipes_dir = Path(sys.argv[0]).resolve().parent.parent / "recipes"
root_readme_filename = recipes_dir / "README.md"


################################################################################
# Select recent commits
################################################################################

commits_and_dates_str = run(
    ["git", "log", "--pretty=format:%H %at"],
    cwd=recipes_dir,
    check=True,
    capture_output=True,
    encoding="utf-8",
).stdout

now = datetime.now()

commits_and_dates = [
    (
        line.partition(" ")[0],
        datetime.fromtimestamp(int(line.partition(" ")[2])),
    )
    for line in commits_and_dates_str.splitlines()
]

recent_commits = [
    (commit_id, timestamp)
    for commit_id, timestamp in commits_and_dates
    if now - timestamp < recent_limit
]


################################################################################
# Gather changed files (and their latest change dates)
################################################################################

repo_root = Path(
    run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=recipes_dir,
        capture_output=True,
        encoding="utf-8",
        check=True,
    ).stdout.rstrip()
)


def get_files_touched_by_commit(commit_id) -> List[Path]:
    file_list_str = run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_id],
        cwd=recipes_dir,
        check=True,
        capture_output=True,
        encoding="utf-8",
    ).stdout

    return [(repo_root / p).resolve() for p in file_list_str.splitlines()]


recently_modified_files: Dict[Path, datetime] = {}
for commit_id, timestamp in recent_commits:
    for file in get_files_touched_by_commit(commit_id):
        if (
            # File mustn't have been deleted
            file.is_file()
            and
            # File must be in the recipes dir
            file.parts[: len(recipes_dir.parts)] == recipes_dir.parts
            and
            # File must be a recipe
            file.name.endswith(".md")
            and
            # File must not be a README
            file.name.lower() not in ("readme.md", "index.md")
        ):
            if recently_modified_files.get(file, timestamp) <= timestamp:
                recently_modified_files[file] = timestamp


################################################################################
# Extract recipe titles
################################################################################


def extract_title(file: Path) -> str:
    try:
        return compile_markdown(file.read_text()).title or file.name
    except:
        return file.name


recently_modified_recipes: List[Tuple[Path, datetime, str]] = [
    (
        file,
        timestamp,
        extract_title(file),
    )
    for file, timestamp in sorted(
        recently_modified_files.items(),
        key=lambda x: (now - x[1], x[0]),
    )
]


################################################################################
# Generate change list
################################################################################

if recently_modified_recipes:
    change_list_html = '<div class="recent-recipes">\n'
    change_list_html += "  <p>Recently added and updated recipes:</p>\n\n  <ul>\n"
    for file, timestamp, title in recently_modified_recipes:
        href = html.escape(str(file.relative_to(recipes_dir)), quote=True)
        title = html.escape(title)
        date = timestamp.strftime("%d-%m-%Y")
        change_list_html += f'    <li><span class="date">{date}</span> <a href="{href}">{title}</a></li>\n'
    change_list_html += "  </ul>\n"
    change_list_html += "</div>"
else:
    change_list_html = ""

################################################################################
# Update README
################################################################################

begin = "<!-- RECENT CHANGE LIST BEGIN -->"
end = "<!-- RECENT CHANGE LIST END -->"

readme = root_readme_filename.read_text()
readme = re.sub(
    f"{re.escape(begin)}.*{re.escape(end)}",
    f"{begin}\n{change_list_html}\n{end}",
    readme,
    flags=re.DOTALL,
)
root_readme_filename.write_text(readme)

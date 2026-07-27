#!/bin/bash
set -e

echo "Reminder: add a CHANGELOG.md entry for this release before committing.";
echo;

if [[ $(git status --porcelain) ]]; then

	echo "Error: git working tree is not clean. Commit or stash changes first.";

	exit 1;

fi;

read -p "Enter the new version (e.g., 1.0.2): " VERSION

VERSION=${VERSION#v};

echo "Releasing v$VERSION...";

echo "Running tests and linting";
pytest;
ruff check .;

# Update the version.py file
VERSION_FILE="src/speechweave/version.py";
echo "__version__ = \"$VERSION\"" > "$VERSION_FILE";

# Commit the version bump
git add "$VERSION_FILE";
git commit -m "chore: release v$VERSION";

git tag "v$VERSION";

echo "Pushing commit and tags to GitHub";
git push github main;
git push github "v$VERSION";

echo "Release [v$VERSION] triggered successfully";

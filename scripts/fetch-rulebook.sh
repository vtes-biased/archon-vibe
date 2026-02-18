#!/bin/bash
# Fetch the VTES rulebook from GitHub and prepare it for the help section.
# Run manually when the rulebook is updated upstream.
set -euo pipefail

REPO="GiottoVerducci/rulebook2024"
BRANCH="main"
BASE_URL="https://raw.githubusercontent.com/${REPO}/${BRANCH}"
REFERENCE_DIR="$(cd "$(dirname "$0")/.." && pwd)/reference"
STATIC_DIR="$(cd "$(dirname "$0")/.." && pwd)/frontend/static/help/rules"

echo "Fetching rulebook markdown..."
mkdir -p "$REFERENCE_DIR"
curl -fsSL "${BASE_URL}/content.md" -o "${REFERENCE_DIR}/vtes-rules.md"

echo "Rewriting image paths..."
# Replace bin/media/imageN.png with /help/rules/imageN.png
sed -i '' 's|bin/media/image|/help/rules/image|g' "${REFERENCE_DIR}/vtes-rules.md"

echo "Converting vekn.net links to local anchors..."
# Cross-references with fragment: [**Text**](https://www.vekn.net/rulebook/...#fragment)
# → [**Text**](#fragment)  (keep link, point to local anchor)
sed -i '' 's|](https://www.vekn.net/rulebook/[^#)]*#\([^)]*\))|](#\1)|g' "${REFERENCE_DIR}/vtes-rules.md"
# Cross-references with fragment only: [**Text**](https://www.vekn.net/rulebook#fragment)
# → [**Text**](#fragment)
sed -i '' 's|](https://www.vekn.net/rulebook#\([^)]*\))|](#\1)|g' "${REFERENCE_DIR}/vtes-rules.md"
# Remaining path-only links on non-heading lines: derive fragment from path slug
# e.g. [**Quick Reference**](https://www.vekn.net/rulebook/9-quick-reference)
# → [**Quick Reference**](#quick-reference) (strip leading number prefix)
python3 -c "
import re, sys
text = open(sys.argv[1]).read()
def convert(m):
    full, bracket_content, path = m.group(0), m.group(1), m.group(2)
    # If this is a heading line (starts with #), strip the link entirely
    line_start = text.rfind('\n', 0, m.start()) + 1
    if text[line_start:m.start()].lstrip().startswith('#'):
        return bracket_content
    # Otherwise convert path to local anchor
    slug = path.rstrip('/').rsplit('/', 1)[-1]
    slug = re.sub(r'^\d+-', '', slug)  # strip leading number prefix
    return f'[{bracket_content}](#{slug})'
text = re.sub(r'\[([^\]]*)\]\(https://www\.vekn\.net/rulebook/([^)#]*)\)', convert, text)
open(sys.argv[1], 'w').write(text)
" "${REFERENCE_DIR}/vtes-rules.md"

echo "Fetching images..."
mkdir -p "$STATIC_DIR"
for i in $(seq 1 71); do
  FILE="image${i}.png"
  if [ ! -f "${STATIC_DIR}/${FILE}" ]; then
    echo "  Downloading ${FILE}..."
    curl -fsSL "${BASE_URL}/bin/media/${FILE}" -o "${STATIC_DIR}/${FILE}" || echo "  Warning: ${FILE} not found"
  else
    echo "  Skipping ${FILE} (already exists)"
  fi
done

echo "Done. Files saved to:"
echo "  ${REFERENCE_DIR}/vtes-rules.md"
echo "  ${STATIC_DIR}/"
echo ""
echo "Review and commit the results."

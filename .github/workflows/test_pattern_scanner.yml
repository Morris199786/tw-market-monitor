name: Test Pattern Scanner

on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  scan-patterns:
    runs-on: ubuntu-latest
    timeout-minutes: 20

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install requests

      - name: Check scanner file
        run: |
          echo "Checking pattern_scanner.py..."
          test -f pattern_scanner.py
          python -m py_compile pattern_scanner.py
          echo "Scanner OK"

      - name: Run pattern scanner
        run: |
          python pattern_scanner.py --top 50

      - name: Show Top 50
        if: always()
        run: |
          echo "========== PATTERN SCANNER RESULT =========="

          if [ -f pattern_scan_top30.csv ]; then
            cat pattern_scan_top30.csv
          else
            echo "pattern_scan_top30.csv not found"
          fi

      - name: Upload scan results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: pattern-scanner-result
          path: |
            pattern_scan_top30.csv
            pattern_scan_top30.json
          if-no-files-found: warn
          retention-days: 7

      - name: Commit scan results
        if: success()
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

          git add pattern_scan_top30.csv pattern_scan_top30.json

          if git diff --cached --quiet; then
            echo "No pattern scan changes to commit"
            exit 0
          fi

          git commit -m "data: update pattern scanner results"

          # 避免掃描期間其他 workflow 剛好更新 main
          git pull --rebase origin main
          git push origin HEAD:main

      - name: Done
        if: success()
        run: |
          echo "Pattern scanner completed"
          echo "Top 50 results committed:"
          echo "  pattern_scan_top30.csv"
          echo "  pattern_scan_top30.json"

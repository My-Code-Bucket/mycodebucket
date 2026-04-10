# Tools

This repository is meant to hold multiple small standalone tools.

## Current Tools

## `uvchat`

- path: [`uvchat/`](/home/ubuntu/uvchat/uvchat)
- purpose: OCR-based Utherverse chat companion window
- status: MVP

## Adding A New Tool

Use one subfolder per tool.

Recommended layout:

```text
mycodebucket/
  README.md
  TOOLS.md
  tool-name/
    README.md
    src or app files
    local config example
    launcher scripts
```

## Conventions

- keep each tool self-contained
- keep local runtime files inside the tool folder
- do not commit local secrets
- prefer a short `README.md` inside each tool folder
- keep repo-root files focused on overview and navigation

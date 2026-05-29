# Import Line Direct Extraction

**Simplified import extraction that returns raw import lines for LLM processing.**

---

## 🎯 Purpose

This module extracts raw import/using lines from source code files **without** path resolution or complex processing. The import lines are passed directly to the LLM, which handles:

- Path resolution
- Dependency detection
- Edge case handling
- Context understanding

---

## 🆚 Comparison with `imports_extract/`

| Feature | `imports_extract/` | `imports_line_direct_extraction/` |
|---------|-------------------|----------------------------------|
| **Import Detection** | ✅ AST parsing | ✅ AST parsing |
| **Path Resolution** | ✅ Full resolution | ❌ Not needed |
| **Relative Imports** | ✅ Resolves to absolute | ❌ Returns as-is |
| **Wildcard Expansion** | ✅ Expands `import *` | ❌ Returns as-is |
| **External Filtering** | ✅ Filters stdlib/packages | ❌ Returns all |
| **Output** | Complex objects | Simple strings |
| **Use Case** | Benchmarking, analysis | LLM input |

---

## 🚀 Quick Start

### Basic Usage

```python
from app.services.rag_services.imports_line_direct_extraction import (
    extract_import_lines_from_file,
    extract_import_lines_from_pr_files
)

# Single file
code = """
import os
from app.utils import helper
"""

result = await extract_import_lines_from_file(code, "main.py", "python")
print(result.import_lines)
# Output: ['import os', 'from app.utils import helper']

# Multiple files (parallel)
pr_files = [
    {"path": "main.py", "content": "import os", "language": "python"},
    {"path": "App.java", "content": "import java.util.List;", "language": "java"}
]

result = await extract_import_lines_from_pr_files(pr_files)
print(result.summary)
# Output: {'total_files': 2, 'total_imports': 2, 'languages': ['java', 'python']}
```

---

## 📋 Supported Languages

- **Python**: `import` and `from ... import` statements
- **JavaScript**: `import` statements
- **TypeScript**: `import` statements
- **Java**: `import` declarations
- **C#**: `using` directives

---

## 🔍 Features

### 1. **Raw Line Extraction**
Returns import lines exactly as they appear in code:

```python
# Input code:
import os
from app.utils import (
    helper1,
    helper2
)

# Output:
[
    "import os",
    "from app.utils import (\n    helper1,\n    helper2\n)"
]
```

### 2. **Automatic Deduplication**
Removes duplicate imports automatically:

```python
# Input code:
import os
import sys
import os  # duplicate

# Output:
["import os", "import sys"]
```

### 3. **Comment Filtering**
Skips commented imports (Tree-sitter excludes comments from AST):

```python
# Input code:
import os
# import sys  (this is skipped)

# Output:
["import os"]
```

### 4. **Original Order Preserved**
Maintains the order imports appear in the file for context preservation.

### 5. **Parallel Processing**
Processes multiple files concurrently for better performance.

---

## 📊 Output Format

### FileImportLines
```python
{
    "file_path": "app/services/auth.py",
    "language": "python",
    "import_lines": [
        "import os",
        "from app.utils import helper"
    ]
}
```

### PRImportLinesSummary
```python
{
    "summary": {
        "total_files": 5,
        "total_imports": 25,
        "languages": ["python", "javascript", "java"]
    },
    "files": [
        # List of FileImportLines objects
    ]
}
```

---

## 🎯 Language-Specific Examples

### Python
```python
# Input:
import os
from app.utils import helper
from ..parent import config

# Output:
[
    "import os",
    "from app.utils import helper",
    "from ..parent import config"  # Relative import as-is
]
```

### JavaScript/TypeScript
```javascript
// Input:
import React from 'react';
import { useState, useEffect } from 'react';
import './styles.css';

// Output:
[
    "import React from 'react';",
    "import { useState, useEffect } from 'react';",
    "import './styles.css';"
]
```

### Java
```java
// Input:
import java.util.List;
import com.app.models.User;
import static java.lang.Math.*;

// Output:
[
    "import java.util.List;",
    "import com.app.models.User;",
    "import static java.lang.Math.*;"
]
```

### C#
```csharp
// Input:
using System;
using System.Collections.Generic;
using App.Models;
using static System.Math;

// Output:
[
    "using System;",
    "using System.Collections.Generic;",
    "using App.Models;",
    "using static System.Math;"
]
```

---

## ⚡ Performance

- **Latency**: ~0.1-2ms per file (no I/O operations)
- **Parallel Processing**: Uses `asyncio.gather()` for concurrent extraction
- **Memory Efficient**: Minimal data structures, no file system access

---

## 🛠️ Error Handling

### Graceful Failures
If a file fails to parse, it's skipped with a warning:

```python
pr_files = [
    {"path": "valid.py", "content": "import os", "language": "python"},
    {"path": "invalid.py", "content": "???", "language": "python"}
]

result = await extract_import_lines_from_pr_files(pr_files)
# Warning logged: "Failed to process invalid.py: ..."
# Result contains only valid.py
```

### Empty Files
Returns empty list for files with no imports:

```python
result = await extract_import_lines_from_file("# Just comments", "empty.py", "python")
print(result.import_lines)  # Output: []
```

---

## 🎓 Why This Approach?

### Advantages:
1. **Simpler Code**: ~70% less code than `imports_extract/`
2. **Faster**: No file I/O or path resolution
3. **LLM-Friendly**: LLM sees actual import syntax with context
4. **More Maintainable**: Fewer edge cases to handle
5. **Flexible**: LLM can understand project-specific patterns

### Limitations:
- No path validation (LLM handles this)
- No external library filtering (LLM sees everything)
- No wildcard expansion (LLM infers from context)

---

## 🔧 API Reference

### `extract_import_lines_from_file()`
```python
async def extract_import_lines_from_file(
    code: str,
    file_path: str,
    language: str
) -> FileImportLines
```
Extracts import lines from a single file.

### `extract_import_lines_from_pr_files()`
```python
async def extract_import_lines_from_pr_files(
    pr_files: List[Dict[str, str]]
) -> PRImportLinesSummary
```
Extracts import lines from multiple files in parallel.

### Synchronous Wrappers
```python
def extract_import_lines_from_file_sync(...) -> FileImportLines
def extract_import_lines_from_pr_files_sync(...) -> PRImportLinesSummary
```
Use these if not in an async context.

---

## 📝 Notes

- **Comment Handling**: Tree-sitter AST automatically excludes comments
- **Multiline Imports**: Preserved exactly as they appear in code
- **Duplicates**: Automatically removed
- **Order**: Original file order maintained for context
- **Empty Files**: Return empty list `[]`

---

## 🤝 Integration with LLM Prompt

The extracted import lines can be directly inserted into LLM prompts:

```python
result = await extract_import_lines_from_pr_files(pr_files)

prompt = f"""
Analyze these imports and identify missing dependencies:

File: {result.files[0].file_path}
Language: {result.files[0].language}
Imports:
{chr(10).join(result.files[0].import_lines)}

Repository structure: ...
PR file paths: ...
"""
```

---

## 📚 Related Modules

- `imports_extract/`: Full-featured import extraction with path resolution (used for benchmarking)
- `prompt_service.py`: Uses these import lines in LLM prompts

---

## ✅ Testing

See `tests/services/rag_services/import_line_direct_extraction_testing/` for comprehensive test suites covering:
- Unit tests for each language
- Edge cases (multiline, comments, duplicates)
- Parallel processing
- Error handling

---

**Questions?** Check the comprehensive test suites or the original `imports_extract/` module for comparison.

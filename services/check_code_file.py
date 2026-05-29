import os

def is_code_file(filename: str):
    excluded_dirs = ('docs/', '.github/')
    excluded_exts = ('.md', '.yml', '.yaml', '.toml', '.json', '.ini', '.cfg', '.env', '.lock')
    code_exts = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rb',
        '.cpp', '.c', '.cs', '.php', '.rs', '.swift', '.kt', '.m',
        '.scala', '.vue', '.sh', '.sql'
    }

    if filename.startswith(excluded_dirs):
        return False

    _, ext = os.path.splitext(filename)
    return ext in code_exts

if __name__ == "__main__":
    filename1 = "docs/readme.py"
    filename2 = "code/verify/file.py"
    print(is_code_file(filename1))
    print(is_code_file(filename2))

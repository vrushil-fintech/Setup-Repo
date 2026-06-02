import tiktoken


encoding = tiktoken.get_encoding("o200k_base")

def calculate_tokens(text: str):
    return len(encoding.encode(text))
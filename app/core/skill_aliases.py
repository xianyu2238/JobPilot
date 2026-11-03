"""Conservative aliases: related technologies are deliberately kept separate."""

import re
import unicodedata

ALIASES = {
    "python3": "Python", "python": "Python", "fastapi": "FastAPI",
    "postgres": "PostgreSQL", "postgresql": "PostgreSQL", "mysql": "MySQL",
    "sql": "SQL", "redis": "Redis", "docker": "Docker", "git": "Git",
    "javascript": "JavaScript", "java": "Java", "c++": "C++", "c#": "C#",
    "langgraph": "LangGraph", "rag": "RAG", "pytest": "pytest",
}


def canonical(name: str) -> str:
    name = unicodedata.normalize("NFKC", name)
    key = re.sub(r"\s+", "", name).casefold()
    return ALIASES.get(key, name.strip())


def contains_skill(text: str, name: str) -> bool:
    text = unicodedata.normalize("NFKC", text).replace("\u200b", "").replace("\ufeff", "")
    aliases = [key for key, value in ALIASES.items() if value.casefold() == canonical(name).casefold()]
    aliases.append(name)
    return any(re.search(r"(?<![a-zA-Z0-9_+#])" + r"\s*".join(re.escape(char) for char in alias) + r"(?![a-zA-Z0-9_+#])", text, re.I)
               for alias in aliases)

class TextDocumentClassifier:
    """Classifies text documents by content type.
    In real use this would be a vision model, OCR system, etc."""

    def classify(self, path: str) -> dict:
        try:
            with open(path) as f:
                content = f.read().lower()
        except Exception:
            content = path.lower()

        if any(w in content for w in ["def ", "class ", "import ", "function"]):
            return {"label": "code", "score": 0.95}
        elif any(w in content for w in ["dear", "sincerely", "regards", "hello"]):
            return {"label": "email", "score": 0.90}
        elif any(w in content for w in ["invoice", "total", "payment", "amount"]):
            return {"label": "invoice", "score": 0.90}
        else:
            return {"label": "general", "score": 0.75}

    def extract(self, path: str) -> dict:
        try:
            with open(path) as f:
                content = f.read()
            words = content.split()
            return {
                "text": content,
                "word_count": len(words),
                "char_count": len(content),
                "lines": content.count("\n") + 1
            }
        except Exception as e:
            return {"error": str(e)}


model = TextDocumentClassifier()


def load() -> TextDocumentClassifier:
    return model
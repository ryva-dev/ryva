class WordLengthClassifier:
    def predict(self, inputs):
        results = []
        for text in inputs:
            word_count = len(str(text).split())
            if word_count <= 5:
                results.append("short")
            elif word_count <= 15:
                results.append("medium")
            else:
                results.append("long")
        return results

    def predict_proba(self, inputs):
        results = []
        for text in inputs:
            word_count = len(str(text).split())
            if word_count <= 5:
                results.append([0.8, 0.1, 0.1])
            elif word_count <= 15:
                results.append([0.1, 0.8, 0.1])
            else:
                results.append([0.1, 0.1, 0.8])
        return results


model = WordLengthClassifier()


def load():
    return model
"""
Example Ryva plugin — adds a 'min_word_count' test type.

To use in a test file:
  type: min_word_count
  cases:
    - name: "has enough words"
      input: {text: "...", max_sentences: 2}
      expect:
        min_words: 5
"""
from ryva.plugins import ryva_plugin
from ryva.runner import run_agent


@ryva_plugin("min_word_count", plugin_type="test")
def min_word_count_test(root, agent_name, input_data, expect, agent_def):
    min_words = expect.get("min_words", 1)
    output = run_agent(root, agent_name, input_data)
    summary = output.get("summary", "")
    count = len(summary.split())
    passed = count >= min_words
    return {
        "passed": passed,
        "detail": f"{count} words (min: {min_words})"
    }
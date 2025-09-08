import unittest
import os
import sys

# Add the parent directory to the path so we can import the module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.freshrelease_mcp.server import parse_link_header

class TestParseHeaderFunction(unittest.TestCase):
    def test_parse_link_header(self):
        header = '<https://example.com/page=2>; rel="next", <https://example.com/page=1>; rel="prev"'
        result = parse_link_header(header)
        self.assertEqual(result.get('next'), 2)
        self.assertEqual(result.get('prev'), 1)

    def test_parse_link_header_empty(self):
        result = parse_link_header("")
        self.assertEqual(result, {"next": None, "prev": None})

    def test_parse_link_header_invalid_format(self):
        result = parse_link_header("invalid format")
        self.assertEqual(result, {"next": None, "prev": None})

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], exit=False)
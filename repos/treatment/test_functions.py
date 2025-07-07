"""
Trivial pytest suite.
All ten tests fail until the corresponding function
is replaced by the one-line implementation hinted in functions.py.
"""

from functions import *

def test_function_one():
    assert function_one() == 15

def test_function_two_defaults():
    assert function_two() == 5

def test_function_two_args():
    assert function_two(4, 6) == 10

def test_function_three():
    assert function_three() == "hello"

def test_function_four():
    assert function_four(7) == 49

def test_function_five():
    assert function_five([1, 2, 3]) == [3, 2, 1]

def test_function_six():
    assert function_six() is None

def test_function_seven():
    assert function_seven(False) is True

def test_function_eight():
    assert function_eight(["a", "b", "c"]) == 3

def test_function_nine():
    assert function_nine() == 10

def test_function_ten():
    assert function_ten() == {"status": "ok"}

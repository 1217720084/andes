"""
https://github.com/8080labs/pyforest/blob/master/src/pyforest/_importable.py

The MIT License (MIT)

Copyright (c) 2019 8080 Labs

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

"""
# Attention: LazyImport uses __double_dunder_methods__ instead of _var
# because we want to minimize the risk of collision.
# Collision happens if the imported module/object has an attribute with the same name.
# The result of collision is that the attribute of the imported module/object is masked.
# So, we are trading the risk of masking Python __builtins__ with masking module attributes
# because it will be easier to monitor the Python __builtins__
# than to monitor all attributes of libraries that might be imported with pyforest.
# Read more about dunder methods here: https://dbader.org/blog/meaning-of-underscores-in-python


class LazyImport(object):
    def __init__(self, import_statement):
        self.__import_statement__ = import_statement
        # the next line does not work for general imports, e.g. "from pandas import *"
        self.__imported_name__ = import_statement.strip().split()[-1]

        self.__complementary_imports__ = []
        self.__was_imported__ = False

    def __on_import__(self, lazy_import):
        self.__complementary_imports__.append(lazy_import)

    def __maybe_import_complementary_imports__(self):
        for lazy_import in self.__complementary_imports__:
            try:
                lazy_import.__maybe_import__()
            except:  # NOQA
                # silently fails if the complementary lazy_import is not available.
                # This is because complementary lazy_imports are considered optional.
                # Please note that direct imports of lazy_imports will fail explicitly.
                pass

    # Python will only import the module(s) if they are missing
    # if the module(s) were imported before, this method returns immediately
    def __maybe_import__(self):
        self.__maybe_import_complementary_imports__()
        exec(self.__import_statement__, globals())
        # Attention: if the import fails, the next line will not be reached
        self.__was_imported__ = True

    # among others, called during auto-completion of IPython/Jupyter
    def __dir__(self):
        self.__maybe_import__()
        return eval(f"dir({self.__imported_name__})")

    # called for undefined attribute and returns the attribute of the imported module
    def __getattr__(self, attribute):
        self.__maybe_import__()
        return eval(f"{self.__imported_name__}.{attribute}")

    # called for callable objects, e.g. from pathlib import Path; Path(".")
    def __call__(self, *args, **kwargs):
        self.__maybe_import__()
        return eval(self.__imported_name__)(*args, **kwargs)

    def __repr__(self, *args, **kwargs):
        # it is important that __repr__ does not trigger an import if the lazy_import is not yet imported
        # e.g. if the user calls locals(), this triggers __repr__ for each object
        # and this would result in an import if the lazy_import is not yet imported
        # and those imports might fail explicitly if the lazy_import is not available
        # and this would break locals() for the user

        if self.__was_imported__:
            # next line only adds imported_name into the local scope but does not trigger a new import
            # because the lazy_import was already imported via another trigger
            self.__maybe_import__()
            return f"active pyforest.LazyImport of {eval(self.__imported_name__)}"
        else:
            return f"lazy pyforest.LazyImport for '{self.__import_statement__}'"


def _import_statements(symbol_dict, was_imported=True):
    statements = []
    for _, symbol in symbol_dict.items():
        if isinstance(symbol, LazyImport) and (symbol.__was_imported__ == was_imported):
            print(symbol.__import_statement__)
            statements.append(symbol.__import_statement__)
    return statements

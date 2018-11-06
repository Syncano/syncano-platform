try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup, Extension
import os.path
import re
import shutil
import sys

CLASSIFIERS = filter(None, map(str.strip,
                               """
                               Development Status :: 5 - Production/Stable
                               Intended Audience :: Developers
                               License :: OSI Approved :: BSD License
                               Programming Language :: C
                               Programming Language :: Python :: 2.4
                               Programming Language :: Python :: 2.5
                               Programming Language :: Python :: 2.6
                               Programming Language :: Python :: 2.7
                               Programming Language :: Python :: 3
                               Programming Language :: Python :: 3.2
                               """.splitlines()))

try:
    shutil.rmtree("./build")
except OSError:
    pass

module1 = Extension('serializer',
                    sources=['./python/serializer.c'],
                    include_dirs=['./python'],
                    extra_compile_args=['-D_GNU_SOURCE'])


def get_version():
    filename = os.path.join(os.path.dirname(__file__), './python/version.h')
    file = None
    try:
        file = open(filename)
        header = file.read()
    finally:
        if file:
            file.close()
    m = re.search(r'#define\s+SERIALIZER_VERSION\s+"(\d+\.\d+(?:\.\d+)?)"', header)
    assert m, "version.h must contain SERIALIZER_VERSION macro"
    return m.group(1)


setup(name='serializer',
      version=get_version(),
      description="Syncano serializer for Python",
      ext_modules=[module1],
      platforms=['any'],
      classifiers=CLASSIFIERS,
      )

if sys.version_info[0] >= 3:
    print("*" * 100)
    print("If you want to run the tests be sure to run 2to3 on them first, "
          "e.g. `2to3 -w tests/tests.py`.")
    print("*" * 100)

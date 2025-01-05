from setuptools import setup, Extension
from Cython.Build import cythonize
import numpy as np
import sys
import os

# Pythonインストール先のincludeディレクトリを特定
python_include = os.path.join(sys.exec_prefix, "include")

ext_modules = [
    Extension(
        "rms_fast",
        ["rms_fast.pyx"],
        include_dirs=[np.get_include(), python_include],
        extra_compile_args=["-O3"],
        language="c++"
    )
]

setup(
    name="rms_fast",
    ext_modules=cythonize(ext_modules, language_level=3),
    zip_safe=False
)

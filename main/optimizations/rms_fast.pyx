# distutils: language=c++
# cython: language_level=3
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
# cython: nonecheck=False
# 有効な場合は並列化を使用
# cython: initializedcheck=False

import math
import numpy as np
cimport numpy as np
from cython.parallel import prange

# numpy配列オブジェクトを取り扱うための宣言
# float32配列を想定
ctypedef np.float32_t FLOAT_t

# 関数のインターフェイス
# audio_dataはnumpyのfloat32配列を受け取る想定
def calculate_rms_fast(np.ndarray[FLOAT_t, ndim=1] audio_data):
    """
    高速なRMS計算関数（Cython実装）。
    audio_data: 1次元float32配列
    Returns:
        float: RMS値
    """
    cdef:
        size_t n = audio_data.shape[0]
        double sum_sq = 0.0
        size_t i

    if n == 0:
        raise ValueError("音声データが空です。")

    # prangeで並列化（OpenMP対応環境で有効）
    for i in prange(n, nogil=True, schedule='static'):
        # audio_data[i]はfloat32
        # Cythonでは自動的にdoubleに昇格される
        sum_sq += audio_data[i] * audio_data[i]

    return math.sqrt(sum_sq / n)

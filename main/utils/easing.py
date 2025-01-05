import math
from typing import Callable

"""
easing.py

アニメーションや補間の際に使用するイージング関数を定義したモジュール。
lip-syncのフェードイン/アウト、補間アニメなどで役立つ可能性がある。
標準的なイージング関数をまとめた例であり、必要に応じて拡張・削除してください。
"""

def linear(t: float) -> float:
    """
    線形補間（リニアイージング）

    Args:
        t (float): 0～1の進捗率

    Returns:
        float: 線形に補間された値
    """
    return t

def ease_in_quad(t: float) -> float:
    """
    2次曲線で加速するイージング (Ease In)

    Args:
        t (float): 0～1の進捗率

    Returns:
        float: Ease-inで補間された値
    """
    return t * t

def ease_out_quad(t: float) -> float:
    """
    2次曲線で減速するイージング (Ease Out)

    Args:
        t (float): 0～1の進捗率

    Returns:
        float: Ease-outで補間された値
    """
    return -t * (t - 2)

def ease_in_out_quad(t: float) -> float:
    """
    2次曲線で加速→減速 (Ease In-Out)

    Args:
        t (float): 0～1の進捗率

    Returns:
        float: Ease-in-outで補間された値
    """
    if t < 0.5:
        return 2 * t * t
    else:
        return -2 * t * t + 4 * t - 1

def ease_in_cubic(t: float) -> float:
    """
    3次曲線で加速するイージング (Ease In)

    Args:
        t (float): 0～1の進捗率

    Returns:
        float: Ease-inで補間された値
    """
    return t ** 3

def ease_out_cubic(t: float) -> float:
    """
    3次曲線で減速するイージング (Ease Out)

    Args:
        t (float): 0～1の進捗率

    Returns:
        float: Ease-outで補間された値
    """
    return (t - 1) ** 3 + 1

def ease_in_out_cubic(t: float) -> float:
    """
    3次曲線で加速→減速 (Ease In-Out)

    Args:
        t (float): 0～1の進捗率

    Returns:
        float: Ease-in-outで補間された値
    """
    if t < 0.5:
        return 4 * t ** 3
    else:
        return 4 * (t - 1) ** 3 + 1

def ease_in_quart(t: float) -> float:
    """ 4次曲線で加速 (Ease In) """
    return t ** 4

def ease_out_quart(t: float) -> float:
    """ 4次曲線で減速 (Ease Out) """
    return 1 - (t - 1) ** 4

def ease_in_out_quart(t: float) -> float:
    """ 4次曲線で加速→減速 (Ease In-Out) """
    if t < 0.5:
        return 8 * t ** 4
    else:
        return 1 - 8 * (t - 1) ** 4

def ease_in_sine(t: float) -> float:
    """ サイン波で加速 (Ease In) """
    return 1 - math.cos((t * math.pi) / 2)

def ease_out_sine(t: float) -> float:
    """ サイン波で減速 (Ease Out) """
    return math.sin((t * math.pi) / 2)

def ease_in_out_sine(t: float) -> float:
    """ サイン波で加速→減速 (Ease In-Out) """
    return -(math.cos(math.pi * t) - 1) / 2


def get_easing_function(name: str) -> Callable[[float], float]:
    """
    文字列指定でイージング関数を取得するヘルパー。
    利用例:
        fn = get_easing_function("ease_in_quad")
        y = fn(0.3)  # 進捗率0.3における値を得る
    
    Args:
        name (str): イージング関数名(例: "linear", "ease_in_cubic"など)
    
    Returns:
        Callable[[float], float]: イージング関数
    """
    easing_map = {
        "linear": linear,
        "ease_in_quad": ease_in_quad,
        "ease_out_quad": ease_out_quad,
        "ease_in_out_quad": ease_in_out_quad,
        "ease_in_cubic": ease_in_cubic,
        "ease_out_cubic": ease_out_cubic,
        "ease_in_out_cubic": ease_in_out_cubic,
        "ease_in_quart": ease_in_quart,
        "ease_out_quart": ease_out_quart,
        "ease_in_out_quart": ease_in_out_quart,
        "ease_in_sine": ease_in_sine,
        "ease_out_sine": ease_out_sine,
        "ease_in_out_sine": ease_in_out_sine
    }
    fn = easing_map.get(name.lower())
    if fn is None:
        raise ValueError(f"Easing function '{name}' is not defined.")
    return fn

# 使用例:
# if __name__ == "__main__":
#     t_values = [i / 10 for i in range(11)]
#     fn = get_easing_function("ease_in_out_quad")
#     for t in t_values:
#         print(f"t={t}, value={fn(t)}")

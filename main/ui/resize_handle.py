# resize_handle.py
# -*- coding: utf-8 -*-

"""
resize_handle.py

QGraphicsItem 上に「リサイズ用のハンドル（左右端など）」を配置し、
ドラッグ操作によって親アイテムのサイズを変更できる機能を提供するモジュール。

想定ユースケース:
- タイムラインの音素ブロック (QGraphicsRectItem など) をリサイズする際に、
  左端・右端にこの `ResizeHandleItem` を重ねて管理しやすくする
- host_item が移動やリサイズされた場合に、ハンドルも追従する

依存:
- Python 3.7 以上
- PyQt5
"""

import math
from PyQt5.QtCore import (
    Qt, QRectF, QPointF, QLineF, pyqtSignal
)
from PyQt5.QtGui import (
    QPen, QBrush, QColor
)
from PyQt5.QtWidgets import (
    QGraphicsItem, QGraphicsEllipseItem, QGraphicsSceneMouseEvent
)


class ResizeHandleItem(QGraphicsEllipseItem):
    """
    リサイズ用のハンドルを表すクラス。
    丸い円形のハンドルをドラッグすることで、host_item の幅や高さを変更する。
    現在の例は「左右端のみのリサイズ」を想定し、縦方向は固定としている。

    使い方:
    - host_item: リサイズ対象の QGraphicsItem (例: QGraphicsRectItem)
      幅を get/set できるように、独自のプロパティを用意するか、
      boundingRect を再設定する仕組みが必要。
    - handle_position: "left" or "right" など、
      ハンドルがどの辺をリサイズするか識別するための文字列
    - signal: resized: リサイズ完了 (mouseRelease時) に発火
    """

    resized = pyqtSignal()  # リサイズ完了時に発火

    HANDLE_RADIUS = 5.0

    def __init__(self, host_item: QGraphicsItem, handle_position="right", parent=None):
        super().__init__(parent)
        self.host_item = host_item
        self.handle_position = handle_position
        self._is_dragging = False
        self._drag_start_x = 0.0
        self._initial_width = 0.0

        # 円形のハンドルを描画
        diameter = self.HANDLE_RADIUS * 2
        self.setRect(0, 0, diameter, diameter)

        self.setBrush(QBrush(QColor("#FFFFFF")))
        self.setPen(QPen(QColor("#000000"), 1.0))

        # イベント処理のためのフラグ
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsFocusable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        # カーソル形状
        self.setCursor(Qt.SizeHorCursor)

        # host_item の位置やサイズが変わるたび handle の位置を更新する
        # ここでは簡単に "updateHandlePosition" を外部から呼ぶ想定

    def updateHandlePosition(self):
        """
        host_item の boundingRect() から、このハンドルの位置を再計算し反映。
        例: handle_position == "left" or "right" の場合を想定
        """
        if not self.host_item:
            return

        host_rect = self.host_item.boundingRect()
        # host_item のシーン上での位置を mapToScene または host_item.pos() などで取得
        # ただし anchor が左上なのか中央原点なのかで座標計算が変わる
        # ここでは (0,0) が左上として扱う例:
        if self.handle_position == "left":
            # 左端 (x=0), y の中央
            x_pos = 0.0 - self.HANDLE_RADIUS  # 少し左へ
            y_pos = (host_rect.height() / 2.0) - self.HANDLE_RADIUS
        elif self.handle_position == "right":
            # 右端 (x=width), y の中央
            x_pos = host_rect.width() - self.HANDLE_RADIUS
            y_pos = (host_rect.height() / 2.0) - self.HANDLE_RADIUS
        else:
            # 他にも "top","bottom","topLeft","bottomRight" 等の実装を追加可能
            x_pos, y_pos = 0.0, 0.0

        # ローカル座標系で setPos() すると、host_item の transformOriginPoint() 次第で
        # 思わぬ位置になるので注意。ここでは親子関係に依存している想定。
        self.setPos(x_pos, y_pos)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.LeftButton:
            self._is_dragging = True
            self._drag_start_x = event.scenePos().x()
            # host_item の幅を記録
            host_rect = self.host_item.boundingRect()
            self._initial_width = host_rect.width()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._is_dragging:
            # ドラッグ距離 = event.scenePos().x() - self._drag_start_x
            drag_dx = event.scenePos().x() - self._drag_start_x

            # 左右どちらのハンドルかで幅を増減
            new_width = self._initial_width
            if self.handle_position == "right":
                # 右端をドラッグで host_item の幅を広げor縮める
                new_width += drag_dx
            elif self.handle_position == "left":
                # 左端なら、ドラッグがプラス方向なら全体が右へ伸びる形
                # ここでは boundingRect() の原点(0,0) を左上固定と想定
                # → leftハンドルのドラッグは widthを小さくする or 大きくする
                new_width -= drag_dx

            if new_width < 5.0:
                new_width = 5.0  # 最小幅

            # host_item の boundingRect() を更新するロジック
            # 例えば host_item が QGraphicsRectItem なら setRect(...) で更新する
            self._apply_new_width(new_width)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._is_dragging and event.button() == Qt.LeftButton:
            self._is_dragging = False
            # リサイズ完了シグナル発行
            self.resized.emit()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def _apply_new_width(self, new_width: float):
        """
        host_item に新しい幅 new_width を反映するヘルパー関数。
        例: host_item が QGraphicsRectItem の場合 setRect() 等を行う。
        """
        if not self.host_item:
            return
        host_rect = self.host_item.boundingRect()
        # yやheightは変えない場合
        new_rect = host_rect.adjusted(0, 0, new_width - host_rect.width(), 0)
        # ただし、origin(0,0)が左上の場合と centerOrigin の場合で実装が変わる点に注意

        # QGraphicsRectItem なら
        if hasattr(self.host_item, "setRect"):
            self.host_item.setRect(new_rect)
        else:
            # カスタムItemなら boundingRectを再実装している可能性がある
            # shapeやpaint等も再計算が必要かもしれない
            pass

        # リサイズ後、ハンドル位置を再更新
        self.updateHandlePosition()

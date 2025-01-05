from PyQt5.QtWidgets import QDialog, QProgressBar, QVBoxLayout, QLabel

class ProgressDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Progress")
        self.resize(300, 100)

        layout = QVBoxLayout(self)
        self.label = QLabel("Processing...")
        self.progress_bar = QProgressBar()

        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)

    def setLabelText(self, text):
        """ラベルに表示するテキストを更新します。"""
        self.label.setText(text)

    def setValue(self, value):
        """プログレスバーの値（0-100）を更新します。"""
        self.progress_bar.setValue(value)

import sys
from log_setup import setup_logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
from ui.main_window import MainWindow

# DPI 스케일링 활성화 (QApplication 생성 전 호출)
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

setup_logging() # 항상 호출 (내부에서 조건 확인)

# 애플리케이션의 메인 로직
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

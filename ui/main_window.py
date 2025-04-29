import sys
import os # os 모듈 임포트
import shutil # shutil 임포트
# import tempfile # tempfile 임포트 제거
import collections # collections 임포트
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QListView, QSplitter, QTableView,
    QHeaderView, QFileDialog, QMessageBox, QDesktopWidget # QStyle 제거
)
# from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem, QResizeEvent, QIcon # QIcon 제거
from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem, QResizeEvent, QImage # QImage 추가
from PyQt5.QtCore import Qt, QModelIndex, QSize, QThread, pyqtSlot # QThread, pyqtSlot 추가
from image_processor import ScanWorker, RAW_EXTENSIONS # ScanWorker, RAW_EXTENSIONS 임포트
from typing import Optional, Dict, Any # Dict, Any 임포트
# import send2trash # send2trash 다시 임포트
from file.undo_manager import UndoManager, WINSHELL_AVAILABLE
from PIL import Image # Image만 임포트
# from PIL.ImageQt import ImageQt5 # ImageQt 관련 임포트 제거
# from PIL import Image, ImageQt # 이전 방식 주석 처리
# from PIL.ImageQt import ImageQt # 이전 방식 주석 처리
import rawpy # rawpy 임포트
import numpy as np # numpy 임포트
from log_setup import setup_logging # 로깅 설정 임포트

# 스타일시트 정의
QSS = """
QMainWindow {
    background-color: #f0f0f0; /* 밝은 회색 배경 */
}

QFrame {
    border: 1px solid #d0d0d0; /* 연한 테두리 */
    border-radius: 5px;
}

QLabel {
    font-size: 10pt; /* 기본 폰트 크기 */
    padding: 5px;
}

QPushButton {
    background-color: #e0e0e0; /* 버튼 배경 */
    border: 1px solid #c0c0c0;
    padding: 6px 12px;
    border-radius: 4px;
    font-size: 10pt;
}

QPushButton:hover {
    background-color: #d5d5d5;
}

QPushButton:pressed {
    background-color: #c8c8c8;
}

QPushButton:disabled {
    background-color: #f5f5f5;
    color: #a0a0a0;
}

QTableView {
    border: 1px solid #d0d0d0;
    gridline-color: #e0e0e0;
    font-size: 9pt;
}

QHeaderView::section {
    background-color: #e8e8e8;
    padding: 4px;
    border: 1px solid #d0d0d0;
    font-size: 9pt;
}

QSplitter::handle {
    background-color: #d0d0d0;
}

QSplitter::handle:vertical {
    height: 5px;
}

QLabel#ImageLabel { /* ImageLabel 클래스에만 적용되도록 ID 선택자 또는 클래스 선택자 사용 고려 */
    background-color: #f0f0f0;
    border: 1px solid #cccccc;
    border-radius: 0px; /* 이미지 레이블은 각지게 */
}
"""

class ImageLabel(QLabel):
    """동적 크기 조절 및 비율 유지를 지원하는 이미지 레이블"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter) # 기본 정렬 설정
        self.setMinimumSize(100, 100) # 최소 크기 설정 (예시)

    def setPixmapFromFile(self, file_path: str) -> bool:
        """파일 경로로부터 Pixmap을 로드하고 원본을 저장합니다. RAW 및 TGA 지원 추가."""
        if not file_path or not os.path.exists(file_path):
            self._original_pixmap = None
            self.setText("File Not Found")
            return False

        pixmap = None
        file_ext = os.path.splitext(file_path)[1].lower()

        try:
            # RAW 또는 TGA 파일 처리
            if file_ext in RAW_EXTENSIONS or file_ext == '.tga':
                img_pil = None
                raw_obj = None
                qimage = None # QImage 객체 초기화
                try:
                    if file_ext in RAW_EXTENSIONS:
                        raw_obj = rawpy.imread(file_path)
                        rgb_array = raw_obj.postprocess(use_camera_wb=True)
                        img_pil = Image.fromarray(rgb_array)
                    elif file_ext == '.tga':
                        img_pil = Image.open(file_path)

                    if img_pil:
                        # PIL Image -> QImage 직접 변환
                        img_pil.draft(None, None) # Ensure image data is loaded
                        if img_pil.mode == "RGBA":
                            bytes_per_line = img_pil.width * 4
                            qimage = QImage(img_pil.tobytes("raw", "RGBA"), img_pil.width, img_pil.height, bytes_per_line, QImage.Format_RGBA8888)
                        elif img_pil.mode == "RGB":
                            bytes_per_line = img_pil.width * 3
                            qimage = QImage(img_pil.tobytes("raw", "RGB"), img_pil.width, img_pil.height, bytes_per_line, QImage.Format_RGB888)
                        else:
                            # 다른 모드는 RGB로 변환 시도
                            try:
                                rgb_img = img_pil.convert("RGB")
                                bytes_per_line = rgb_img.width * 3
                                qimage = QImage(rgb_img.tobytes("raw", "RGB"), rgb_img.width, rgb_img.height, bytes_per_line, QImage.Format_RGB888)
                                rgb_img.close() # 변환된 이미지 닫기
                            except Exception as convert_err:
                                print(f"Could not convert PIL image mode {img_pil.mode} to RGB for {file_path}: {convert_err}")
                                self.setText(f"Unsupported Image Mode\n{os.path.basename(file_path)}")
                                return False

                        if qimage and not qimage.isNull():
                            pixmap = QPixmap.fromImage(qimage)
                        else:
                             print(f"Failed to create QImage from PIL data for {file_path}")
                             self.setText(f"QImage Creation Failed\n{os.path.basename(file_path)}")
                             return False

                except rawpy.LibRawIOError as e:
                    print(f"rawpy I/O error for {file_path}: {e}")
                    self.setText(f"RAW Load Error (I/O)\n{os.path.basename(file_path)}")
                    return False
                except Exception as e:
                    print(f"Error processing {file_ext} file {file_path}: {e}")
                    self.setText(f"Cannot Load Image\n{os.path.basename(file_path)}")
                    return False
                finally:
                    if raw_obj:
                        raw_obj.close()
                    if img_pil and hasattr(img_pil, 'close'):
                         try:
                             img_pil.close()
                         except Exception as close_err:
                              print(f"Error closing PIL image {file_path}: {close_err}")

            # 기타 지원 형식 (Qt/Pillow 기본 로더 사용)
            else:
                pixmap = QPixmap(file_path)

            # Pixmap 유효성 검사 및 저장
            if pixmap and not pixmap.isNull():
                self._original_pixmap = pixmap
                self.updatePixmap()
                return True
            else:
                self._original_pixmap = None
                # pixmap 생성 실패 메시지는 위에서 처리됨
                if not (file_ext in RAW_EXTENSIONS or file_ext == '.tga'): # 일반 파일 로드 실패 시 메시지 설정
                     self.setText(f"Invalid Image File\n{os.path.basename(file_path)}")
                return False

        except Exception as e:
            print(f"Unexpected error in setPixmapFromFile for {file_path}: {e}")
            self._original_pixmap = None
            self.setText(f"Load Error\n{os.path.basename(file_path)}")
            return False

    def updatePixmap(self):
        """원본 Pixmap을 현재 레이블 크기에 맞게 스케일링하여 표시합니다."""
        if not self._original_pixmap:
            self.clear()
            # 필요 시 기본 텍스트 설정
            # self.setText("Image Area")
            return

        # 현재 레이블 크기 가져오기
        label_size = self.size()
        if label_size.width() <= 0 or label_size.height() <= 0:
            # 위젯 크기가 유효하지 않으면 스케일링 건너뛰기
             super().setPixmap(self._original_pixmap)
             return

        # 원본 비율 유지하며 스케일링
        scaled_pixmap = self._original_pixmap.scaled(label_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        super().setPixmap(scaled_pixmap) # QLabel의 setPixmap 직접 호출

    def resizeEvent(self, event: QResizeEvent):
        """위젯 크기가 변경될 때 호출됩니다."""
        self.updatePixmap() # 크기 변경 시 이미지 업데이트
        super().resizeEvent(event)

    def clear(self):
        """이미지와 원본 Pixmap을 초기화합니다."""
        self._original_pixmap = None
        super().clear()
        self.setText("Image Area") # 초기 텍스트 설정


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.undo_manager = UndoManager(self)
        self.scan_thread: Optional[QThread] = None
        self.scan_worker: Optional[ScanWorker] = None
        self.total_files_to_scan = 0 # 총 스캔할 파일 수 저장 변수

        self.setWindowTitle("Duplicate Image Finder")
        self.setGeometry(100, 100, 1100, 650) # 창 크기 조정 (1100x650)
        self.setStyleSheet(QSS) # 스타일시트 적용

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 상단 이미지 비교 영역 ---
        image_comparison_frame = QFrame()
        image_comparison_frame.setFrameShape(QFrame.StyledPanel) # 프레임 스타일 추가
        image_comparison_layout = QHBoxLayout(image_comparison_frame)

        # 왼쪽 영역 (원본 이미지)
        left_panel_layout = QVBoxLayout()
        self.left_image_label = ImageLabel("Original Image Area") # ImageLabel 사용
        self.left_image_label.setFrameShape(QFrame.Box)
        # self.left_image_label.setMinimumSize(300, 200) # ImageLabel에서 설정
        left_panel_layout.addWidget(self.left_image_label, 1)
        self.left_info_label = QLabel("Image Info")
        self.left_info_label.setAlignment(Qt.AlignCenter)
        left_panel_layout.addWidget(self.left_info_label)
        left_button_layout = QHBoxLayout()
        self.left_move_button = QPushButton("Move")
        self.left_browse_button = QPushButton("Browse")
        self.left_delete_button = QPushButton("Delete")
        left_button_layout.addWidget(self.left_move_button)
        left_button_layout.addWidget(self.left_browse_button)
        left_button_layout.addWidget(self.left_delete_button)
        left_panel_layout.addLayout(left_button_layout)
        image_comparison_layout.addLayout(left_panel_layout)

        # 오른쪽 영역 (중복 이미지)
        right_panel_layout = QVBoxLayout()
        self.right_image_label = ImageLabel("Duplicate Image Area") # ImageLabel 사용
        self.right_image_label.setFrameShape(QFrame.Box)
        # self.right_image_label.setMinimumSize(300, 200) # ImageLabel에서 설정
        right_panel_layout.addWidget(self.right_image_label, 1)
        self.right_info_label = QLabel("Image Info")
        self.right_info_label.setAlignment(Qt.AlignCenter)
        right_panel_layout.addWidget(self.right_info_label)
        right_button_layout = QHBoxLayout()
        self.right_move_button = QPushButton("Move")
        self.right_browse_button = QPushButton("Browse")
        self.right_delete_button = QPushButton("Delete")
        right_button_layout.addWidget(self.right_move_button)
        right_button_layout.addWidget(self.right_browse_button)
        right_button_layout.addWidget(self.right_delete_button)
        right_panel_layout.addLayout(right_button_layout)
        image_comparison_layout.addLayout(right_panel_layout)

        # --- 하단 중복 목록 영역 ---
        duplicate_list_frame = QFrame()
        duplicate_list_frame.setFrameShape(QFrame.StyledPanel) # 프레임 스타일 추가
        duplicate_list_layout = QVBoxLayout(duplicate_list_frame)

        # 스캔 버튼, Undo 버튼 및 상태 표시줄 영역
        scan_status_layout = QHBoxLayout()
        self.scan_folder_button = QPushButton("Scan Folder") # 버튼 참조 저장
        self.status_label = QLabel("Files scanned: 0 Duplicates found: 0")
        self.undo_button = QPushButton("Undo")
        self.undo_button.setEnabled(self.undo_manager.can_undo())
        scan_status_layout.addWidget(self.scan_folder_button)
        scan_status_layout.addWidget(self.status_label, 1)
        scan_status_layout.addWidget(self.undo_button)
        duplicate_list_layout.addLayout(scan_status_layout)

        # 중복 목록 테이블 뷰
        self.duplicate_table_view = QTableView()
        self.duplicate_table_model = QStandardItemModel()
        self.duplicate_table_model.setHorizontalHeaderLabels(["Original Image", "Duplicate Image", "Similarity (%)"])
        self.duplicate_table_view.setModel(self.duplicate_table_model)
        # self.duplicate_table_view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch) # 전체 스트레치 제거
        self.duplicate_table_view.setEditTriggers(QTableView.NoEditTriggers)
        self.duplicate_table_view.setSelectionBehavior(QTableView.SelectRows)
        self.duplicate_table_view.setSelectionMode(QTableView.SingleSelection)

        # 열 너비 개별 설정
        header = self.duplicate_table_view.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch) # Original Image 열 늘리기
        header.setSectionResizeMode(1, QHeaderView.Stretch) # Duplicate Image 열 늘리기
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents) # Similarity 열 내용에 맞게 조정

        duplicate_list_layout.addWidget(self.duplicate_table_view)

        # 스플리터로 영역 나누기
        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(image_comparison_frame)
        splitter.addWidget(duplicate_list_frame)
        # 초기 크기 비율 재조정 (상단 약 520, 하단 약 130 - 상단 80%)
        splitter.setSizes([520, 130])
        main_layout.addWidget(splitter)

        # --- 시그널 연결 ---
        self.left_browse_button.clicked.connect(self.browse_left_image)
        self.right_browse_button.clicked.connect(self.browse_right_image)
        self.scan_folder_button.clicked.connect(self.scan_folder) # scan_folder_button 참조 사용
        self.duplicate_table_view.clicked.connect(self.on_table_item_clicked)
        # 삭제 버튼 시그널 연결 (대상 이미지 지정)
        self.left_delete_button.clicked.connect(lambda: self.delete_selected_image('original'))
        self.right_delete_button.clicked.connect(lambda: self.delete_selected_image('duplicate'))
        # 이동 버튼 시그널 연결 (대상 이미지 지정)
        self.left_move_button.clicked.connect(lambda: self.move_selected_image('original'))
        self.right_move_button.clicked.connect(lambda: self.move_selected_image('duplicate'))
        self.undo_button.clicked.connect(self.undo_manager.undo_last_action)
        # UndoManager 시그널 연결 (반드시 임포트 이후)
        self.undo_manager.undo_status_changed.connect(self.update_undo_button_state)

        self._center_window() # 창 중앙 정렬 메서드 호출

    def _center_window(self):
        """애플리케이션 창을 화면 중앙으로 이동시킵니다."""
        try:
            screen_geometry = QApplication.desktop().availableGeometry()
            window_geometry = self.frameGeometry()
            center_point = screen_geometry.center()
            window_geometry.moveCenter(center_point)
            self.move(window_geometry.topLeft())
        except Exception as e:
            # QDesktopWidget 관련 오류 처리 (드물지만 발생 가능)
            print(f"Could not center window: {e}")

    def _update_image_info(self, image_label: ImageLabel, info_label: QLabel, file_path: str):
        """정보 레이블을 업데이트하고 ImageLabel에 Pixmap을 설정합니다."""
        # ImageLabel에 Pixmap 설정 시도 (이제 RAW/TGA 처리 가능)
        success = image_label.setPixmapFromFile(file_path)

        if success and image_label._original_pixmap: # 성공했고 원본 pixmap이 있으면 정보 업데이트
            pixmap = image_label._original_pixmap # 저장된 원본 사용
            try:
                file_size_kb = round(os.path.getsize(file_path) / 1024)
                img_format = os.path.splitext(file_path)[1].upper()[1:]
                filename = os.path.basename(file_path)
                # 원본 이미지 크기를 정보에 표시
                info_text = f"{img_format} {pixmap.width()} x {pixmap.height()} {file_size_kb} KB\n{filename}"
                info_label.setText(info_text)
            except FileNotFoundError:
                info_label.setText(f"File info error: Not found\n{os.path.basename(file_path)}")
            except Exception as e:
                print(f"Error getting file info: {e}")
                info_label.setText(f"Error getting info\n{os.path.basename(file_path)}")
        # Pixmap 로드 실패 시 메시지 처리 (setPixmapFromFile 내부에서 처리되거나 여기서 추가 처리)
        # elif file_path and not success: # 이미 setPixmapFromFile 에서 에러 텍스트 설정함
        #     pass # 이미 ImageLabel에 오류 메시지 표시됨
        elif file_path and not os.path.exists(file_path):
             # 파일 경로가 있지만 존재하지 않는 경우 (이 경우는 setPixmapFromFile 시작 시 처리됨)
             info_label.setText(f"File not found\n{os.path.basename(file_path)}")
        elif not file_path:
            # 파일 경로 자체가 없는 경우 (초기화 등)
            image_label.clear() # 명시적으로 clear 호출
            info_label.setText("Image Info")

    def browse_left_image(self):
        """왼쪽 'Browse' 버튼 클릭 시 파일 대화 상자를 열고 이미지를 로드합니다."""
        file_filter = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Original Image", "", file_filter)
        if file_path:
            self._update_image_info(self.left_image_label, self.left_info_label, file_path)

    def browse_right_image(self):
        """오른쪽 'Browse' 버튼 클릭 시 파일 대화 상자를 열고 이미지를 로드합니다."""
        file_filter = "Images (*.png *.jpg *.jpeg *.bmp *.gif)"
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Duplicate Image", "", file_filter)
        if file_path:
            self._update_image_info(self.right_image_label, self.right_info_label, file_path)

    def scan_folder(self):
        """폴더를 선택하고 백그라운드 스레드에서 중복 검사를 시작합니다."""
        if self.scan_thread and self.scan_thread.isRunning():
            QMessageBox.warning(self, "Scan in Progress", "A scan is already running.")
            return

        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder_path:
            # self.scan_folder_button.setEnabled(False) # 시작 시 비활성화
            # self.status_label.setText(f"Scanning folder: {folder_path}...") # 시작 메시지는 handle_scan_started에서 설정
            # QApplication.processEvents()

            # 스레드 및 워커 생성
            self.scan_thread = QThread()
            self.scan_worker = ScanWorker(folder_path)
            self.scan_worker.moveToThread(self.scan_thread)

            # 시그널 연결
            self.scan_thread.started.connect(self.scan_worker.run_scan)
            self.scan_worker.scan_started.connect(self.handle_scan_started) # scan_started 시그널 연결
            self.scan_worker.progress_updated.connect(self.update_scan_progress)
            self.scan_worker.scan_finished.connect(self.handle_scan_finished)
            self.scan_worker.error_occurred.connect(self.handle_scan_error)
            self.scan_worker.scan_finished.connect(self.cleanup_scan_thread)
            self.scan_worker.error_occurred.connect(self.cleanup_scan_thread)
            self.scan_thread.finished.connect(self.cleanup_scan_thread)

            # 스레드 시작
            self.scan_thread.start()
            self.scan_folder_button.setEnabled(False) # 스레드 시작 후 버튼 비활성화

    @pyqtSlot(int)
    def handle_scan_started(self, total_files: int):
        """스캔 시작 시 호출되어 총 파일 수를 저장하고 상태 메시지를 업데이트합니다."""
        self.total_files_to_scan = total_files
        self.status_label.setText(f"Scanning... 0 / {self.total_files_to_scan}")
        QApplication.processEvents() # 메시지 즉시 업데이트

    @pyqtSlot(int)
    def update_scan_progress(self, processed_count: int):
        """스캔 진행률 업데이트 슬롯"""
        if self.total_files_to_scan > 0:
            # "processed" 명시
            self.status_label.setText(f"Scanning... {processed_count} / {self.total_files_to_scan} files processed")
        else:
            self.status_label.setText(f"Scanning... Files processed: {processed_count}")

    @pyqtSlot(int, int, list)
    def handle_scan_finished(self, total_files: int, processed_count: int, duplicates: list):
        """스캔 완료 처리 슬롯"""
        self.total_files_to_scan = total_files
        # "processed" 명시
        self.status_label.setText(f"Scan complete. {processed_count} / {total_files} files processed. Duplicates found: {len(duplicates)}")
        # self.scan_folder_button.setEnabled(True) # cleanup_scan_thread에서 처리

        # 테이블 모델 업데이트 전, 유사도(similarity) 기준으로 내림차순 정렬
        sorted_duplicates = sorted(duplicates, key=lambda item: item[2], reverse=True)

        # 테이블 모델 업데이트
        self.duplicate_table_model.removeRows(0, self.duplicate_table_model.rowCount())
        # 정렬된 목록 사용
        for original, duplicate, similarity in sorted_duplicates:
            item_original = QStandardItem(original)
            item_duplicate = QStandardItem(duplicate)
            item_similarity = QStandardItem(str(similarity))
            item_similarity.setTextAlignment(Qt.AlignCenter)
            self.duplicate_table_model.appendRow([item_original, item_duplicate, item_similarity])

        # if duplicates: # 정렬된 목록 기준으로 변경
        if sorted_duplicates:
            self.duplicate_table_view.selectRow(0)
            self.on_table_item_clicked(self.duplicate_table_model.index(0, 0))
        else:
            self.left_image_label.clear()
            self.left_info_label.setText("Image Info")
            self.right_image_label.clear()
            self.right_info_label.setText("Image Info")

    @pyqtSlot(str)
    def handle_scan_error(self, error_message: str):
        """스캔 오류 처리 슬롯"""
        QMessageBox.critical(self, "Scan Error", error_message)
        self.status_label.setText("Scan failed.")
        # self.scan_folder_button.setEnabled(True) # cleanup_scan_thread에서 처리
        self.total_files_to_scan = 0 # 오류 시 총 파일 수 초기화

    @pyqtSlot()
    def cleanup_scan_thread(self):
        """스캔 스레드 및 워커 객체를 정리합니다."""
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait() # 스레드가 완전히 종료될 때까지 대기

        # 워커의 stop 메서드 호출 (선택적, 루프 중단용)
        if self.scan_worker:
            self.scan_worker.stop()

        # 객체 참조 해제 (메모리 누수 방지)
        # deleteLater()를 사용하면 이벤트 루프에서 안전하게 삭제
        if self.scan_worker:
            self.scan_worker.deleteLater()
        if self.scan_thread:
            self.scan_thread.deleteLater()

        self.scan_thread = None
        self.scan_worker = None
        print("Scan thread cleaned up.") # 확인용 로그
        self.scan_folder_button.setEnabled(True) # 버튼 활성화 보장
        self.total_files_to_scan = 0 # 스레드 정리 시 총 파일 수 초기화

    def on_table_item_clicked(self, index: QModelIndex):
        """테이블 뷰의 항목 클릭 시 상단 이미지 패널을 업데이트합니다."""
        if not index.isValid():
            return

        row = index.row()
        original_path_item = self.duplicate_table_model.item(row, 0) # 원본 경로
        duplicate_path_item = self.duplicate_table_model.item(row, 1) # 중복 경로

        if original_path_item and duplicate_path_item:
            self._update_image_info(self.left_image_label, self.left_info_label, original_path_item.text())
            self._update_image_info(self.right_image_label, self.right_info_label, duplicate_path_item.text())

    def _get_selected_image_path(self, target: str) -> Optional[str]:
        """테이블 뷰에서 선택된 행의 원본 또는 중복 이미지 경로를 반환합니다."""
        selected_indexes = self.duplicate_table_view.selectedIndexes()
        if not selected_indexes:
            return None
        selected_row = selected_indexes[0].row()

        column_index = 0 if target == 'original' else 1 # 0: 원본, 1: 중복
        image_path_item = self.duplicate_table_model.item(selected_row, column_index)

        if image_path_item:
            return image_path_item.text()
        return None

    def _remove_selected_row_logic_only(self) -> int:
        """UI 업데이트 없이 테이블 모델에서 선택된 행만 제거하고 제거된 행 인덱스를 반환합니다."""
        selected_indexes = self.duplicate_table_view.selectedIndexes()
        if selected_indexes:
            selected_row = selected_indexes[0].row()
            self.duplicate_table_model.removeRow(selected_row)
            return selected_row # 제거된 행 인덱스 반환
        return -1 # 선택된 행이 없거나 제거 실패

    def _update_selection_after_removal(self, removed_row_index: int):
        """행 제거 후 테이블 선택 및 이미지 패널을 업데이트합니다."""
        new_row_count = self.duplicate_table_model.rowCount()
        if new_row_count > 0:
            # 다음에 선택할 행 인덱스 결정
            next_row_to_select = min(removed_row_index, new_row_count - 1)
            if next_row_to_select >= 0: # 유효한 인덱스인지 확인
                self.duplicate_table_view.selectRow(next_row_to_select)
                self.on_table_item_clicked(self.duplicate_table_model.index(next_row_to_select, 0))
            else:
                # 이상 상황: 패널 초기화
                self.left_image_label.clear()
                self.left_info_label.setText("Image Info")
                self.right_image_label.clear()
                self.right_info_label.setText("Image Info")
        else:
            # 남은 행이 없으면 패널 초기화
            self.left_image_label.clear()
            self.left_info_label.setText("Image Info")
            self.right_image_label.clear()
            self.right_info_label.setText("Image Info")

    def delete_selected_image(self, target: str):
        """선택된 이미지를 휴지통으로 보내고 UndoManager를 통해 추적합니다."""
        image_path = self._get_selected_image_path(target)
        if not image_path:
            QMessageBox.warning(self, "Warning", "Please select an image pair from the list.")
            return

        # UndoManager의 delete_file 호출
        if self.undo_manager.delete_file(image_path, target):
            # 성공 시 테이블 행 제거 및 UI 업데이트
            removed_index = self._remove_selected_row_logic_only()
            if removed_index != -1:
                self._update_selection_after_removal(removed_index)
        # else: # 실패 메시지는 UndoManager에서 표시

    def move_selected_image(self, target: str):
        """선택된 이미지를 이동하고 UndoManager를 통해 추적합니다."""
        image_path = self._get_selected_image_path(target)
        if not image_path:
            QMessageBox.warning(self, "Warning", "Please select an image pair from the list.")
            return

        target_name = "Original" if target == 'original' else "Duplicate"
        destination_folder = QFileDialog.getExistingDirectory(self, f"Select Destination Folder for {target_name} Image")

        if destination_folder:
            # UndoManager의 move_file 호출
            if self.undo_manager.move_file(image_path, destination_folder, target):
                # 성공 시 테이블 행 제거 및 UI 업데이트
                removed_index = self._remove_selected_row_logic_only()
                if removed_index != -1:
                    self._update_selection_after_removal(removed_index)
            # else: # 실패/취소 메시지는 UndoManager에서 처리

    def update_undo_button_state(self, enabled: bool):
        """Undo 버튼의 활성화 상태를 업데이트하는 슬롯"""
        self.undo_button.setEnabled(enabled)

    def _get_selected_row_data(self) -> Optional[Dict[str, Any]]:
        """테이블 뷰에서 선택된 행의 데이터를 딕셔너리로 반환합니다."""
        selected_indexes = self.duplicate_table_view.selectedIndexes()
        if not selected_indexes:
            return None
        row = selected_indexes[0].row()
        try:
            original_path = self.duplicate_table_model.item(row, 0).text()
            duplicate_path = self.duplicate_table_model.item(row, 1).text()
            similarity = int(self.duplicate_table_model.item(row, 2).text())
            return {'original': original_path, 'duplicate': duplicate_path, 'similarity': similarity}
        except Exception as e:
            print(f"Error getting selected row data: {e}")
            return None

if __name__ == '__main__':
    # DPI 스케일링 활성화 (QApplication 생성 전 호출)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    setup_logging()
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 
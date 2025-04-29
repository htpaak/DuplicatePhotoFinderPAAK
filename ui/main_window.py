import sys
import os # os 모듈 임포트
import shutil # shutil 임포트
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QListView, QSplitter, QTableView,
    QHeaderView, QFileDialog, QMessageBox, QDesktopWidget # QDesktopWidget 추가
)
from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem, QResizeEvent # QResizeEvent 추가
from PyQt5.QtCore import Qt, QModelIndex, QSize # QSize 추가
from image_processor import find_duplicates # image_processor 임포트
from typing import Optional

class ImageLabel(QLabel):
    """동적 크기 조절 및 비율 유지를 지원하는 이미지 레이블"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_pixmap: Optional[QPixmap] = None
        self.setAlignment(Qt.AlignCenter) # 기본 정렬 설정
        self.setMinimumSize(100, 100) # 최소 크기 설정 (예시)

    def setPixmapFromFile(self, file_path: str) -> bool:
        """파일 경로로부터 Pixmap을 로드하고 원본을 저장합니다."""
        if not file_path or not os.path.exists(file_path):
            self._original_pixmap = None
            self.setText("File Not Found")
            return False

        self._original_pixmap = QPixmap(file_path)
        if self._original_pixmap.isNull():
            self._original_pixmap = None
            self.setText("Invalid Image File")
            return False

        self.updatePixmap() # 초기 이미지 표시
        return True

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
        self.setWindowTitle("Duplicate Image Finder")
        self.setGeometry(100, 100, 1100, 650) # 창 크기 조정 (1100x650)

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

        # 스캔 버튼 및 상태 표시줄 영역
        scan_status_layout = QHBoxLayout()
        scan_folder_button = QPushButton("Scan Folder")
        self.status_label = QLabel("Files scanned: 0 Duplicates found: 0")
        scan_status_layout.addWidget(scan_folder_button)
        scan_status_layout.addWidget(self.status_label, 1) # 상태 레이블이 남은 공간 차지
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
        # 초기 크기 비율 재조정 (상단 약 488, 하단 약 162 - 상단 비중 증가)
        splitter.setSizes([488, 162])
        main_layout.addWidget(splitter)

        # --- 시그널 연결 ---
        self.left_browse_button.clicked.connect(self.browse_left_image)
        self.right_browse_button.clicked.connect(self.browse_right_image)
        scan_folder_button.clicked.connect(self.scan_folder)
        self.duplicate_table_view.clicked.connect(self.on_table_item_clicked)
        # 삭제 버튼 시그널 연결 (대상 이미지 지정)
        self.left_delete_button.clicked.connect(lambda: self.delete_selected_image('original'))
        self.right_delete_button.clicked.connect(lambda: self.delete_selected_image('duplicate'))
        # 이동 버튼 시그널 연결 (대상 이미지 지정)
        self.left_move_button.clicked.connect(lambda: self.move_selected_image('original'))
        self.right_move_button.clicked.connect(lambda: self.move_selected_image('duplicate'))

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
        # ImageLabel에 Pixmap 설정 시도
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
        elif file_path and os.path.exists(file_path):
            # Pixmap 로드는 실패했지만 파일은 존재할 경우 (예: 지원하지 않는 형식)
            info_label.setText(f"Cannot load image format\n{os.path.basename(file_path)}")
        elif file_path:
             # 파일 경로가 있지만 존재하지 않는 경우
             info_label.setText(f"File not found\n{os.path.basename(file_path)}")
        else:
            # 파일 경로 자체가 없는 경우 (초기화 등)
            info_label.setText("Image Info")
            # image_label.clear()는 setPixmapFromFile(None) 등에서 처리됨

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
        """'Scan Folder' 버튼 클릭 시 폴더를 선택하고 중복 검사를 수행합니다."""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if folder_path:
            QApplication.setOverrideCursor(Qt.WaitCursor) # 작업 중 커서 변경
            self.status_label.setText(f"Scanning folder: {folder_path}...")
            QApplication.processEvents() # UI 업데이트 강제

            try:
                scanned_count, duplicates = find_duplicates(folder_path)
                self.status_label.setText(f"Files scanned: {scanned_count} Duplicates found: {len(duplicates)}")

                # 테이블 모델 초기화 및 데이터 채우기
                self.duplicate_table_model.removeRows(0, self.duplicate_table_model.rowCount())
                for original, duplicate, similarity in duplicates:
                    item_original = QStandardItem(original)
                    item_duplicate = QStandardItem(duplicate)
                    item_similarity = QStandardItem(str(similarity))
                    item_similarity.setTextAlignment(Qt.AlignCenter) # 유사도 가운데 정렬
                    self.duplicate_table_model.appendRow([item_original, item_duplicate, item_similarity])

                # 첫 번째 항목 자동 선택 (결과가 있는 경우)
                if duplicates:
                    self.duplicate_table_view.selectRow(0)
                    self.on_table_item_clicked(self.duplicate_table_model.index(0, 0)) # 첫 행 데이터로 이미지 업데이트
                else:
                    # 중복 없을 시 이미지 초기화
                    self.left_image_label.clear()
                    self.left_info_label.setText("Image Info")
                    self.right_image_label.clear()
                    self.right_info_label.setText("Image Info")

            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to scan folder: {e}")
                self.status_label.setText("Scan failed.")
            finally:
                QApplication.restoreOverrideCursor() # 원래 커서로 복구

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

    def _remove_selected_row(self):
        """테이블 뷰에서 선택된 행을 제거하고, 다음 행을 선택하여 표시하거나 패널을 초기화합니다."""
        selected_indexes = self.duplicate_table_view.selectedIndexes()
        if selected_indexes:
            selected_row = selected_indexes[0].row()
            current_row_count = self.duplicate_table_model.rowCount()

            # 행 제거
            self.duplicate_table_model.removeRow(selected_row)

            # 상태 레이블 업데이트
            new_row_count = self.duplicate_table_model.rowCount()
            try:
                status_text_part = self.status_label.text().split(" Duplicates found:")[0]
                self.status_label.setText(f"{status_text_part} Duplicates found: {new_row_count}")
            except IndexError:
                 self.status_label.setText(f"Duplicates found: {new_row_count}")

            # 남은 행이 있으면 다음 행 선택, 없으면 패널 초기화
            if new_row_count > 0:
                # 다음에 선택할 행 인덱스 결정 (현재 인덱스 또는 이전 인덱스)
                next_row_to_select = min(selected_row, new_row_count - 1)
                self.duplicate_table_view.selectRow(next_row_to_select)
                # 선택된 행의 이미지 표시 업데이트 트리거
                self.on_table_item_clicked(self.duplicate_table_model.index(next_row_to_select, 0))
            else:
                # 남은 행이 없으면 양쪽 패널 초기화
                self.left_image_label.clear()
                self.left_info_label.setText("Image Info")
                self.right_image_label.clear()
                self.right_info_label.setText("Image Info")

    def delete_selected_image(self, target: str):
        """선택된 원본 또는 중복 이미지를 확인 없이 바로 삭제합니다."""
        image_path = self._get_selected_image_path(target)
        if not image_path:
            QMessageBox.warning(self, "Warning", "Please select an image pair from the list.")
            return

        target_name = "Original" if target == 'original' else "Duplicate"
        # 확인 메시지 제거
        # reply = QMessageBox.question(self, f'Confirm Delete {target_name}',
        #                              f"Are you sure you want to delete this {target_name.lower()} file?\n{image_path}",
        #                              QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        # if reply == QMessageBox.Yes:
        try:
            os.remove(image_path)
            # 삭제 성공 시 간단한 상태 표시 (옵션)
            # print(f"{target_name} file deleted: {image_path}")
            # QMessageBox.information(self, "Success", f"{target_name} file deleted successfully:\n{image_path}") # 정보 메시지도 제거 가능
            self._remove_selected_row()
        except FileNotFoundError:
            QMessageBox.critical(self, "Error", "File not found. It might have been already deleted or moved.")
            self._remove_selected_row()
        except PermissionError:
            QMessageBox.critical(self, "Error", f"Permission denied. Cannot delete the {target_name.lower()} file.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to delete {target_name.lower()} file: {e}")

    def move_selected_image(self, target: str):
        """선택된 원본 또는 중복 이미지를 다른 폴더로 이동합니다."""
        image_path = self._get_selected_image_path(target)
        if not image_path:
            QMessageBox.warning(self, "Warning", "Please select an image pair from the list.")
            return

        target_name = "Original" if target == 'original' else "Duplicate"
        destination_folder = QFileDialog.getExistingDirectory(self, f"Select Destination Folder for {target_name} Image")
        if destination_folder:
            if os.path.dirname(image_path) == destination_folder:
                 QMessageBox.warning(self, "Warning", "Source and destination folders are the same.")
                 return
            try:
                base_filename = os.path.basename(image_path)
                destination_path = os.path.join(destination_folder, base_filename)

                if os.path.exists(destination_path):
                    reply = QMessageBox.question(self, 'Confirm Overwrite',
                                             f"File already exists in the destination folder:\n{destination_path}\nOverwrite?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if reply == QMessageBox.No:
                        return

                shutil.move(image_path, destination_path)
                QMessageBox.information(self, "Success", f"{target_name} file moved successfully to:\n{destination_folder}")
                self._remove_selected_row()
            except FileNotFoundError:
                 QMessageBox.critical(self, "Error", "File not found. It might have been already deleted or moved.")
                 self._remove_selected_row()
            except PermissionError:
                QMessageBox.critical(self, "Error", f"Permission denied. Cannot move the {target_name.lower()} file.")
            except Exception as e:
                 QMessageBox.critical(self, "Error", f"Failed to move {target_name.lower()} file: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 
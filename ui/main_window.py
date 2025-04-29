import sys
import os # os 모듈 임포트
import shutil # shutil 임포트
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QListView, QSplitter, QTableView,
    QHeaderView, QFileDialog, QMessageBox, QDesktopWidget # QDesktopWidget 추가
)
from PyQt5.QtGui import QPixmap, QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt, QModelIndex # QModelIndex 추가
from image_processor import find_duplicates # image_processor 임포트
from typing import Optional

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
        self.left_image_label = QLabel("Original Image Area") # 이미지 표시용 레이블
        self.left_image_label.setAlignment(Qt.AlignCenter)
        self.left_image_label.setFrameShape(QFrame.Box) # 테두리 추가
        self.left_image_label.setMinimumSize(300, 200) # 최소 크기 설정
        self.left_image_label.setScaledContents(True)
        left_panel_layout.addWidget(self.left_image_label, 1) # Stretch factor 1 설정
        self.left_info_label = QLabel("Image Info") # 정보 레이블
        self.left_info_label.setAlignment(Qt.AlignCenter)
        left_panel_layout.addWidget(self.left_info_label) # Stretch factor 0 (기본값)

        left_button_layout = QHBoxLayout()
        self.left_move_button = QPushButton("Move") # 버튼 객체 저장
        self.left_browse_button = QPushButton("Browse") # 버튼 객체 저장
        self.left_delete_button = QPushButton("Delete") # 버튼 객체 저장
        left_button_layout.addWidget(self.left_move_button)
        left_button_layout.addWidget(self.left_browse_button)
        left_button_layout.addWidget(self.left_delete_button)
        left_panel_layout.addLayout(left_button_layout) # Stretch factor 0 (기본값)
        image_comparison_layout.addLayout(left_panel_layout)

        # 오른쪽 영역 (중복 이미지)
        right_panel_layout = QVBoxLayout()
        self.right_image_label = QLabel("Duplicate Image Area") # 이미지 표시용 레이블
        self.right_image_label.setAlignment(Qt.AlignCenter)
        self.right_image_label.setFrameShape(QFrame.Box) # 테두리 추가
        self.right_image_label.setMinimumSize(300, 200) # 최소 크기 설정
        self.right_image_label.setScaledContents(True)
        right_panel_layout.addWidget(self.right_image_label, 1) # Stretch factor 1 설정
        self.right_info_label = QLabel("Image Info") # 정보 레이블
        self.right_info_label.setAlignment(Qt.AlignCenter)
        right_panel_layout.addWidget(self.right_info_label) # Stretch factor 0 (기본값)

        right_button_layout = QHBoxLayout()
        self.right_move_button = QPushButton("Move") # 버튼 객체 저장
        self.right_browse_button = QPushButton("Browse") # 버튼 객체 저장
        self.right_delete_button = QPushButton("Delete") # 버튼 객체 저장
        right_button_layout.addWidget(self.right_move_button)
        right_button_layout.addWidget(self.right_browse_button)
        right_button_layout.addWidget(self.right_delete_button)
        right_panel_layout.addLayout(right_button_layout) # Stretch factor 0 (기본값)
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
        self.right_browse_button.clicked.connect(self.browse_right_image) # 오른쪽 Browse 버튼 시그널 연결
        scan_folder_button.clicked.connect(self.scan_folder) # 스캔 버튼 시그널 연결
        self.duplicate_table_view.clicked.connect(self.on_table_item_clicked) # 테이블 클릭 시그널 연결
        # 삭제 버튼 시그널 연결 (양쪽 버튼 모두 동일 기능 수행)
        self.left_delete_button.clicked.connect(self.delete_selected_duplicate)
        self.right_delete_button.clicked.connect(self.delete_selected_duplicate)
        # 이동 버튼 시그널 연결 (양쪽 버튼 모두 동일 기능 수행)
        self.left_move_button.clicked.connect(self.move_selected_duplicate)
        self.right_move_button.clicked.connect(self.move_selected_duplicate)

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

    def _update_image_info(self, image_label: QLabel, info_label: QLabel, file_path: str):
        """이미지 레이블과 정보 레이블을 업데이트하는 헬퍼 메서드"""
        pixmap = QPixmap(file_path)
        if not pixmap.isNull():
            image_label.setPixmap(pixmap)
            try:
                file_size_kb = round(os.path.getsize(file_path) / 1024)
                img_format = os.path.splitext(file_path)[1].upper()[1:]
                filename = os.path.basename(file_path) # 파일 이름 추출
                # 정보 텍스트에 파일 이름 추가 (줄바꿈 사용)
                info_text = f"{img_format} {pixmap.width()} x {pixmap.height()} {file_size_kb} KB\n{filename}"
                info_label.setText(info_text)
            except FileNotFoundError:
                info_label.setText("File not found.")
                image_label.setText("File Not Found")
            except Exception as e:
                print(f"Error getting file info: {e}")
                info_label.setText("Error getting info.")
        else:
            info_label.setText("Cannot load image.")
            image_label.setText("Invalid Image File")

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

    def _get_selected_duplicate_path(self) -> Optional[str]:
        """테이블 뷰에서 선택된 행의 중복 이미지 경로를 반환합니다."""
        selected_indexes = self.duplicate_table_view.selectedIndexes()
        if not selected_indexes:
            return None
        selected_row = selected_indexes[0].row()
        duplicate_path_item = self.duplicate_table_model.item(selected_row, 1) # 중복 이미지 경로 열
        if duplicate_path_item:
            return duplicate_path_item.text()
        return None

    def _remove_selected_row(self):
        """테이블 뷰에서 선택된 행을 제거합니다."""
        selected_indexes = self.duplicate_table_view.selectedIndexes()
        if selected_indexes:
            selected_row = selected_indexes[0].row()
            self.duplicate_table_model.removeRow(selected_row)
            # 상태 레이블 업데이트
            current_duplicates = self.duplicate_table_model.rowCount()
            status_text = self.status_label.text().split("Duplicates found:")[0]
            self.status_label.setText(f"{status_text} Duplicates found: {current_duplicates}")
            # 삭제/이동 후 이미지 패널 초기화
            self.right_image_label.clear()
            self.right_info_label.setText("Image Info")
            # 원본 이미지도 선택 해제된 것으로 간주하여 초기화 (선택적)
            # self.left_image_label.clear()
            # self.left_info_label.setText("Image Info")

    def delete_selected_duplicate(self):
        """선택된 중복 이미지를 삭제합니다."""
        duplicate_path = self._get_selected_duplicate_path()
        if not duplicate_path:
            QMessageBox.warning(self, "Warning", "Please select a duplicate image from the list.")
            return

        reply = QMessageBox.question(self, 'Confirm Delete',
                                     f"Are you sure you want to delete this file?\n{duplicate_path}",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            try:
                os.remove(duplicate_path)
                QMessageBox.information(self, "Success", f"File deleted successfully:\n{duplicate_path}")
                self._remove_selected_row()
            except FileNotFoundError:
                QMessageBox.critical(self, "Error", "File not found. It might have been already deleted or moved.")
                # 파일이 없어도 테이블에서는 제거할 수 있음
                self._remove_selected_row()
            except PermissionError:
                QMessageBox.critical(self, "Error", "Permission denied. Cannot delete the file.")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete file: {e}")

    def move_selected_duplicate(self):
        """선택된 중복 이미지를 다른 폴더로 이동합니다."""
        duplicate_path = self._get_selected_duplicate_path()
        if not duplicate_path:
            QMessageBox.warning(self, "Warning", "Please select a duplicate image from the list.")
            return

        destination_folder = QFileDialog.getExistingDirectory(self, "Select Destination Folder")
        if destination_folder:
            # 대상 폴더와 원본 파일의 폴더가 같은 경우 경고 (선택적)
            if os.path.dirname(duplicate_path) == destination_folder:
                 QMessageBox.warning(self, "Warning", "Source and destination folders are the same.")
                 return
            try:
                base_filename = os.path.basename(duplicate_path)
                destination_path = os.path.join(destination_folder, base_filename)

                # 대상 경로에 동일한 파일 이름이 있는지 확인 (선택적)
                if os.path.exists(destination_path):
                    reply = QMessageBox.question(self, 'Confirm Overwrite',
                                             f"File already exists in the destination folder:\n{destination_path}\nOverwrite?",
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                    if reply == QMessageBox.No:
                        return

                shutil.move(duplicate_path, destination_path)
                QMessageBox.information(self, "Success", f"File moved successfully to:\n{destination_folder}")
                self._remove_selected_row()
            except FileNotFoundError:
                 QMessageBox.critical(self, "Error", "File not found. It might have been already deleted or moved.")
                 self._remove_selected_row()
            except PermissionError:
                QMessageBox.critical(self, "Error", "Permission denied. Cannot move the file.")
            except Exception as e:
                 QMessageBox.critical(self, "Error", f"Failed to move file: {e}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_()) 
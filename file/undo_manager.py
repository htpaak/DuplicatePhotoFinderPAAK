"""
실행 취소 관리 모듈

이 모듈은 삭제된 파일을 추적하고 복원하는 기능을 담당합니다.
"""

import os
import shutil
import gc
from collections import deque
import time
import platform
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import QMessageBox, QApplication, QTableView, QLabel
from PyQt5.QtCore import QObject, pyqtSignal, QTimer, Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from typing import Dict, Any, Optional
import send2trash

# Windows 환경에서 사용할 winshell 패키지
try:
    import winshell
    WINSHELL_AVAILABLE = True
except ImportError:
    WINSHELL_AVAILABLE = False

class UndoManager(QObject):
    """
    실행 취소 관리 클래스
    
    이 클래스는 삭제된 파일을 추적하고 복원하는 기능을 담당합니다.
    파일이 휴지통으로 이동된 경우 원본 경로를 기억하고, 나중에 복원할 수 있습니다.
    """
    
    # 작업 실행 취소 가능 상태 변경 시그널
    undo_status_changed = pyqtSignal(bool)
    
    # 작업 유형 상수
    ACTION_DELETE = "delete"
    ACTION_MOVE = "move"
    ACTION_COPY = "copy"
    
    def __init__(self, main_window: 'MainWindow'):
        """
        UndoManager 초기화
        
        Args:
            main_window: 메인 윈도우 인스턴스 (MainWindow)
        """
        super().__init__()
        self.main_window = main_window
        self.actions = deque(maxlen=10)  # 최대 10개 작업 추적
    
    def show_message(self, message: str, level: str = 'info'):
        """메시지 박스를 사용하여 메시지를 표시합니다."""
        if level == 'error':
            QMessageBox.critical(self.main_window, "Error", message)
        elif level == 'warning':
            QMessageBox.warning(self.main_window, "Warning", message)
        else:
            # 정보 메시지는 표시하지 않도록 변경 (요청사항 반영)
            # QMessageBox.information(self.main_window, "Info", message)
            print(f"[UndoManager Info] {message}") # 콘솔 로그로 대체
    
    def delete_file(self, original_path: str, target_type: str) -> bool:
        """파일을 휴지통으로 보내고 작업을 추적합니다."""
        success = False
        try:
            normalized_path = os.path.normpath(original_path)
            send2trash.send2trash(normalized_path)
            success = True
            print(f"File sent to trash: {normalized_path}")
        except FileNotFoundError:
            self.show_message(f"File not found: {original_path}", 'error')
        except Exception as e:
            self.show_message(f"Failed to send file to trash: {e}\nPath: {original_path}", 'error')

        if success:
            # 테이블 모델에서 현재 선택된 행의 데이터 가져오기
            # MainWindow의 _get_selected_row_data 활용
            selected_data = self.main_window._get_selected_row_data()
            if selected_data:
                action_details = {
                    'type': self.ACTION_DELETE,
                    'target': target_type,
                    'original_path': selected_data['original'],
                    'duplicate_path': selected_data['duplicate'],
                    'similarity': selected_data['similarity'],
                    'deleted_path': original_path # 삭제된 파일의 원래 경로 저장
                }
                self.actions.append(action_details)
                self.undo_status_changed.emit(True)
            else:
                print("[UndoManager Error] Could not get selected row data after deletion.")
                success = False # 작업 추적 실패
        return success

    def move_file(self, original_path: str, destination_folder: str, target_type: str) -> bool:
        """파일을 이동하고 작업을 추적합니다."""
        success = False
        destination_path = ""
        try:
            base_filename = os.path.basename(original_path)
            destination_path = os.path.join(destination_folder, base_filename)
            # 덮어쓰기 확인 (QMessageBox 직접 호출)
            if os.path.exists(destination_path):
                reply = QMessageBox.question(self.main_window, 'Confirm Overwrite',
                                         f"File already exists: {destination_path}\nOverwrite?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    return False # 작업 취소
            # 이동
            shutil.move(original_path, destination_path)
            success = True
            print(f"File moved: {original_path} -> {destination_path}")
        except FileNotFoundError:
            self.show_message(f"File not found: {original_path}", 'error')
        except Exception as e:
            self.show_message(f"Failed to move file: {e}\nFrom: {original_path}\nTo: {destination_path}", 'error')

        if success:
            selected_data = self.main_window._get_selected_row_data()
            if selected_data:
                action_details = {
                    'type': self.ACTION_MOVE,
                    'target': target_type,
                    'original_path': selected_data['original'],
                    'duplicate_path': selected_data['duplicate'],
                    'similarity': selected_data['similarity'],
                    'moved_from': original_path,
                    'moved_to': destination_path
                }
                self.actions.append(action_details)
                self.undo_status_changed.emit(True)
            else:
                 print("[UndoManager Error] Could not get selected row data after move.")
                 # 이동은 성공했으나 추적 실패 시 어떻게 처리할지? 일단 성공으로 간주.
        return success

    def can_undo(self):
        """
        실행 취소 가능 여부 확인
        
        Returns:
            bool: 실행 취소 가능 여부
        """
        return len(self.actions) > 0
    
    def undo_last_action(self):
        """
        마지막 작업 취소 (삭제, 이동, 복사)
        
        Returns:
            tuple: (성공 여부, 복원된 파일 경로)
        """
        if not self.actions:
            self.show_message("No actions to undo")
            return False, None
        
        # 마지막 작업 가져오기
        last_action = self.actions.pop()
        action_type = last_action.get('type')
        
        # 작업 유형에 따라 처리
        if action_type == self.ACTION_DELETE:
            result = self._undo_deletion(last_action)
        elif action_type == self.ACTION_MOVE:
            result = self._undo_move(last_action)
        # elif action_type == self.ACTION_COPY:
        #     result = self._undo_copy(last_action)
        else:
            self.show_message(f"Unknown action type: {action_type}", 'error')
            result = False, None
        
        # Undo 후 상태 업데이트
        self.undo_status_changed.emit(len(self.actions) > 0)
        return result
    
    def _undo_deletion(self, delete_action):
        """
        삭제 작업 취소 내부 처리 메소드
        
        Args:
            delete_action: 삭제 작업 정보 딕셔너리
            
        Returns:
            tuple: (성공 여부, 복원된 파일 경로)
        """
        original_path = delete_action.get('deleted_path')
        if not original_path:
             self.show_message("Invalid action data for undo delete.", 'error')
             return False, None

        # 파일 복원 시도
        if self._restore_from_trash(original_path):
            # 테이블에 데이터 복원
            if self._add_to_table(delete_action):
                 self.show_message(f"File restored: {os.path.basename(original_path)}")
                 return True, original_path
            else:
                 # 파일 복원은 성공했으나 테이블 추가 실패
                 self.show_message(f"File restored but failed to update list: {os.path.basename(original_path)}", 'warning')
                 return True, original_path # 파일 복원 자체는 성공
        else:
            # 복원 실패 메시지는 _restore_from_trash에서 표시
            return False, None
    
    def _undo_move(self, move_action):
        """
        이동 작업 취소 내부 처리 메소드
        
        Args:
            move_action: 이동 작업 정보 딕셔너리
            
        Returns:
            tuple: (성공 여부, 복원된 파일 경로)
        """
        original_path = move_action.get('moved_from')
        current_path = move_action.get('moved_to')
        if not original_path or not current_path:
             self.show_message("Invalid action data for undo move.", 'error')
             return False, None

        # 이동 취소 가능 확인
        if not os.path.exists(current_path):
            self.show_message(f"Moved file not found: {os.path.basename(current_path)}", 'error')
            return False, None
        if os.path.exists(original_path):
            self.show_message(f"File already exists at original location: {os.path.basename(original_path)}", 'warning')
            return False, None

        try:
            shutil.move(current_path, original_path)
            if self._add_to_table(move_action):
                 self.show_message(f"Move undone: {os.path.basename(original_path)}")
                 return True, original_path
            else:
                 self.show_message(f"Move undone but failed to update list: {os.path.basename(original_path)}", 'warning')
                 return True, original_path
        except Exception as e:
            self.show_message(f"Failed to undo move: {e}", 'error')
            return False, None
    
    def _restore_from_trash(self, original_path):
        """
        휴지통에서 파일 복원 시도
        
        Args:
            original_path: 원본 파일 경로
            
        Returns:
            bool: 복원 성공 여부
        """
        try:
            file_name = os.path.basename(original_path)
            
            # Windows 환경에서 winshell을 사용하여 휴지통 검색
            if platform.system() == 'Windows' and WINSHELL_AVAILABLE:
                # 휴지통의 모든 항목을 검색
                recycled_items = list(winshell.recycle_bin())
                
                # 원본 파일명과 일치하는 항목 찾기
                for item in recycled_items:
                    try:
                         # 간혹 original_filename() 접근 시 오류 발생 가능성 있음
                         item_orig_path = item.original_filename()
                         item_name = os.path.basename(item_orig_path)
                         if item_name.lower() == file_name.lower():
                             print(f"Found in trash: {item_orig_path}, attempting to restore to {original_path}")
                             winshell.undelete(item_orig_path)
                             # 복원 후 경로 확인 및 필요시 이동
                             if os.path.exists(original_path):
                                 return True
                             elif os.path.exists(item_orig_path):
                                  print(f"Restored to {item_orig_path}, moving to {original_path}")
                                  shutil.move(item_orig_path, original_path)
                                  return True
                             else:
                                  print(f"Undelete called but file not found at either {original_path} or {item_orig_path}")
                                  # 다른 경로에 복원되었을 가능성? (탐색 어려움)
                    except Exception as ie:
                         print(f"Error accessing recycle bin item: {ie}")
                
                # 파일을 찾지 못한 경우
                self.show_message(f"Could not find {file_name} in the recycle bin", 'warning')
                return False
                
            # 다른 OS 환경에서는 대체 방법 제공
            else:
                # 파일 목록에만 추가 (실제 파일은 복원하지 않음)
                self.show_message("Recycle bin restoration is only supported on Windows.", 'warning')
                return False # Windows 외 OS에서는 복원 불가로 처리
                
        except Exception as e:
            self.show_message(f"Failed to restore from recycle bin: {e}", 'error')
            return False
    
    def _add_to_table(self, action_details: Dict[str, Any]) -> bool:
        """복원된 항목 데이터를 테이블 모델의 첫 번째 행에 삽입합니다."""
        try:
            model: QStandardItemModel = self.main_window.duplicate_table_model
            item_original = QStandardItem(action_details['original_path'])
            item_duplicate = QStandardItem(action_details['duplicate_path'])
            item_similarity = QStandardItem(str(action_details['similarity']))
            item_similarity.setTextAlignment(Qt.AlignCenter)
            model.insertRow(0, [item_original, item_duplicate, item_similarity])

            # 테이블 뷰 업데이트 및 선택
            table_view: QTableView = self.main_window.duplicate_table_view
            table_view.selectRow(0)
            # MainWindow의 on_table_item_clicked 호출하여 패널 업데이트
            self.main_window.on_table_item_clicked(model.index(0, 0))

            # 상태 레이블 업데이트
            status_label: QLabel = self.main_window.status_label
            new_row_count = model.rowCount()
            try:
                status_text_part = status_label.text().split(" Duplicates found:")[0]
                status_label.setText(f"{status_text_part} Duplicates found: {new_row_count}")
            except IndexError:
                 status_label.setText(f"Duplicates found: {new_row_count}")

            return True
        except Exception as e:
            print(f"[UndoManager Error] Failed to add item back to table: {e}")
            self.show_message(f"Failed to update the list after restoring file.", 'error')
            return False 
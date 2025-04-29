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
from typing import Dict, Any, Optional, List
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
    
    def delete_file(self, deleted_path: str, group_id: str, representative_path: str, member_paths: List[str]) -> bool:
        """파일을 휴지통으로 보내고 작업을 추적합니다. (그룹 정보 사용)"""
        success = False
        try:
            normalized_path = os.path.normpath(deleted_path)
            send2trash.send2trash(normalized_path)
            success = True
            print(f"File sent to trash: {normalized_path}")
        except FileNotFoundError:
            self.show_message(f"File not found: {deleted_path}", 'error')
        except Exception as e:
            self.show_message(f"Failed to send file to trash: {e}\nPath: {deleted_path}", 'error')

        if success:
            # 전달받은 그룹 정보를 사용하여 action_details 생성
            action_details = {
                'type': self.ACTION_DELETE,
                'group_id': group_id,
                'representative_path': representative_path, # 삭제 시점의 대표
                'member_paths': list(member_paths), # 삭제 시점의 멤버 목록 (복사본)
                'deleted_path': deleted_path # 실제 삭제된 파일 경로
            }
            self.actions.append(action_details)
            self.undo_status_changed.emit(True)
            # else: # selected_data 의존성 제거됨
            #     print("[UndoManager Error] Could not get selected row data after deletion.")
            #     success = False # 작업 추적 실패
        return success

    def move_file(self, moved_from_path: str, destination_folder: str, group_id: str, representative_path: str, member_paths: List[str]) -> bool:
        """파일을 이동하고 작업을 추적합니다. (그룹 정보 사용)"""
        success = False
        destination_path = ""
        try:
            base_filename = os.path.basename(moved_from_path)
            destination_path = os.path.join(destination_folder, base_filename)
            if os.path.exists(destination_path):
                reply = QMessageBox.question(self.main_window, 'Confirm Overwrite',
                                         f"File already exists: {destination_path}\nOverwrite?",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.No:
                    return False
            shutil.move(moved_from_path, destination_path)
            success = True
            print(f"File moved: {moved_from_path} -> {destination_path}")
        except FileNotFoundError:
            self.show_message(f"File not found: {moved_from_path}", 'error')
        except Exception as e:
            self.show_message(f"Failed to move file: {e}\nFrom: {moved_from_path}\nTo: {destination_path}", 'error')

        if success:
            # 전달받은 그룹 정보 사용
            action_details = {
                'type': self.ACTION_MOVE,
                'group_id': group_id,
                'representative_path': representative_path,
                'member_paths': list(member_paths),
                'moved_from': moved_from_path,
                'moved_to': destination_path
            }
            self.actions.append(action_details)
            self.undo_status_changed.emit(True)
            # else:
            #      print("[UndoManager Error] Could not get selected row data after move.")
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

        if self._restore_from_trash(original_path):
            # 테이블 복원 로직 변경: _add_to_table 대신 MainWindow의 그룹 업데이트 로직 호출 필요
            # 임시: 콘솔 로그만 출력하고 MainWindow 업데이트는 외부에서 처리하도록 유도
            print(f"[UndoManager] File restored: {original_path}. Triggering UI update needed.")
            # TODO: MainWindow의 그룹 데이터 및 테이블 업데이트 로직 호출 방법 강구
            # self.main_window._restore_group_ui(delete_action) # 예시
            return True, original_path
        else:
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
            # 테이블 복원 로직 변경 (삭제와 동일)
            print(f"[UndoManager] Move undone for: {original_path}. Triggering UI update needed.")
            # TODO: MainWindow의 그룹 데이터 및 테이블 업데이트 로직 호출 방법 강구
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
    
    # _add_to_table 메서드는 더 이상 직접 사용되지 않음 (제거 또는 주석 처리)
    # def _add_to_table(self, action_details: Dict[str, Any]) -> bool:
    #     ... 
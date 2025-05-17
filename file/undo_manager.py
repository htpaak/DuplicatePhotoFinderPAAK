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
from PyQt5.QtCore import QObject, pyqtSignal, Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from typing import Dict, Any, Optional, List, Tuple, TYPE_CHECKING
import send2trash

# Windows 환경에서 사용할 winshell 패키지
try:
    import winshell
    WINSHELL_AVAILABLE = True
except ImportError:
    WINSHELL_AVAILABLE = False

# 타입 검사를 위한 조건부 임포트
if TYPE_CHECKING:
    from ui.main_window import MainWindow

class UndoManager(QObject):
    """
    실행 취소 관리 클래스
    
    이 클래스는 삭제된 파일을 추적하고 복원하는 기능을 담당합니다.
    파일이 휴지통으로 이동된 경우 원본 경로를 기억하고, 나중에 복원할 수 있습니다.
    """
    
    # 작업 실행 취소 가능 상태 변경 시그널
    undo_status_changed = pyqtSignal(bool)
    # 그룹 상태 복원 필요 시그널 (복원할 액션 정보를 전달)
    group_state_restore_needed = pyqtSignal(dict)
    
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
    
    def delete_file(self, deleted_path: str, group_id: str, representative_path: str, member_paths: List[str], snapshot_rep: Optional[str], snapshot_members: Optional[List[Tuple[str, int, int]]]) -> bool:
        """파일을 휴지통으로 보내고 작업을 추적합니다. (그룹 정보 및 스냅샷 사용)"""
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
                'deleted_path': deleted_path, # 실제 삭제된 파일 경로
                'snapshot_rep': snapshot_rep,
                'snapshot_members': snapshot_members
            }
            self.actions.append(action_details)
            self.undo_status_changed.emit(True)
            # else: # selected_data 의존성 제거됨
            #     print("[UndoManager Error] Could not get selected row data after deletion.")
            #     success = False # 작업 추적 실패
        return success

    def move_file(self, moved_from_path: str, destination_folder: str, group_id: str, representative_path: str, member_paths: List[str], snapshot_rep: Optional[str], snapshot_members: Optional[List[Tuple[str, int, int]]]) -> bool:
        """파일을 이동하고 작업을 추적합니다. (그룹 정보 및 스냅샷 사용)"""
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
                'moved_to': destination_path,
                'snapshot_rep': snapshot_rep,
                'snapshot_members': snapshot_members
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
        마지막 작업 취소 (삭제, 이동, 복사, 배치 작업)
        
        Returns:
            tuple: (성공 여부, 복원된 파일 경로)
        """
        if not self.actions:
            self.show_message("No actions to undo")
            return False, None
        
        # 마지막 작업 가져오기
        last_action = self.actions.pop()
        action_type = last_action.get('type')
        
        print(f"[UndoManager Debug] 마지막 작업 실행 취소 시작: {action_type}")
        
        # 작업 유형에 따라 처리
        if action_type == self.ACTION_DELETE:
            result = self._undo_deletion(last_action)
        elif action_type == self.ACTION_MOVE:
            result = self._undo_move(last_action)
        elif action_type == 'batch_delete':
            result = self._undo_batch_deletion(last_action)
        elif action_type == 'batch_move':
            result = self._undo_batch_move(last_action)
        else:
            self.show_message(f"Unknown action type: {action_type}", 'error')
            result = False, None
        
        print(f"[UndoManager Debug] 작업 취소 결과: {result}")
        
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

        print(f"[UndoManager Debug] 삭제 취소 시도: {original_path}")

        if self._restore_from_trash(original_path):
            # 테이블 복원 로직 변경: MainWindow에서 처리하도록 시그널 발생
            print(f"[UndoManager] File restored: {original_path}. Triggering group state restore.")
            
            # 시그널 발생 전 데이터 확인
            group_id = delete_action.get('group_id')
            snapshot_rep = delete_action.get('snapshot_rep')
            snapshot_members = delete_action.get('snapshot_members')
            print(f"[UndoManager Debug] 시그널 발생할 데이터: group_id={group_id}, snapshot_rep={os.path.basename(snapshot_rep) if snapshot_rep else 'None'}, snapshot_members 수={len(snapshot_members) if snapshot_members else 0}")
            
            # 시그널 발생
            self.group_state_restore_needed.emit(delete_action)
            return True, original_path
        else:
            print(f"[UndoManager Debug] 휴지통에서 파일 복원 실패: {original_path}")
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
            # 테이블 복원 로직 변경: MainWindow에서 처리하도록 시그널 발생
            print(f"[UndoManager] Move undone for: {original_path}. Triggering group state restore.")
            self.group_state_restore_needed.emit(move_action)
            return True, original_path
        except Exception as e:
            self.show_message(f"Failed to undo move: {e}", 'error')
            return False, None
    
    def _restore_from_trash(self, original_path):
        """
        휴지통에서 파일 복원 시도 (윈도우에서는 winshell 사용, 다른 OS에서는 대안 메커니즘 사용)

        Args:
            original_path (str): 복원할 파일의 원래 경로

        Returns:
            bool: 복원 성공 여부
        """
        # 먼저 파일이 이미 존재하는지 확인
        if os.path.exists(original_path):
            print(f"[UndoManager] File already exists at original path: {original_path}")
            return True  # 이미 원래 위치에 있음
        
        try:
            if platform.system() == 'Windows' and WINSHELL_AVAILABLE:
                # Windows에서 winshell을 사용하여 파일 찾기 시도
                basename = os.path.basename(original_path)
                found_in_recycle_bin = False
                
                # 휴지통의 각 항목에 대해
                for item in winshell.recycle_bin():
                    try:
                        recycle_name = os.path.basename(item.original_filename())
                        if recycle_name == basename:
                            found_in_recycle_bin = True
                            print(f"[UndoManager] Found {basename} in recycle bin")
                            # 원본 위치로 복원
                            item.undelete()
                            return True
                    except Exception as inner_e:
                        print(f"[UndoManager] Error accessing recycle bin item: {inner_e}")
                        continue
                
                if not found_in_recycle_bin:
                    self.show_message(f"File not found in recycle bin: {basename}", 'warning')
                    return False
            else:
                # Windows가 아니거나 winshell이 없는 경우
                # 다른 OS의 휴지통 접근은 복잡하므로 알림만 표시
                message = f"Manual restore needed: Please restore '{os.path.basename(original_path)}' from trash"
                self.show_message(message)
                return False
                
        except Exception as e:
            self.show_message(f"Failed to restore from trash: {e}", 'error')
            return False
        
        return False
            
    def batch_delete_files(self, delete_actions: List[dict]) -> Tuple[bool, List[str]]:
        """
        여러 파일을 한 번에 삭제하고 이를 하나의 Undo 작업으로 추적합니다.
        
        Args:
            delete_actions: 삭제할 파일들의 정보 목록 (각 항목은 deleted_path, group_id, representative_path,
                            member_paths, snapshot_rep, snapshot_members 정보를 포함하는 딕셔너리)
                            
        Returns:
            tuple: (성공 여부, 삭제된 파일 경로 목록)
        """
        if not delete_actions:
            print("[UndoManager] No files to delete in batch")
            return False, []
            
        successful_deletes = []
        failed_deletes = []
        
        # 모든 파일에 대해 삭제 시도
        for action in delete_actions:
            deleted_path = action.get('deleted_path')
            if not deleted_path or not os.path.exists(deleted_path):
                failed_deletes.append(deleted_path if deleted_path else "Unknown path")
                continue
                
            try:
                normalized_path = os.path.normpath(deleted_path)
                send2trash.send2trash(normalized_path)
                successful_deletes.append(deleted_path)
                print(f"[UndoManager] File sent to trash: {normalized_path}")
            except Exception as e:
                print(f"[UndoManager] Failed to delete file: {e}\nPath: {deleted_path}")
                failed_deletes.append(deleted_path)
                
        # 모든 삭제가 실패한 경우
        if not successful_deletes:
            if failed_deletes:
                error_msg = f"Failed to delete {len(failed_deletes)} files."
                self.show_message(error_msg, 'error')
            return False, []
            
        # 실패한 항목이 있는 경우 경고 표시
        if failed_deletes:
            warn_msg = f"Failed to delete {len(failed_deletes)} of {len(delete_actions)} files."
            self.show_message(warn_msg, 'warning')
            
        # 배치 작업을 Undo 스택에 추가
        batch_action = {
            'type': 'batch_delete',
            'items': [action for action in delete_actions if action.get('deleted_path') in successful_deletes],
            'timestamp': time.time()
        }
        self.actions.append(batch_action)
        self.undo_status_changed.emit(True)
        
        return True, successful_deletes
        
    def batch_move_files(self, move_actions: List[dict]) -> Tuple[bool, List[Tuple[str, str]]]:
        """
        여러 파일을 한 번에 이동하고 이를 하나의 Undo 작업으로 추적합니다.
        
        Args:
            move_actions: 이동할 파일들의 정보 목록 (각 항목은 moved_from, destination_folder, group_id, 
                          representative_path, member_paths, snapshot_rep, snapshot_members 정보를 포함하는 딕셔너리)
                            
        Returns:
            tuple: (성공 여부, 이동된 파일 경로와 대상 경로의 튜플 목록)
        """
        if not move_actions:
            print("[UndoManager] No files to move in batch")
            return False, []
            
        successful_moves = []
        failed_moves = []
        
        # 모든 파일에 대해 이동 시도
        for action in move_actions:
            source_path = action.get('moved_from')
            dest_folder = action.get('destination_folder')
            
            if not source_path or not os.path.exists(source_path):
                failed_moves.append((source_path if source_path else "Unknown source", 
                                    dest_folder if dest_folder else "Unknown destination"))
                continue
                
            if not dest_folder or not os.path.isdir(dest_folder):
                failed_moves.append((source_path, dest_folder if dest_folder else "Invalid destination"))
                continue
                
            try:
                base_filename = os.path.basename(source_path)
                destination_path = os.path.join(dest_folder, base_filename)
                
                # 대상 경로에 이미 파일이 있는 경우 확인
                if os.path.exists(destination_path):
                    # 배치 작업에서는 묻지 않고 경로를 변경하는 방식으로 처리
                    name, ext = os.path.splitext(base_filename)
                    timestamp = time.strftime("_%Y%m%d_%H%M%S")
                    new_filename = f"{name}{timestamp}{ext}"
                    destination_path = os.path.join(dest_folder, new_filename)
                    
                shutil.move(source_path, destination_path)
                # 성공한 이동 정보와 함께 원래 경로 정보도 저장
                action['moved_to'] = destination_path
                successful_moves.append((source_path, destination_path))
                print(f"[UndoManager] File moved: {source_path} -> {destination_path}")
            except Exception as e:
                print(f"[UndoManager] Failed to move file: {e}\nFrom: {source_path}")
                failed_moves.append((source_path, dest_folder))
                
        # 모든 이동이 실패한 경우
        if not successful_moves:
            if failed_moves:
                error_msg = f"Failed to move {len(failed_moves)} files."
                self.show_message(error_msg, 'error')
            return False, []
            
        # 실패한 항목이 있는 경우 경고 표시
        if failed_moves:
            warn_msg = f"Failed to move {len(failed_moves)} of {len(move_actions)} files."
            self.show_message(warn_msg, 'warning')
            
        # 배치 작업을 Undo 스택에 추가
        batch_action = {
            'type': 'batch_move',
            'items': [action for i, action in enumerate(move_actions) 
                     if i < len(successful_moves) and action.get('moved_from') == successful_moves[i][0]],
            'timestamp': time.time()
        }
        self.actions.append(batch_action)
        self.undo_status_changed.emit(True)
        
        return True, successful_moves
        
    def _undo_batch_deletion(self, batch_action):
        """
        배치 삭제 작업 취소 메서드
        
        Args:
            batch_action: 배치 삭제 작업 정보 (items 키에 개별 삭제 항목 목록 포함)
            
        Returns:
            tuple: (성공 여부, 복원된 파일 경로 목록)
        """
        items = batch_action.get('items', [])
        if not items:
            self.show_message("Invalid batch delete action data.", 'error')
            return False, None
            
        success_count = 0
        failed_count = 0
        restored_paths = []
        
        # 가장 최근 항목의 그룹 정보를 이용하여 UI 복원에 사용할 대표 정보
        last_group_id = None
        
        # 배치의 각 항목에 대해 복원 시도
        for item in items:
            deleted_path = item.get('deleted_path')
            group_id = item.get('group_id')
            
            if not deleted_path or not group_id:
                failed_count += 1
                continue
                
            # 마지막 처리된 그룹 ID 기록 (UI 복원용)
            last_group_id = group_id
                
            if self._restore_from_trash(deleted_path):
                success_count += 1
                restored_paths.append(deleted_path)
            else:
                failed_count += 1
                
        # 전체 결과 처리
        if success_count > 0:
            # 가장 마지막으로 복원된 항목의 그룹 정보를 이용하여 UI 업데이트 시그널 발생
            if last_group_id and items:
                # 배치의 마지막 항목으로 복원 시그널 발생
                self.group_state_restore_needed.emit(items[-1])
                
            result_message = f"{success_count}개 파일 복원 완료."
            if failed_count > 0:
                result_message += f" {failed_count}개 파일 복원 실패."
            print(f"[UndoManager] {result_message}")
            
            return True, restored_paths
        else:
            self.show_message("Failed to restore any files from trash.", 'error')
            return False, None
            
    def _undo_batch_move(self, batch_action):
        """
        배치 이동 작업 취소 메서드
        
        Args:
            batch_action: 배치 이동 작업 정보 (items 키에 개별 이동 항목 목록 포함)
            
        Returns:
            tuple: (성공 여부, 복원된 파일 경로 목록)
        """
        items = batch_action.get('items', [])
        if not items:
            self.show_message("Invalid batch move action data.", 'error')
            return False, None
            
        success_count = 0
        failed_count = 0
        restored_paths = []
        
        # 가장 최근 항목의 그룹 정보를 이용하여 UI 복원에 사용할 대표 정보
        last_group_id = None
        
        # 배치의 각 항목에 대해 이동 취소 시도
        for item in items:
            moved_from = item.get('moved_from')
            moved_to = item.get('moved_to')
            group_id = item.get('group_id')
            
            if not moved_from or not moved_to or not group_id:
                failed_count += 1
                continue
                
            # 마지막 처리된 그룹 ID 기록 (UI 복원용)
            last_group_id = group_id
                
            try:
                # 이동 취소 시도 (현재 위치에서 원래 위치로)
                if os.path.exists(moved_to):
                    # 원래 위치에 파일이 이미 있는지 확인
                    if os.path.exists(moved_from):
                        # 이름 충돌 시 새 이름 생성
                        dirname = os.path.dirname(moved_from)
                        basename = os.path.basename(moved_from)
                        name, ext = os.path.splitext(basename)
                        timestamp = time.strftime("_restored_%Y%m%d_%H%M%S")
                        new_path = os.path.join(dirname, f"{name}{timestamp}{ext}")
                        shutil.move(moved_to, new_path)
                        restored_paths.append(new_path)
                    else:
                        # 원래 위치로 이동
                        shutil.move(moved_to, moved_from)
                        restored_paths.append(moved_from)
                    
                    success_count += 1
                else:
                    failed_count += 1
                    print(f"[UndoManager] File not found for move undo: {moved_to}")
            except Exception as e:
                failed_count += 1
                print(f"[UndoManager] Error undoing move: {e}")
                
        # 전체 결과 처리
        if success_count > 0:
            # 가장 마지막으로 복원된 항목의 그룹 정보를 이용하여 UI 업데이트 시그널 발생
            if last_group_id and items:
                # 배치의 마지막 항목으로 복원 시그널 발생
                self.group_state_restore_needed.emit(items[-1])
                
            result_message = f"{success_count}개 파일 이동 취소 완료."
            if failed_count > 0:
                result_message += f" {failed_count}개 파일 이동 취소 실패."
            print(f"[UndoManager] {result_message}")
            
            return True, restored_paths
        else:
            self.show_message("Failed to restore any moved files.", 'error')
            return False, None
            
    # _add_to_table 메서드는 더 이상 직접 사용되지 않음 (제거 또는 주석 처리)
    # def _add_to_table(self, action_details: Dict[str, Any]) -> bool:
    #     ... 
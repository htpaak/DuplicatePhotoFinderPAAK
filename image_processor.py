import os
from PIL import Image
import imagehash
from typing import List, Tuple, Dict, Optional
from PyQt5.QtCore import QObject, pyqtSignal

SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}

class ScanWorker(QObject):
    """별도 스레드에서 이미지 스캔 작업을 수행하는 워커"""
    scan_started = pyqtSignal(int) # 총 스캔할 파일 수 전달
    progress_updated = pyqtSignal(int) # 스캔한 파일 수 전달
    scan_finished = pyqtSignal(int, int, list) # 총 파일 수, 스캔 완료 수, 중복 목록 전달
    error_occurred = pyqtSignal(str) # 오류 메시지 전달

    def __init__(self, folder_path: str, hash_size: int = 8):
        super().__init__()
        self.folder_path = folder_path
        self.hash_size = hash_size
        self._is_running = True # 외부에서 중단 요청 가능하도록 플래그 추가 (선택적)

    def run_scan(self):
        """이미지 스캔 작업을 실행합니다."""
        image_hashes: Dict[str, imagehash.ImageHash] = {}
        duplicates: List[Tuple[str, str, int]] = []
        scanned_files = 0
        total_image_files = 0

        try:
            all_files = os.listdir(self.folder_path)
            # 스캔 대상 이미지 파일 수 미리 계산
            image_files_to_scan = [
                f for f in all_files
                if os.path.isfile(os.path.join(self.folder_path, f))
                and os.path.splitext(f)[1].lower() in SUPPORTED_FORMATS
            ]
            total_image_files = len(image_files_to_scan)

            # 스캔 시작 신호 (총 파일 수 전달)
            self.scan_started.emit(total_image_files)

            # 실제 스캔은 계산된 목록 사용
            for i, filename in enumerate(image_files_to_scan):
                if not self._is_running:
                    print("Scan cancelled.")
                    break

                file_path = os.path.join(self.folder_path, filename)
                # _, ext = os.path.splitext(filename) # 이미 위에서 필터링됨

                # if os.path.isfile(file_path) and ext.lower() in SUPPORTED_FORMATS: # 이미 위에서 필터링됨
                scanned_files += 1
                try:
                    img = Image.open(file_path)
                    current_hash = imagehash.phash(img, hash_size=self.hash_size)
                    img.close()

                    found_duplicate = False
                    for path, existing_hash in image_hashes.items():
                        similarity = existing_hash - current_hash
                        if similarity <= 5:
                            duplicates.append((path, file_path, 100 - similarity * 100 // (self.hash_size**2)))
                            found_duplicate = True
                            # break

                    if not found_duplicate:
                            image_hashes[file_path] = current_hash

                except Exception as e:
                    print(f"Error processing file {file_path}: {e}")

                # 진행률 업데이트 (매 파일 처리 후 또는 주기적)
                # if scanned_files % 5 == 0 or i == total_image_files - 1:
                self.progress_updated.emit(scanned_files) # 매 파일마다 업데이트

            if self._is_running:
                # 완료 신호 발생 (총 파일 수, 실제 스캔된 수, 중복 목록)
                self.scan_finished.emit(total_image_files, scanned_files, duplicates)

        except FileNotFoundError:
            self.error_occurred.emit(f"Error: Folder not found - {self.folder_path}")
        except Exception as e:
            self.error_occurred.emit(f"An unexpected error occurred during scan: {e}")

    def stop(self):
        """스캔 작업을 중단하도록 요청합니다."""
        self._is_running = False

# 기존 find_duplicates 함수는 유지하거나 제거 (이제 ScanWorker 사용)
# def find_duplicates(folder_path: str, hash_size: int = 8) -> Tuple[int, List[Tuple[str, str, int]]]:
#    ... 
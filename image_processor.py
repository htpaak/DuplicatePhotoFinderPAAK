import os
from PIL import Image
import imagehash
from typing import List, Tuple, Dict, Optional
from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np # NumPy 임포트
import rawpy # rawpy 임포트

# Pillow에서 일반적으로 지원하는 정적 이미지 형식 추가
SUPPORTED_FORMATS = {
    # 기존 형식
    '.png', '.jpg', '.jpeg', '.bmp', '.webp',
    # 추가 형식
    '.tif', '.tiff', '.ico', '.pcx',
    '.ppm', '.pgm', '.pbm', '.tga',
    # RAW 형식 (일반적인 것들)
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.rw2', '.orf',
    '.raf', '.pef', '.srw', '.kdc', '.raw'
}

# RAW 확장자만 따로 관리 (파일 처리 분기용)
RAW_EXTENSIONS = {
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.rw2', '.orf',
    '.raf', '.pef', '.srw', '.kdc', '.raw'
}

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
        """이미지 스캔 작업을 실행합니다 (RAW 지원 포함)."""
        image_hashes: Dict[str, imagehash.ImageHash] = {}
        duplicates: List[Tuple[str, str, int]] = []
        processed_files_count = 0 # 실제로 처리(해싱)된 파일 수
        total_target_files = 0 # 스캔 대상 확장자를 가진 총 파일 수

        try:
            all_files_in_folder = os.listdir(self.folder_path)
            target_files = [
                f for f in all_files_in_folder
                if os.path.isfile(os.path.join(self.folder_path, f))
                and os.path.splitext(f)[1].lower() in SUPPORTED_FORMATS
            ]
            total_target_files = len(target_files)
            self.scan_started.emit(total_target_files)

            for filename in target_files:
                if not self._is_running:
                    print("Scan cancelled.")
                    break

                file_path = os.path.join(self.folder_path, filename)
                file_ext = os.path.splitext(filename)[1].lower()
                img_pil = None # PIL Image 객체 저장용
                raw_obj = None # rawpy 객체 저장용

                try:
                    # 파일 확장자에 따라 처리 분기
                    if file_ext in RAW_EXTENSIONS:
                        try:
                            raw_obj = rawpy.imread(file_path)
                            # postprocess()로 RGB 이미지 데이터(NumPy 배열) 얻기
                            # 옵션 추가 가능: use_camera_wb=True, half_size=True 등
                            rgb_array = raw_obj.postprocess()
                            img_pil = Image.fromarray(rgb_array) # NumPy 배열을 PIL Image로 변환
                            print(f"Processed RAW: {file_path}")
                        except rawpy.LibRawIOError:
                            print(f"Skipping RAW (I/O Error or unsupported): {file_path}")
                            continue # 지원하지 않는 RAW 형식이거나 I/O 오류 시 건너뛰기
                        except Exception as raw_err:
                            print(f"Error processing RAW file {file_path}: {raw_err}")
                            continue # 기타 rawpy 오류 시 건너뛰기
                        finally:
                            if raw_obj:
                                raw_obj.close() # rawpy 객체 리소스 해제
                    else:
                        # 기존 Pillow 로직 (WebP 애니메이션 체크 포함)
                        img = Image.open(file_path)
                        is_animated_webp = False
                        if file_ext == '.webp':
                            try:
                                if img.n_frames > 1:
                                    is_animated_webp = True
                            except AttributeError:
                                try:
                                    img.seek(1)
                                    is_animated_webp = True
                                    img.seek(0)
                                except EOFError:
                                    pass
                        if is_animated_webp:
                            print(f"Skipping animated WebP: {file_path}")
                            img.close()
                            continue
                        # Pillow로 열린 이미지를 img_pil에 할당
                        img_pil = img
                        # img.close() 는 finally 블록에서 img_pil이 None이 아닐 때 처리

                    # img_pil 객체가 생성되었으면 해시 계산 진행
                    if img_pil:
                        processed_files_count += 1
                        current_hash = imagehash.phash(img_pil, hash_size=self.hash_size)

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
                    # 파일 열기/처리 중 오류 발생 시 (처리된 파일 수에 포함 안 됨)
                    print(f"Error processing file {file_path}: {e}")
                finally:
                    # Pillow 이미지 객체 닫기 (img_pil이 Pillow 객체일 때)
                    if img_pil and not file_ext in RAW_EXTENSIONS and hasattr(img_pil, 'close'):
                        try:
                            img_pil.close()
                        except Exception as close_err:
                            print(f"Error closing PIL image {file_path}: {close_err}")

                # 진행률 업데이트 (처리된 파일 수 기준)
                self.progress_updated.emit(processed_files_count)

            if self._is_running:
                # 완료 신호 (총 대상 파일 수, 처리된 파일 수, 중복 목록)
                self.scan_finished.emit(total_target_files, processed_files_count, duplicates)

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
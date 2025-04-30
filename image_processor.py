import os
from PIL import Image
import imagehash
from typing import List, Dict, Optional, Set, Tuple
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

# 해시 유사도 임계값
HASH_THRESHOLD = 5

# 새로운 시그널 데이터 타입 정의 (가독성 위해)
# List[Tuple[str, List[Tuple[str, int]]]]
# -> 대표 파일 경로, [(멤버 파일 경로, 대표와의 유사도 점수), ...]
DuplicateGroupWithSimilarity = List[Tuple[str, List[Tuple[str, int]]]]

class ScanWorker(QObject):
    """별도 스레드에서 이미지 스캔 작업을 수행하는 워커"""
    scan_started = pyqtSignal(int) # 총 스캔할 파일 수 전달
    progress_updated = pyqtSignal(int) # 스캔한 파일 수 전달
    # scan_finished 시그널의 세 번째 인자 타입을 list로 유지 (내부 데이터 구조 변경)
    scan_finished = pyqtSignal(int, int, list) # 총 파일 수, 스캔 완료 수, 중복 그룹 정보 전달
    error_occurred = pyqtSignal(str) # 오류 메시지 전달

    def __init__(self, folder_path: str, hash_size: int = 8):
        super().__init__()
        self.folder_path = folder_path
        self.hash_size = hash_size
        self._is_running = True # 외부에서 중단 요청 가능하도록 플래그 추가 (선택적)

    def run_scan(self):
        """이미지 스캔 작업을 실행하여 중복 그룹 목록과 유사도 점수를 반환합니다."""
        # 해시를 키로, (파일 경로, 대표 해시와의 거리) 튜플 리스트를 값으로 갖는 딕셔너리
        hashes_to_files: Dict[imagehash.ImageHash, List[Tuple[str, int]]] = {}
        # 이미 처리된(그룹에 포함된) 파일 경로 집합
        grouped_files: Set[str] = set()
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

            for i, filename in enumerate(target_files):
                if not self._is_running:
                    break

                file_path = os.path.join(self.folder_path, filename)

                # 이미 그룹화된 파일은 건너뛰기
                if file_path in grouped_files:
                    self.progress_updated.emit(i + 1)
                    continue
                
                file_ext = os.path.splitext(filename)[1].lower()
                img_pil = None 
                raw_obj = None 
                current_hash = None
                try:
                    # 파일 확장자에 따라 처리 분기
                    if file_ext in RAW_EXTENSIONS:
                        try:
                            raw_obj = rawpy.imread(file_path)
                            # postprocess()로 RGB 이미지 데이터(NumPy 배열) 얻기
                            # 옵션 추가 가능: use_camera_wb=True, half_size=True 등
                            rgb_array = raw_obj.postprocess(use_camera_wb=True)
                            img_pil = Image.fromarray(rgb_array) # NumPy 배열을 PIL Image로 변환
                            # print(f"Processed RAW: {file_path}") # 디버깅용 로그 비활성화
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

                        found_group = False
                        # 기존 해시 그룹들과 비교
                        for existing_hash, file_list_with_similarity in hashes_to_files.items():
                            similarity = current_hash - existing_hash # 해시 거리 계산
                            # --- 유사도 계산 로그 제거 ---
                            # print(f"[Debug] Comparing {os.path.basename(file_path)} ({current_hash}) with group hash {existing_hash}. Similarity: {similarity}")
                            # --- 로그 제거 끝 ---
                            if similarity <= HASH_THRESHOLD:
                                # 유사 그룹 발견 시 현재 파일과 유사도 점수 추가
                                file_list_with_similarity.append((file_path, similarity))
                                # --- 그룹 추가 로그 제거 ---
                                # print(f"[Debug] Added {os.path.basename(file_path)} to group {existing_hash} with calculated similarity {similarity}")
                                # --- 로그 제거 끝 ---
                                grouped_files.add(file_path) # 그룹화된 파일로 등록
                                found_group = True
                                break # 첫 번째 매칭 그룹에만 추가

                        # 유사 그룹 없으면 새로운 그룹 생성 (대표 파일, 유사도 0)
                        if not found_group:
                            hashes_to_files[current_hash] = [(file_path, 0)]
                            # grouped_files.add(file_path) # 새 그룹의 첫 파일은 등록 불필요
                
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
                self.progress_updated.emit(i + 1)

            # --- 최종 중복 그룹 목록 생성 전 데이터 확인 로그 제거 ---
            # print("\n--- [Debug] Content of hashes_to_files before final processing ---")
            # for h, file_list in hashes_to_files.items():
            #      if len(file_list) > 1:
            #           print(f"Hash: {h}, Files: {[(os.path.basename(p), s) for p, s in file_list]}")
            # print("--- [Debug] End of hashes_to_files content ---\n")
            # --- 로그 제거 끝 ---
            
            # --- 최종 중복 그룹 목록 생성 (새로운 형식) ---
            # DuplicateGroupWithSimilarity = List[Tuple[str, List[Tuple[str, int]]]]
            duplicate_groups_with_similarity: DuplicateGroupWithSimilarity = []
            if self._is_running:
                for file_list_with_similarity in hashes_to_files.values():
                    if len(file_list_with_similarity) > 1: # 그룹 크기가 2 이상인 경우만
                        # 첫 번째 파일을 대표로 설정
                        representative_path, _ = file_list_with_similarity[0]
                        # 멤버 목록 생성 (대표 제외, 경로와 유사도 점수 포함)
                        members_with_similarity = []
                        # 리스트의 두 번째 요소부터 순회
                        for path, similarity in file_list_with_similarity[1:]:
                             # --- 내부 루프 값 확인 로그 제거 ---
                             # print(f"[Debug] Processing member for final list: Path={os.path.basename(path)}, Similarity={similarity}")
                             # --- 로그 제거 끝 ---
                             members_with_similarity.append((path, similarity))
                        
                        if members_with_similarity:
                             duplicate_groups_with_similarity.append((representative_path, members_with_similarity))
                             # --- 최종 데이터 구조 로그 제거 ---
                             # print(f"[Debug] Final group data added: Rep={os.path.basename(representative_path)}, Members={[(os.path.basename(p), s) for p, s in members_with_similarity]}")
                             # --- 로그 제거 끝 ---

                # 완료 신호 (새로운 데이터 구조 전달)
                # --- 시그널 방출 전 데이터 로그 제거 ---
                # print(f"[Debug] Emitting scan_finished with data: {duplicate_groups_with_similarity}")
                # --- 로그 제거 끝 ---
                self.scan_finished.emit(total_target_files, processed_files_count, duplicate_groups_with_similarity)

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
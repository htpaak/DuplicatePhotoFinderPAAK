import os
from PIL import Image
import imagehash
from typing import List, Dict, Optional, Set, Tuple
from PyQt5.QtCore import QObject, pyqtSignal
import numpy as np # NumPy 임포트
import rawpy # rawpy 임포트
# 비디오 처리 임포트 추가
from video_processor import VideoProcessor
from video_duplicate_finder import VideoDuplicateFinder
# 파일 형식 정의 모듈 임포트
from supported_formats import (
    STATIC_IMAGE_FORMATS, RAW_EXTENSIONS, VIDEO_ANIMATION_EXTENSIONS, 
    ALL_SUPPORTED_FORMATS, HASH_THRESHOLD, VIDEO_SIMILARITY_THRESHOLD,
    FRAME_CHECK_FORMATS, VIDEO_ONLY_EXTENSIONS
)

# 기존 중복 정의 제거하고 임포트된 상수 사용
SUPPORTED_FORMATS = STATIC_IMAGE_FORMATS.union(RAW_EXTENSIONS)
VIDEO_EXTENSIONS = VIDEO_ONLY_EXTENSIONS

# 지원하는 모든 파일 형식 (이미지 + 비디오)
ALL_SUPPORTED_FORMATS = STATIC_IMAGE_FORMATS.union(RAW_EXTENSIONS).union(VIDEO_ONLY_EXTENSIONS).union(FRAME_CHECK_FORMATS)

# 해시 유사도 임계값 - 모듈에서 임포트함으로 제거
# HASH_THRESHOLD = 5
# 비디오 유사도 임계값 - 모듈에서 임포트함으로 제거
# VIDEO_SIMILARITY_THRESHOLD = 85.0

# 새로운 시그널 데이터 타입 정의 (가독성 위해)
# List[Tuple[str, List[Tuple[str, int]]]]
# -> 대표 파일 경로, [(멤버 파일 경로, 대표와의 유사도 점수), ...]
DuplicateGroupWithSimilarity = List[Tuple[str, List[Tuple[str, int]]]]

class ScanWorker(QObject):
    """별도 스레드에서 이미지와 비디오 스캔 작업을 수행하는 워커"""
    scan_started = pyqtSignal(int) # 총 스캔할 파일 수 전달
    progress_updated = pyqtSignal(int) # 스캔한 파일 수 전달
    # scan_finished 시그널의 세 번째 인자 타입을 list로 유지 (내부 데이터 구조 변경)
    scan_finished = pyqtSignal(int, int, list) # 총 파일 수, 스캔 완료 수, 중복 그룹 정보 전달
    error_occurred = pyqtSignal(str) # 오류 메시지 전달

    def __init__(self, folder_path: str, include_subfolders: bool = False, hash_size: int = 8):
        super().__init__()
        self.folder_path = folder_path
        self.include_subfolders = include_subfolders
        self.hash_size = hash_size
        self._is_running = True # 외부에서 중단 요청 가능하도록 플래그 추가 (선택적)
        # 비디오 처리 객체 초기화
        self.video_finder = VideoDuplicateFinder()
        
    def check_animation_frames(self, file_path):
        """
        파일이 다중 프레임을 가진 애니메이션인지 확인합니다.
        
        반환값:
            - True: 다중 프레임 애니메이션
            - False: 단일 프레임 이미지
            - None: 확인할 수 없음
        """
        try:
            _, ext = os.path.splitext(file_path.lower())
            
            # 프레임 검사가 필요한 포맷인 경우
            if ext in FRAME_CHECK_FORMATS:
                with Image.open(file_path) as img:
                    # 여러 프레임이 있는지 확인
                    try:
                        # n_frames 속성이 있는 경우
                        if hasattr(img, 'n_frames') and img.n_frames > 1:
                            print(f"다중 프레임 애니메이션 감지됨: {os.path.basename(file_path)} ({img.n_frames}프레임)")
                            return True
                    except AttributeError:
                        pass
                    
                    # seek 메서드로 확인 시도
                    try:
                        img.seek(1)  # 두 번째 프레임 확인
                        print(f"다중 프레임 애니메이션 감지됨: {os.path.basename(file_path)} (seek 메서드)")
                        img.seek(0)  # 첫 번째 프레임으로 되돌림
                        return True
                    except EOFError:
                        # 두 번째 프레임이 없으면 단일 프레임 이미지
                        return False
            
            # 프레임 검사가 필요 없는 포맷인 경우
            return None
            
        except Exception as e:
            print(f"프레임 확인 중 오류: {file_path} - {e}")
            return None

    def run_scan(self):
        """이미지와 비디오 스캔 작업을 실행하여 중복 그룹 목록과 유사도 점수를 반환합니다."""
        # 해시를 키로, (파일 경로, 대표 해시와의 거리) 튜플 리스트를 값으로 갖는 딕셔너리
        hashes_to_files: Dict[imagehash.ImageHash, List[Tuple[str, int]]] = {}
        # 이미 처리된(그룹에 포함된) 파일 경로 집합
        grouped_files: Set[str] = set()
        processed_files_count = 0 # 실제로 처리(해싱)된 파일 수
        total_target_files = 0 # 스캔 대상 확장자를 가진 총 파일 수
        target_files = [] # 스캔 대상 이미지 파일 목록
        video_files = [] # 비디오 파일 목록

        try:
            # 하위폴더 포함 여부에 따라 다른 방식으로 파일 수집
            if self.include_subfolders:
                # 하위폴더를 포함한 모든 파일 수집 (os.walk 사용)
                for root, _, files in os.walk(self.folder_path):
                    for filename in files:
                        file_ext = os.path.splitext(filename)[1].lower()
                        file_path = os.path.join(root, filename)
                        if not os.path.isfile(file_path):
                            continue
                            
                        # 항상 이미지인 포맷
                        if file_ext in STATIC_IMAGE_FORMATS or file_ext in RAW_EXTENSIONS:
                            target_files.append(file_path)
                        # 항상 비디오/애니메이션인 포맷
                        elif file_ext in VIDEO_ONLY_EXTENSIONS:
                            video_files.append(file_path)
                        # 프레임 검사가 필요한 포맷 (.webp, .gif 등)
                        elif file_ext in FRAME_CHECK_FORMATS:
                            # 프레임 수에 따라 이미지 또는 비디오로 분류
                            is_animation = self.check_animation_frames(file_path)
                            if is_animation is True:  # 애니메이션
                                video_files.append(file_path)
                            elif is_animation is False:  # 정적 이미지
                                target_files.append(file_path)
                            else:  # 알 수 없음, 확장자 기반으로 판단
                                if file_ext in ['.gif', '.apng']:  # 일반적으로 애니메이션
                                    video_files.append(file_path)
                                else:  # 일반적으로 이미지
                                    target_files.append(file_path)
            else:
                # 현재 폴더의 파일만 수집 (기존 방식)
                all_files_in_folder = os.listdir(self.folder_path)
                for filename in all_files_in_folder:
                    file_path = os.path.join(self.folder_path, filename)
                    if not os.path.isfile(file_path):
                        continue
                        
                    file_ext = os.path.splitext(filename)[1].lower()
                    # 항상 이미지인 포맷
                    if file_ext in STATIC_IMAGE_FORMATS or file_ext in RAW_EXTENSIONS:
                        target_files.append(file_path)
                    # 항상 비디오/애니메이션인 포맷
                    elif file_ext in VIDEO_ONLY_EXTENSIONS:
                        video_files.append(file_path)
                    # 프레임 검사가 필요한 포맷 (.webp, .gif 등)
                    elif file_ext in FRAME_CHECK_FORMATS:
                        # 프레임 수에 따라 이미지 또는 비디오로 분류
                        is_animation = self.check_animation_frames(file_path)
                        if is_animation is True:  # 애니메이션
                            video_files.append(file_path)
                        elif is_animation is False:  # 정적 이미지
                            target_files.append(file_path)
                        else:  # 알 수 없음, 확장자 기반으로 판단
                            if file_ext in ['.gif', '.apng']:  # 일반적으로 애니메이션
                                video_files.append(file_path)
                            else:  # 일반적으로 이미지
                                target_files.append(file_path)
            
            total_target_files = len(target_files) + len(video_files)
            self.scan_started.emit(total_target_files)
            
            print(f"이미지 파일 수: {len(target_files)}, 비디오/애니메이션 파일 수: {len(video_files)}")

            # 이미지 파일 처리
            for i, file_path in enumerate(target_files):
                if not self._is_running:
                    break

                # 이미 그룹화된 파일은 건너뛰기
                if file_path in grouped_files:
                    self.progress_updated.emit(i + 1)
                    continue
                
                file_ext = os.path.splitext(file_path)[1].lower()
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
                        # Pillow 로직 (WebP 애니메이션 체크는 이미 앞에서 처리됨)
                        img_pil = Image.open(file_path)

                    # img_pil 객체가 생성되었으면 해시 계산 진행
                    if img_pil:
                        processed_files_count += 1
                        current_hash = imagehash.phash(img_pil, hash_size=self.hash_size)

                        found_group = False
                        # 기존 해시 그룹들과 비교
                        for existing_hash, file_list_with_similarity in hashes_to_files.items():
                            similarity = current_hash - existing_hash # 해시 거리 계산
                            if similarity <= HASH_THRESHOLD:
                                # 유사 그룹 발견 시 현재 파일과 유사도 점수 추가
                                file_list_with_similarity.append((file_path, similarity))
                                grouped_files.add(file_path) # 그룹화된 파일로 등록
                                found_group = True
                                break # 첫 번째 매칭 그룹에만 추가

                        # 유사 그룹 없으면 새로운 그룹 생성 (대표 파일, 유사도 0)
                        if not found_group:
                            hashes_to_files[current_hash] = [(file_path, 0)]
                
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
            
            # 비디오 파일 처리
            if video_files and self._is_running:
                try:
                    # PyAV 라이브러리 확인
                    if VideoProcessor.check_av():
                        print("비디오 파일 처리 중...")
                        # 비디오 중복 찾기 수행
                        video_duplicates = self.video_finder.find_duplicates(video_files)
                        
                        # 진행률 업데이트 (비디오 파일도 처리했으므로 전체 파일 수로 업데이트)
                        processed_files_count += len(video_files)
                        self.progress_updated.emit(total_target_files)
                except Exception as e:
                    print(f"비디오 처리 중 오류 발생: {e}")
            
            # --- 최종 중복 그룹 목록 생성 (새로운 형식) ---
            # DuplicateGroupWithSimilarity = List[Tuple[str, List[Tuple[str, int]]]]
            duplicate_groups_with_similarity: DuplicateGroupWithSimilarity = []
            if self._is_running:
                # 이미지 중복 그룹 처리
                for file_list_with_similarity in hashes_to_files.values():
                    if len(file_list_with_similarity) > 1: # 그룹 크기가 2 이상인 경우만
                        # 첫 번째 파일을 대표로 설정
                        representative_path, _ = file_list_with_similarity[0]
                        # 멤버 목록 생성 (대표 제외, 경로와 유사도 점수 포함)
                        members_with_similarity = []
                        # 리스트의 두 번째 요소부터 순회
                        for path, similarity in file_list_with_similarity[1:]:
                             members_with_similarity.append((path, similarity))
                        # 멤버가 있으면 그룹 추가
                        if members_with_similarity:
                             duplicate_groups_with_similarity.append(
                                 (representative_path, members_with_similarity)
                             )
                
                # 비디오 중복 그룹 처리 (video_duplicates가 정의된 경우)
                if 'video_duplicates' in locals() and video_duplicates:
                    for rep_path, dupes in video_duplicates:
                        # 유사도 점수 처리 - 원래의 부동 소수점 값 유지
                        members = [(dupe_path, similarity) for dupe_path, similarity in dupes]
                        if members:
                            print(f"비디오 중복 그룹 추가: {os.path.basename(rep_path)}, 멤버 수: {len(members)}")
                            for mem_path, sim in members:
                                print(f"  - {os.path.basename(mem_path)}: 유사도 {sim:.1f}%")
                            duplicate_groups_with_similarity.append((rep_path, members))
                
                # 최종 처리된 파일 수와 중복 그룹 목록 전달
                self.scan_finished.emit(
                    total_target_files,
                    processed_files_count,
                    duplicate_groups_with_similarity
                )
        except Exception as global_e:
            # 전역 예외 처리 (워커 전체 실패)
            error_message = f"Error in scan worker: {global_e}"
            print(error_message)
            self.error_occurred.emit(error_message)
            
    def stop(self):
        """현재 실행 중인 스캔 작업을 중지하기 위한 메서드"""
        self._is_running = False

# 기존 find_duplicates 함수는 유지하거나 제거 (이제 ScanWorker 사용)
# def find_duplicates(folder_path: str, hash_size: int = 8) -> Tuple[int, List[Tuple[str, str, int]]]:
#    ... 
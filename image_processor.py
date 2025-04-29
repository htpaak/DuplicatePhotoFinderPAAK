import os
from PIL import Image
import imagehash
from typing import List, Tuple, Dict, Optional

SUPPORTED_FORMATS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}

def find_duplicates(folder_path: str, hash_size: int = 8) -> Tuple[int, List[Tuple[str, str, int]]]:
    """지정된 폴더에서 중복 이미지를 찾아 리스트로 반환합니다.

    Args:
        folder_path: 이미지를 스캔할 폴더 경로.
        hash_size: 이미지 해시 계산에 사용할 크기 (값이 클수록 정밀하지만 느려짐).

    Returns:
        Tuple: (스캔한 총 파일 수, 중복 이미지 쌍 리스트 [(원본 경로, 중복 경로, 유사도)])
               유사도는 해시 간의 해밍 거리(차이 비트 수)이며, 0이 완전 일치입니다.
    """
    image_hashes: Dict[str, imagehash.ImageHash] = {}
    duplicates: List[Tuple[str, str, int]] = []
    scanned_files = 0

    try:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            _, ext = os.path.splitext(filename)

            if os.path.isfile(file_path) and ext.lower() in SUPPORTED_FORMATS:
                scanned_files += 1
                try:
                    img = Image.open(file_path)
                    # 이미지 로딩 후 바로 닫아 메모리 확보 (필요 시)
                    # img.verify() # Pillow 이슈로 verify() 후 다시 열어야 할 수 있음
                    # img = Image.open(file_path)
                    current_hash = imagehash.phash(img, hash_size=hash_size)
                    img.close() # 파일 핸들 닫기

                    # 기존 해시들과 비교
                    found_duplicate = False
                    for path, existing_hash in image_hashes.items():
                        similarity = existing_hash - current_hash # 해밍 거리 계산
                        # 임계값 설정 (예: 해밍 거리가 5 이하이면 중복으로 간주)
                        # TODO: 임계값을 사용자가 조절할 수 있도록 개선 가능
                        if similarity <= 5:
                            duplicates.append((path, file_path, 100 - similarity * 100 // (hash_size**2))) # 유사도 % 변환 (근사치)
                            found_duplicate = True
                            # 하나의 원본에 여러 중복이 매칭될 수 있도록 break 제거 가능
                            # break

                    # 새 이미지 해시 추가 (중복이 아닌 경우 또는 모든 비교 후)
                    # 동일한 해시가 이미 있어도 추가 (다른 원본과 비교 위함)
                    # TODO: 완전 동일 해시 처리 전략 결정 필요 (덮어쓰기 or 리스트 관리)
                    if not found_duplicate: # 중복으로 발견되지 않은 경우만 원본 후보로 추가
                         image_hashes[file_path] = current_hash

                except Exception as e:
                    print(f"Error processing file {file_path}: {e}") # 오류 로그

    except FileNotFoundError:
        print(f"Error: Folder not found - {folder_path}")
        return 0, []
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return 0, []

    return scanned_files, duplicates 
"""
파일 형식 정의 모듈

이 모듈은 프로그램에서 지원하는 모든 파일 형식을 정의합니다.
이미지, 비디오, 애니메이션 등의 형식을 집합(set) 또는 리스트(list)로 정의하여
코드의 일관성을 유지하고 중복을 방지합니다.
"""

# Pillow에서 일반적으로 지원하는 정적 이미지 형식
STATIC_IMAGE_FORMATS = {
    # 기본 형식
    '.png', '.jpg', '.jpeg', '.bmp', '.webp',
    # 추가 형식
    '.tif', '.tiff', '.ico', '.pcx',
    '.ppm', '.pgm', '.pbm', '.tga',
}

# RAW 이미지 확장자
RAW_EXTENSIONS = {
    '.cr2', '.cr3', '.nef', '.arw', '.dng', '.rw2', '.orf',
    '.raf', '.pef', '.srw', '.kdc', '.raw'
}

# 모든 이미지 형식 = 정적 이미지 + RAW 이미지
SUPPORTED_IMAGE_FORMATS = STATIC_IMAGE_FORMATS.union(RAW_EXTENSIONS)

# 비디오 및 애니메이션 확장자
VIDEO_ANIMATION_EXTENSIONS = {
    # 일반 비디오 형식
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', 
    '.m4v', '.mpg', '.mpeg', '.3gp',
    # 애니메이션 형식
    '.gif', '.apng', '.mng', '.webp', '.svg', '.ani', '.swf'
}

# 지원하는 모든 파일 형식 (이미지 + 비디오 + 애니메이션)
ALL_SUPPORTED_FORMATS = SUPPORTED_IMAGE_FORMATS.union(VIDEO_ANIMATION_EXTENSIONS)

# 리스트 형태로도 제공 (일부 API에서 필요할 수 있음)
VIDEO_ANIMATION_EXTENSIONS_LIST = list(VIDEO_ANIMATION_EXTENSIONS)
ALL_SUPPORTED_FORMATS_LIST = list(ALL_SUPPORTED_FORMATS)

# 해시 유사도 임계값
HASH_THRESHOLD = 5
# 비디오 유사도 임계값
VIDEO_SIMILARITY_THRESHOLD = 85.0 